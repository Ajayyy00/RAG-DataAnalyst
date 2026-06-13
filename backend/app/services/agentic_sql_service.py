"""
Agentic SQL Service using LangGraph.
Implements a multi-agent workflow for generating SQL:
1. Schema Understanding
2. Query Planning
3. SQL Generation
4. SQL Validation
5. Query Optimization
"""

from typing import Annotated, TypedDict, List, Optional, Dict, Any
import operator

import structlog
from prometheus_client import Counter, Histogram

from langchain_core.messages import SystemMessage, HumanMessage
from langchain_openai import ChatOpenAI
from langgraph.graph import StateGraph, END

from app.config import get_settings
from app.services.rag_service import RAGService
from app.services.sql_validation_service import SQLValidationService
from app.core.exceptions import LLMServiceError

log = structlog.get_logger(__name__)
settings = get_settings()

# Prometheus Metrics
AGENT_STEPS = Counter(
    "agentic_sql_steps_total",
    "Total number of agent steps executed",
    ["agent_name"]
)
AGENT_ERRORS = Counter(
    "agentic_sql_errors_total",
    "Total number of errors encountered during agentic SQL generation",
    ["error_type"]
)
AGENT_LATENCY = Histogram(
    "agentic_sql_step_latency_seconds",
    "Latency of individual agent steps",
    ["agent_name"]
)

# Define State
class AgentState(TypedDict):
    question: str
    schema_context: str
    plan: str
    sql_draft: str
    validation_errors: str
    final_sql: str
    retry_count: int
    index_suggestions: List[str]
    execution_plan: Optional[Dict[str, Any]]

# Initialize LLM
llm = ChatOpenAI(
    base_url=settings.llm_base_url,
    api_key=settings.llm_api_key or "not-needed",
    model=settings.llm_model,
    max_tokens=settings.llm_max_tokens,
    temperature=settings.llm_temperature,
)

from app.services.sql_optimization_engine import SQLOptimizationEngine

class AgenticSQLService:
    def __init__(self, db_session, current_user=None):
        self.db = db_session
        self.current_user = current_user
        self.rag_service = RAGService()
        self.validation_service = SQLValidationService()
        self.optimization_engine = SQLOptimizationEngine()
        self.graph = self._build_graph()

    def _build_graph(self):
        workflow = StateGraph(AgentState)

        # Add nodes
        workflow.add_node("schema_agent", self.schema_agent)
        workflow.add_node("planning_agent", self.planning_agent)
        workflow.add_node("generation_agent", self.generation_agent)
        workflow.add_node("validation_agent", self.validation_agent)
        workflow.add_node("optimization_agent", self.optimization_agent)

        # Define edges
        workflow.set_entry_point("schema_agent")
        workflow.add_edge("schema_agent", "planning_agent")
        workflow.add_edge("planning_agent", "generation_agent")
        workflow.add_edge("generation_agent", "validation_agent")
        
        # Conditional edge from validation
        workflow.add_conditional_edges(
            "validation_agent",
            self.route_validation,
            {
                "generation_agent": "generation_agent",
                "optimization_agent": "optimization_agent",
                "end": END
            }
        )
        
        workflow.add_edge("optimization_agent", END)
        
        return workflow.compile()

    async def schema_agent(self, state: AgentState) -> AgentState:
        with AGENT_LATENCY.labels(agent_name="schema").time():
            AGENT_STEPS.labels(agent_name="schema").inc()
            log.info("Running Schema Agent")
            try:
                role = getattr(self.current_user, "role", "analyst")
                if hasattr(role, "value"):
                    role = role.value
                
                # Fetch schema from RAG based on the question
                schema_context = self.rag_service.retrieve_schema_context(state["question"], top_k=5, user_role=role)
                return {"schema_context": schema_context}
            except Exception as e:
                AGENT_ERRORS.labels(error_type="schema_fetch").inc()
                log.error("Schema fetch failed", error=str(e))
                return {"schema_context": "Error retrieving schema"}

    async def planning_agent(self, state: AgentState) -> AgentState:
        with AGENT_LATENCY.labels(agent_name="planning").time():
            AGENT_STEPS.labels(agent_name="planning").inc()
            log.info("Running Planning Agent")
            
            role = getattr(self.current_user, "role", "analyst")
            if hasattr(role, "value"):
                role = role.value
            
            rbac_instruction = ""
            if role == "doctor":
                rbac_instruction = "IMPORTANT: The user is a DOCTOR. Queries MUST only relate to clinical care (e.g. patients, diagnoses, medications, encounters). Do NOT query financial tables like claims."
            elif role == "nurse":
                rbac_instruction = "IMPORTANT: The user is a NURSE. Queries MUST only relate to direct patient vitals, medications, and encounters. Do NOT query financial claims or provider payroll."
            elif role == "analyst":
                rbac_instruction = "IMPORTANT: The user is a DATA ANALYST. Queries MUST NOT expose patient PII (e.g., mrn, first_name, last_name). Aggregate data is preferred."
            else:
                rbac_instruction = "The user is an ADMIN with full access."

            sys_msg = SystemMessage(
                content=f"You are a SQL planning assistant. Analyze the user's question and the provided database schema.\n"
                        f"{rbac_instruction}\n"
                        f"Output a concise step-by-step plan for the necessary SQL query. "
                        f"Identify the required tables, JOIN conditions, WHERE filters, and aggregation needs."
            )
            human_msg = HumanMessage(
                content=f"Schema:\n{state.get('schema_context', '')}\n\nQuestion: {state['question']}\n\nPlan:"
            )
            
            response = await llm.ainvoke([sys_msg, human_msg])
            return {"plan": response.content}

    async def generation_agent(self, state: AgentState) -> AgentState:
        with AGENT_LATENCY.labels(agent_name="generation").time():
            AGENT_STEPS.labels(agent_name="generation").inc()
            log.info("Running Generation Agent", retry=state.get("retry_count", 0))
            
            sys_msg = SystemMessage(
                content="You are an expert PostgreSQL developer. Write the raw SQL query based on the plan and schema. "
                        "Output ONLY the SQL code without markdown fences or explanations. "
                        "Use proper table aliases and explicit JOINs. Include a LIMIT 100 clause."
            )
            
            content = (
                f"Schema:\n{state.get('schema_context', '')}\n\n"
                f"Question: {state['question']}\n\n"
                f"Plan:\n{state.get('plan', '')}\n\n"
            )
            
            if state.get("validation_errors"):
                content += f"Previous SQL: {state.get('sql_draft', '')}\nErrors: {state['validation_errors']}\nFix the SQL:\n"
            else:
                content += "SQL:\n"
                
            human_msg = HumanMessage(content=content)
            
            response = await llm.ainvoke([sys_msg, human_msg])
            raw_sql = self._clean_sql(response.content)
            
            return {
                "sql_draft": raw_sql,
                "retry_count": state.get("retry_count", 0) + 1,
                "validation_errors": "" # Reset errors for the next validation check
            }

    async def validation_agent(self, state: AgentState) -> AgentState:
        with AGENT_LATENCY.labels(agent_name="validation").time():
            AGENT_STEPS.labels(agent_name="validation").inc()
            log.info("Running Validation Agent")
            
            draft = state["sql_draft"]
            
            # Use existing validation service
            val_result = self.validation_service.validate(draft)
            
            if not val_result.is_valid:
                AGENT_ERRORS.labels(error_type="sql_validation").inc()
                error_msg = "; ".join(val_result.violations)
                log.warning("Validation failed", error=error_msg)
                return {"validation_errors": error_msg}
                
            return {"validation_errors": ""}

    async def optimization_agent(self, state: AgentState) -> AgentState:
        with AGENT_LATENCY.labels(agent_name="optimization").time():
            AGENT_STEPS.labels(agent_name="optimization").inc()
            log.info("Running Optimization Agent")
            
            sql_draft = state["sql_draft"]
            
            # Step 1: Analyze execution plan
            plan_json = await self.optimization_engine.analyze_plan(self.db, sql_draft)
            
            # Step 2: Detect if slow
            is_slow = self.optimization_engine.is_slow_query(plan_json)
            
            if not is_slow:
                log.info("Query is efficient. Bypassing LLM rewrite.")
                return {
                    "final_sql": sql_draft,
                    "index_suggestions": [],
                    "execution_plan": plan_json
                }
            
            # Step 3: Rewrite and suggest indexes
            result = await self.optimization_engine.optimize(sql_draft, plan_json)
            
            return {
                "final_sql": result.optimized_sql,
                "index_suggestions": result.index_suggestions,
                "execution_plan": plan_json
            }

    def route_validation(self, state: AgentState) -> str:
        if state.get("validation_errors"):
            if state.get("retry_count", 0) >= 3:
                log.error("Max retries reached during SQL validation.")
                return "end"
            return "generation_agent"
        return "optimization_agent"

    async def generate_sql(self, question: str) -> str:
        """Main entry point for the service."""
        initial_state = AgentState(
            question=question,
            schema_context="",
            plan="",
            sql_draft="",
            validation_errors="",
            final_sql="",
            retry_count=0,
            index_suggestions=[],
            execution_plan={}
        )
        
        try:
            # LangGraph's ainvoke executes the compiled StateGraph
            result = await self.graph.ainvoke(initial_state)
            
            # Return final SQL if present, otherwise fallback to the last valid draft or empty string
            if result.get("final_sql"):
                return result["final_sql"]
            elif result.get("sql_draft") and not result.get("validation_errors"):
                return result["sql_draft"]
            else:
                raise LLMServiceError("Failed to generate a valid SQL query.")
                
        except Exception as e:
            AGENT_ERRORS.labels(error_type="graph_execution").inc()
            log.error("Agentic SQL execution failed", error=str(e))
            raise LLMServiceError(f"Failed to execute agentic workflow: {e}")

    async def generate_sql_stream(self, question: str):
        """Stream progress events and finally yield the generated SQL."""
        initial_state = AgentState(
            question=question,
            schema_context="",
            plan="",
            sql_draft="",
            validation_errors="",
            final_sql="",
            retry_count=0,
            index_suggestions=[],
            execution_plan={}
        )
        
        try:
            last_state = initial_state
            async for event in self.graph.astream(initial_state):
                for node_name, state_update in event.items():
                    yield {"type": "progress", "agent": node_name, "status": "completed"}
                    last_state.update(state_update)
            
            final_sql = last_state.get("final_sql") or last_state.get("sql_draft")
            if final_sql:
                yield {
                    "type": "sql", 
                    "sql": final_sql,
                    "optimizations": last_state.get("index_suggestions", []),
                    "execution_plan": last_state.get("execution_plan", {})
                }
            else:
                yield {"type": "error", "message": "Failed to generate a valid SQL query."}
                
        except Exception as e:
            AGENT_ERRORS.labels(error_type="graph_execution").inc()
            log.error("Agentic SQL stream failed", error=str(e))
            yield {"type": "error", "message": f"Failed to execute agentic workflow: {e}"}

    @staticmethod
    def _clean_sql(raw: str) -> str:
        """Strip markdown fences and any non-SQL preamble the model may have added."""
        if raw.startswith("```"):
            lines = raw.split("\n")
            inner = lines[1:-1] if lines[-1].strip() == "```" else lines[1:]
            raw = "\n".join(inner).strip()

        for prefix in ("sql:", "query:", "sql query:"):
            if raw.lower().startswith(prefix):
                raw = raw[len(prefix):].strip()
                break

        return raw.strip()
