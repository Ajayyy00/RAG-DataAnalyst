"""
Agentic SQL Service using LangGraph.
Implements a multi-agent workflow for generating SQL:
1. Schema Understanding
2. Query Planning
3. SQL Generation
4. SQL Validation
5. Query Optimization
"""

import operator
from typing import Annotated, Any, Dict, List, Optional, TypedDict

import structlog
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from langgraph.graph import END, StateGraph
from prometheus_client import Counter, Histogram

from app.config import get_settings
from app.core.exceptions import LLMServiceError
from app.services.rag_service import RAGService
from app.services.sql_validation_service import ALLOWED_TABLES, SQLValidationService

# Authoritative schema guardrails injected into the planning + generation prompts
# so the model targets REAL tables/columns even when RAG context is thin/empty
# (otherwise it invents identifiers that fail the table allow-list validator).
SCHEMA_GUARDRAILS = (
    "## Database (PostgreSQL) — use ONLY these tables and columns\n"
    "patients(id, mrn, first_name, last_name, date_of_birth, gender, race, ethnicity, zip_code, insurance_type)\n"
    "encounters(id, patient_id, provider_id, department_id, encounter_type, admit_date, discharge_date, drg_code, total_charge, total_payment)\n"
    "diagnoses(id, encounter_id, patient_id, icd10_code, icd10_desc, diagnosis_type, diagnosis_date, is_chronic)\n"
    "procedures(id, encounter_id, patient_id, cpt_code, cpt_desc, procedure_date, provider_id, quantity, charge_amount)\n"
    "medications(id, encounter_id, patient_id, drug_name, ndc_code, rxnorm_code, dose, route, frequency, start_date, end_date, prescriber_id)\n"
    "lab_results(id, encounter_id, patient_id, loinc_code, test_name, result_value, numeric_value, unit, abnormal_flag, result_date)\n"
    "vital_signs(id, encounter_id, patient_id, recorded_at, systolic_bp, diastolic_bp, heart_rate, temperature_f, spo2_pct)\n"
    "claims(id, encounter_id, patient_id, claim_type, payer_name, billed_amount, allowed_amount, paid_amount, claim_status, submission_date)\n"
    "readmissions(id, index_encounter_id, readmit_encounter_id, patient_id, days_to_readmit, readmit_reason)\n"
    "providers(id, npi, first_name, last_name, specialty, department_id)\n"
    "departments(id, name, dept_type, facility_id)\n"
    "facilities(id, name, city, state, facility_type)\n"
    f"\nAllowed tables (NEVER reference any other table): {', '.join(sorted(ALLOWED_TABLES))}.\n"
    "## Hard rules\n"
    "- Output ONLY a single read-only SELECT (or WITH ... SELECT). No DML/DDL, no semicolon-separated statements.\n"
    "- Always include a LIMIT (default 100). Use explicit JOIN ... ON. Use ILIKE for text matching.\n"
    "- Use DATE_TRUNC for time grouping; CURRENT_DATE - INTERVAL 'N months' for recent windows.\n"
    "- 'this month' => DATE_TRUNC('month', <date_col>) = DATE_TRUNC('month', CURRENT_DATE).\n"
)

log = structlog.get_logger(__name__)
settings = get_settings()

# Prometheus Metrics
AGENT_STEPS = Counter(
    "agentic_sql_steps_total", "Total number of agent steps executed", ["agent_name"]
)
AGENT_ERRORS = Counter(
    "agentic_sql_errors_total",
    "Total number of errors encountered during agentic SQL generation",
    ["error_type"],
)
AGENT_LATENCY = Histogram(
    "agentic_sql_step_latency_seconds",
    "Latency of individual agent steps",
    ["agent_name"],
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
                "end": END,
            },
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

                # Fetch schema from RAG based on the question.
                # NOTE: retrieve_schema_context is async — it MUST be awaited,
                # otherwise a coroutine object is fed into the prompt and the
                # model receives no schema at all.
                schema_context = await self.rag_service.retrieve_schema_context(
                    state["question"], top_k=5, user_role=role
                )
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
                f"{SCHEMA_GUARDRAILS}\n"
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
                content="You are an expert PostgreSQL developer. Write the raw SQL query based on the plan and schema.\n"
                f"{SCHEMA_GUARDRAILS}\n"
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
                "validation_errors": "",  # Reset errors for the next validation check
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
                    "execution_plan": plan_json,
                }

            # Step 3: Rewrite and suggest indexes
            result = await self.optimization_engine.optimize(sql_draft, plan_json)
            if isinstance(result, dict):
                optimized_sql = result.get("optimized_sql", sql_draft)
                index_suggestions = result.get("index_suggestions", [])
            else:
                optimized_sql = getattr(result, "optimized_sql", sql_draft)
                index_suggestions = getattr(result, "index_suggestions", [])

            # CRITICAL: the optimizer is an LLM and can introduce unsafe SQL
            # (unauthorized tables, removed LIMIT, etc.). Re-validate its output
            # and fall back to the already-validated draft if the rewrite fails.
            opt_validation = self.validation_service.validate(optimized_sql)
            if opt_validation.is_valid:
                final_sql = opt_validation.normalized_sql
            else:
                log.warning(
                    "Optimizer rewrite failed validation — using validated draft",
                    violations=opt_validation.violations,
                )
                AGENT_ERRORS.labels(error_type="optimizer_validation").inc()
                final_sql = sql_draft
                index_suggestions = []

            return {
                "final_sql": final_sql,
                "index_suggestions": index_suggestions,
                "execution_plan": plan_json,
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
            execution_plan={},
        )

        try:
            # LangGraph's ainvoke executes the compiled StateGraph
            result = await self.graph.ainvoke(initial_state)

            # Only `final_sql` (set by the optimization_agent on the validated
            # path) is safe to return. Never return a raw draft.
            if result.get("final_sql"):
                return result["final_sql"]
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
            execution_plan={},
        )

        try:
            last_state = initial_state
            async for event in self.graph.astream(initial_state):
                for node_name, state_update in event.items():
                    yield {
                        "type": "progress",
                        "agent": node_name,
                        "status": "completed",
                    }
                    last_state.update(state_update)

            # SECURITY: only emit `final_sql`, which is set exclusively by the
            # optimization_agent and is therefore guaranteed to have passed
            # validation. NEVER fall back to `sql_draft` — after 3 failed
            # validation retries the draft is invalid/unsafe and must not run.
            final_sql = last_state.get("final_sql")
            if final_sql:
                yield {
                    "type": "sql",
                    "sql": final_sql,
                    "optimizations": last_state.get("index_suggestions", []),
                    "execution_plan": last_state.get("execution_plan", {}),
                }
            else:
                reason = last_state.get("validation_errors") or "no SQL produced"
                log.warning(
                    "Agentic generation exhausted retries without valid SQL",
                    last_errors=reason,
                    last_draft=(last_state.get("sql_draft") or "")[:300],
                )
                yield {
                    "type": "error",
                    "message": (
                        "Could not generate a SQL query that passed safety "
                        f"validation. Last issue: {reason}"
                    ),
                }

        except Exception as e:
            AGENT_ERRORS.labels(error_type="graph_execution").inc()
            log.error("Agentic SQL stream failed", error=str(e))
            yield {
                "type": "error",
                "message": f"Failed to execute agentic workflow: {e}",
            }

    @staticmethod
    def _clean_sql(raw: str) -> str:
        """Strip markdown fences and any non-SQL preamble the model may have added."""
        if raw.startswith("```"):
            lines = raw.split("\n")
            inner = lines[1:-1] if lines[-1].strip() == "```" else lines[1:]
            raw = "\n".join(inner).strip()

        for prefix in ("sql:", "query:", "sql query:"):
            if raw.lower().startswith(prefix):
                raw = raw[len(prefix) :].strip()
                break

        return raw.strip()
