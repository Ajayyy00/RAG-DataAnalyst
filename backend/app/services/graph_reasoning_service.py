"""
Graph Reasoning Service
Translates natural language into Cypher, executes against Neo4j,
and uses LLM to reason over the graph results.
"""
import structlog
from typing import Any, Dict

from langchain_core.messages import SystemMessage, HumanMessage
from langchain_openai import ChatOpenAI

from app.config import get_settings
from app.services.neo4j_driver import run_query

log = structlog.get_logger(__name__)
settings = get_settings()

# Static Neo4j schema description fed to the LLM for Cypher generation
NEO4J_SCHEMA = """
Node Labels and Properties:
  - Patient {id, first_name, last_name, dob, gender}
  - Disease {name}
  - Symptom {name}
  - Medication {name}
  - LabTest {name}

Relationship Types:
  - (Patient)-[:HAS_DISEASE]->(Disease)
  - (Patient)-[:PRESCRIBED]->(Medication)
  - (Patient)-[:EXHIBITS]->(Symptom)
  - (Patient)-[:TOOK_TEST]->(LabTest)
  - (Disease)-[:HAS_SYMPTOM]->(Symptom)
  - (Medication)-[:TREATS]->(Disease)
"""


class GraphReasoningService:
    def __init__(self):
        self.cypher_llm = ChatOpenAI(
            base_url=settings.llm_base_url,
            api_key=settings.llm_api_key or "not-needed",
            model=settings.llm_model,
            temperature=0.0,
        )
        self.reasoning_llm = ChatOpenAI(
            base_url=settings.llm_base_url,
            api_key=settings.llm_api_key or "not-needed",
            model=settings.llm_model,
            temperature=0.3,
        )

    async def _generate_cypher(self, question: str, previous_error: str = None, previous_cypher: str = None) -> str:
        """Step 1: Translate NL question → Cypher query, with optional error feedback."""
        prompt = (
            f"You are an expert Neo4j Cypher query writer.\n"
            f"Given this graph schema:\n{NEO4J_SCHEMA}\n"
            "Write ONLY a valid Cypher query that answers the user's question.\n"
            "Do NOT include explanations or markdown fences.\n"
            "CRITICAL RULES FOR RETURNING GRAPH DATA:\n"
            "1. You MUST return full nodes and relationships, not just properties.\n"
            "2. You MUST bind relationships to a variable (e.g., `r`) to return them.\n"
            "EXAMPLE DO: MATCH (p:Patient)-[r:HAS_DISEASE]->(d:Disease {name: 'Hypertension'}) RETURN p, r, d LIMIT 50\n"
            "EXAMPLE DON'T: MATCH (p:Patient)-[:HAS_DISEASE]->(d:Disease) RETURN p, d, :HAS_DISEASE\n"
        )
        
        if previous_error:
            prompt += f"\n\nWARNING: Your previous query `{previous_cypher}` failed with error:\n{previous_error}\n"
            prompt += "If the error says 'Invalid input... expected NOT', it means you tried to return a raw relationship like `:HAS_DISEASE`. You MUST bind it to a variable like `[r:HAS_DISEASE]` and return `r`. Fix the query!"

        response = await self.cypher_llm.ainvoke([
            SystemMessage(content=prompt),
            HumanMessage(content=f"Question: {question}"),
        ])
        cypher = response.content.strip()
        if cypher.startswith("```"):
            cypher = "\n".join(cypher.split("\n")[1:-1])
        return cypher

    async def _reason_over_results(self, question: str, cypher: str, graph_data: list) -> str:
        """Step 2: LLM reasons over raw graph results to produce a human answer."""
        if not graph_data:
            return "No relevant graph data was found to answer your question."

        response = await self.reasoning_llm.ainvoke([
            SystemMessage(content=(
                "You are a clinical AI assistant. You are given a user's question "
                "and the raw results from a healthcare knowledge graph query. "
                "Provide a clear, accurate, and concise clinical answer using ONLY the provided data."
            )),
            HumanMessage(content=(
                f"Question: {question}\n\n"
                f"Cypher Query Used: {cypher}\n\n"
                f"Graph Results (JSON): {graph_data[:50]}\n\n"
                "Answer:"
            )),
        ])
        return response.content

    async def _is_neo4j_available(self) -> bool:
        """Quick ping to check if Neo4j is reachable."""
        try:
            result = await run_query("RETURN 1 AS ok")
            return bool(result)
        except Exception:
            return False

    async def query(self, question: str) -> Dict[str, Any]:
        """Full pipeline: NL → Cypher → Execute → LLM Reason → Answer."""
        log.info("Graph reasoning query received", question=question)

        if not await self._is_neo4j_available():
            log.warning("Neo4j is unavailable — returning offline demo response")
            return {
                "question": question,
                "cypher": "-- Neo4j is not running. Start Neo4j to enable live graph queries.",
                "graph_data": [],
                "answer": (
                    "Neo4j is currently offline. The knowledge graph cannot be queried. "
                    "Please start your Neo4j instance (bolt://localhost:7687) and run a "
                    "graph sync via POST /api/v1/kg/sync to populate the graph."
                ),
                "neo4j_available": False,
            }

        # Cypher Generation and Execution with Retry Logic
        max_retries = 2
        cypher = ""
        graph_data = []
        error_msg = None
        
        for attempt in range(max_retries):
            cypher = await self._generate_cypher(question, previous_error=error_msg, previous_cypher=cypher)
            log.info(f"Generated Cypher (Attempt {attempt+1})", cypher=cypher)
            
            try:
                graph_data = await run_query(cypher)
                error_msg = None # Success!
                break
            except Exception as e:
                error_msg = str(e)
                log.warning("Cypher execution failed, retrying...", error=error_msg, cypher=cypher)

        if error_msg:
            log.error("All Cypher execution attempts failed", error=error_msg, cypher=cypher)
            return {
                "question": question,
                "cypher": cypher,
                "graph_data": [],
                "answer": f"Graph query execution failed: {error_msg}",
                "error": error_msg,
                "neo4j_available": True,
            }

        # Step 3: LLM reasons over results
        answer = await self._reason_over_results(question, cypher, graph_data)

        return {
            "question": question,
            "cypher": cypher,
            "graph_data": graph_data,
            "answer": answer,
            "neo4j_available": True,
        }
