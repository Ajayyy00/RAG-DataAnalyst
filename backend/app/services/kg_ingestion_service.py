"""
Knowledge Graph Ingestion Service
Syncs data from PostgreSQL into Neo4j and dynamically extracts
medical knowledge (Disease→Symptom, Medication→Disease) via LLM.
"""
import structlog
import asyncio
from typing import List, Dict, Any
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from langchain_core.messages import SystemMessage, HumanMessage
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field

from app.config import get_settings
from app.services.neo4j_driver import run_query

log = structlog.get_logger(__name__)
settings = get_settings()


# ── LLM-extracted knowledge schemas ──────────────────────────

class DiseaseKnowledge(BaseModel):
    symptoms: List[str] = Field(..., description="Common symptoms of this disease, e.g. ['fever', 'cough']")
    related_medications: List[str] = Field(..., description="Common first-line medications used to treat this disease")


class MedicationKnowledge(BaseModel):
    treats_diseases: List[str] = Field(..., description="Diseases this medication is primarily used to treat")
    common_side_effects: List[str] = Field(..., description="Common side effects of this medication")


# ── Constraint bootstrap ──────────────────────────────────────

CREATE_CONSTRAINTS = [
    "CREATE CONSTRAINT patient_id IF NOT EXISTS FOR (p:Patient) REQUIRE p.id IS UNIQUE",
    "CREATE CONSTRAINT disease_name IF NOT EXISTS FOR (d:Disease) REQUIRE d.name IS UNIQUE",
    "CREATE CONSTRAINT symptom_name IF NOT EXISTS FOR (s:Symptom) REQUIRE s.name IS UNIQUE",
    "CREATE CONSTRAINT medication_name IF NOT EXISTS FOR (m:Medication) REQUIRE m.name IS UNIQUE",
    "CREATE CONSTRAINT labtest_name IF NOT EXISTS FOR (l:LabTest) REQUIRE l.name IS UNIQUE",
]


class KGIngestionService:
    def __init__(self):
        self.llm_disease = ChatOpenAI(
            base_url=settings.llm_base_url,
            api_key=settings.llm_api_key or "not-needed",
            model=settings.llm_model,
            temperature=0.1,
        ).with_structured_output(DiseaseKnowledge, method="json_mode")

        self.llm_medication = ChatOpenAI(
            base_url=settings.llm_base_url,
            api_key=settings.llm_api_key or "not-needed",
            model=settings.llm_model,
            temperature=0.1,
        ).with_structured_output(MedicationKnowledge, method="json_mode")

    # ── Schema bootstrap ──────────────────────────────────────

    async def bootstrap_constraints(self):
        for cypher in CREATE_CONSTRAINTS:
            try:
                await run_query(cypher)
            except Exception as e:
                log.warning("Constraint already exists or failed", error=str(e))
        log.info("Neo4j constraints bootstrapped")

    # ── LLM Knowledge Extraction ──────────────────────────────

    async def extract_disease_knowledge(self, disease_name: str) -> DiseaseKnowledge:
        try:
            schema_instructions = (
                "Respond in valid JSON matching exactly this schema:\n"
                "{\n"
                "  \"symptoms\": [\"list of common symptoms\"],\n"
                "  \"related_medications\": [\"list of common medications\"]\n"
                "}"
            )
            result = await self.llm_disease.ainvoke([
                SystemMessage(content=f"You are a medical expert. Extract clinical knowledge about the given disease. {schema_instructions}"),
                HumanMessage(content=f"Disease: {disease_name}"),
            ])
            return result
        except Exception as e:
            log.warning("Disease knowledge extraction failed", disease=disease_name, error=str(e))
            return DiseaseKnowledge(symptoms=[], related_medications=[])

    async def extract_medication_knowledge(self, medication_name: str) -> MedicationKnowledge:
        try:
            schema_instructions = (
                "Respond in valid JSON matching exactly this schema:\n"
                "{\n"
                "  \"treats_diseases\": [\"list of diseases treated\"],\n"
                "  \"common_side_effects\": [\"list of side effects\"]\n"
                "}"
            )
            result = await self.llm_medication.ainvoke([
                SystemMessage(content=f"You are a clinical pharmacist. Extract knowledge about the given medication. {schema_instructions}"),
                HumanMessage(content=f"Medication: {medication_name}"),
            ])
            return result
        except Exception as e:
            log.warning("Medication knowledge extraction failed", medication=medication_name, error=str(e))
            return MedicationKnowledge(treats_diseases=[], common_side_effects=[])

    # ── ETL helpers ───────────────────────────────────────────

    async def _sync_patients(self, db: AsyncSession):
        rows = await db.execute(text(
            "SELECT id::text, first_name, last_name, date_of_birth, gender FROM patients LIMIT 5000"
        ))
        patients = rows.mappings().all()
        for p in patients:
            await run_query(
                """MERGE (pt:Patient {id: $id})
                   SET pt.first_name = $first_name,
                       pt.last_name  = $last_name,
                       pt.dob        = $dob,
                       pt.gender     = $gender""",
                {"id": p["id"], "first_name": p["first_name"],
                 "last_name": p["last_name"], "dob": str(p["date_of_birth"]),
                 "gender": p["gender"]},
            )
        log.info("Synced patients to Neo4j", count=len(patients))

    async def _sync_diagnoses(self, db: AsyncSession):
        rows = await db.execute(text(
            """SELECT d.patient_id::text, d.icd10_desc as diagnosis_name
               FROM diagnoses d WHERE d.icd10_desc IS NOT NULL LIMIT 10000"""
        ))
        diagnoses = rows.mappings().all()
        seen_diseases: Dict[str, bool] = {}

        for row in diagnoses:
            disease_name = row["diagnosis_name"]

            # MERGE disease node
            await run_query(
                "MERGE (d:Disease {name: $name})",
                {"name": disease_name}
            )

            # Patient → Disease relationship
            await run_query(
                """MATCH (pt:Patient {id: $patient_id})
                   MATCH (d:Disease {name: $disease_name})
                   MERGE (pt)-[:HAS_DISEASE]->(d)""",
                {"patient_id": row["patient_id"], "disease_name": disease_name},
            )

            # 3. Extract LLM Knowledge
            if disease_name not in seen_diseases:
                seen_diseases[disease_name] = True
                
                # Protect against Groq 30 RPM rate limits by only taking first 10 unique diseases
                if len(seen_diseases) <= 10:
                    knowledge = await self.extract_disease_knowledge(disease_name)
                    await asyncio.sleep(2.1)
                else:
                    knowledge = DiseaseKnowledge(symptoms=[], related_medications=[])

                # 4. Link Symptoms in knowledge.symptoms:
                for symptom in knowledge.symptoms:
                    await run_query(
                        """MERGE (s:Symptom {name: $name})
                           WITH s
                           MATCH (d:Disease {name: $disease_name})
                           MERGE (d)-[:HAS_SYMPTOM]->(s)""",
                        {"name": symptom, "disease_name": disease_name},
                    )

        log.info("Synced diagnoses to Neo4j", count=len(diagnoses))

    async def _sync_medications(self, db: AsyncSession):
        rows = await db.execute(text(
            """SELECT m.patient_id::text, m.drug_name as medication_name
               FROM medications m WHERE m.drug_name IS NOT NULL LIMIT 10000"""
        ))
        medications = rows.mappings().all()
        seen_medications: Dict[str, bool] = {}

        for row in medications:
            med_name = row["medication_name"]

            await run_query("MERGE (m:Medication {name: $name})", {"name": med_name})

            await run_query(
                """MATCH (pt:Patient {id: $patient_id})
                   MATCH (m:Medication {name: $med_name})
                   MERGE (pt)-[:PRESCRIBED]->(m)""",
                {"patient_id": row["patient_id"], "med_name": med_name},
            )

            # 3. Extract LLM Knowledge
            if med_name not in seen_medications:
                seen_medications[med_name] = True
                
                if len(seen_medications) <= 10:
                    knowledge = await self.extract_medication_knowledge(med_name)
                    await asyncio.sleep(2.1)
                else:
                    knowledge = MedicationKnowledge(treats_diseases=[], common_side_effects=[])

                # 4. Link Treated Diseases in knowledge.treats_diseases:
                for disease in knowledge.treats_diseases:
                    await run_query(
                        """MERGE (d:Disease {name: $disease})
                           WITH d
                           MATCH (m:Medication {name: $med_name})
                           MERGE (m)-[:TREATS]->(d)""",
                        {"disease": disease, "med_name": med_name},
                    )

        log.info("Synced medications to Neo4j", count=len(medications))

    async def _sync_symptoms(self, db: AsyncSession):
        """Sync patient-reported symptoms via vital signs / observations as a proxy."""
        # Link patients exhibiting symptoms already extracted by LLM from their diseases
        # by traversing HAS_DISEASE → HAS_SYMPTOM
        await run_query(
            """MATCH (pt:Patient)-[:HAS_DISEASE]->(d:Disease)-[:HAS_SYMPTOM]->(s:Symptom)
               MERGE (pt)-[:EXHIBITS]->(s)"""
        )
        log.info("Synced patient symptom relationships via disease graph")

    async def _sync_lab_tests(self, db: AsyncSession):
        rows = await db.execute(text(
            """SELECT lr.patient_id::text, lr.test_name
               FROM lab_results lr LIMIT 10000"""
        ))
        lab_tests = rows.mappings().all()

        for row in lab_tests:
            await run_query("MERGE (lt:LabTest {name: $name})", {"name": row["test_name"]})
            await run_query(
                """MATCH (pt:Patient {id: $patient_id})
                   MATCH (lt:LabTest {name: $test_name})
                   MERGE (pt)-[:TOOK_TEST]->(lt)""",
                {"patient_id": row["patient_id"], "test_name": row["test_name"]},
            )

        log.info("Synced lab tests to Neo4j", count=len(lab_tests))

    # ── Main entry point ──────────────────────────────────────

    async def sync(self, db: AsyncSession) -> Dict[str, Any]:
        log.info("Starting Knowledge Graph sync")
        await self.bootstrap_constraints()
        await self._sync_patients(db)
        await self._sync_diagnoses(db)
        await self._sync_medications(db)
        await self._sync_symptoms(db)
        await self._sync_lab_tests(db)
        log.info("Knowledge Graph sync complete")
        return {"status": "completed"}
