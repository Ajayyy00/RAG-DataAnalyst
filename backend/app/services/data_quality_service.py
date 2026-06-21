import json
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd
import structlog
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.schemas.data_quality import AutomatedFix, DataQualityReport, QualityIssue

log = structlog.get_logger(__name__)
settings = get_settings()


class LLMFixResponse(BaseModel):
    fixes: List[AutomatedFix]


class DataQualityService:
    def __init__(self, db_session: AsyncSession):
        self.db = db_session
        self.llm = ChatOpenAI(
            base_url=settings.llm_base_url,
            api_key=settings.llm_api_key or "not-needed",
            model=settings.llm_model,
            temperature=0.1,
            max_tokens=2048,
        ).with_structured_output(LLMFixResponse)

    async def analyze_table(
        self, table_name: str, limit: int = 10000
    ) -> DataQualityReport:
        """Fetch data from Postgres into Pandas and run quality checks."""
        log.info("Starting data quality analysis", table_name=table_name, limit=limit)

        # 1. Fetch data
        # We use a simple select * because we are just doing exploratory DQ.
        # Identifier hardening: must be a bare identifier AND on the clinical
        # allowlist (never users/audit_logs/copilot_*). This eliminates the SQL
        # injection vector — the value is constrained to a fixed, vetted set.
        from app.services.sql_validation_service import ALLOWED_TABLES

        if not table_name.isidentifier() or table_name.lower() not in ALLOWED_TABLES:
            raise ValueError(f"Invalid or non-allowlisted table name: {table_name}")

        _sql = f"SELECT * FROM {table_name} LIMIT :limit"  # nosec B608 (allowlisted)
        result = await self.db.execute(text(_sql), {"limit": limit})

        # Convert to list of dicts
        rows = [dict(row._mapping) for row in result.fetchall()]
        if not rows:
            return DataQualityReport(
                table_name=table_name,
                total_rows_analyzed=0,
                issues=[],
                automated_fixes=[],
            )

        df = pd.DataFrame(rows)
        total_rows = len(df)
        issues: List[QualityIssue] = []

        # 2. Detect missing values
        for col in df.columns:
            missing_count = int(df[col].isnull().sum())
            if missing_count > 0:
                affected_ids = []
                if "id" in df.columns:
                    affected_ids = df[df[col].isnull()]["id"].head(5).tolist()

                issues.append(
                    QualityIssue(
                        type="missing",
                        column=col,
                        description=f"Column '{col}' has {missing_count} missing values ({missing_count/total_rows*100:.1f}%).",
                        count=missing_count,
                        affected_ids=affected_ids,
                    )
                )

        # 3. Detect exact duplicates
        duplicate_count = int(df.duplicated().sum())
        if duplicate_count > 0:
            dup_df = df[df.duplicated(keep=False)]
            affected_ids = []
            if "id" in dup_df.columns:
                affected_ids = dup_df["id"].head(5).tolist()

            issues.append(
                QualityIssue(
                    type="duplicate",
                    description=f"Found {duplicate_count} exactly duplicated rows in the dataset.",
                    count=duplicate_count,
                    affected_ids=affected_ids,
                )
            )

        # 4. Detect numerical outliers (using Z-score heuristic)
        numeric_cols = df.select_dtypes(include=[np.number]).columns
        for col in numeric_cols:
            # Skip ID columns
            if "id" in col.lower():
                continue

            # Use IQR method for outlier detection
            Q1 = df[col].quantile(0.25)
            Q3 = df[col].quantile(0.75)
            IQR = Q3 - Q1
            lower_bound = Q1 - 1.5 * IQR
            upper_bound = Q3 + 1.5 * IQR

            outliers = df[(df[col] < lower_bound) | (df[col] > upper_bound)]
            outlier_count = len(outliers)

            if outlier_count > 0:
                affected_ids = []
                if "id" in outliers.columns:
                    affected_ids = outliers["id"].head(5).tolist()

                issues.append(
                    QualityIssue(
                        type="outlier",
                        column=col,
                        description=f"Column '{col}' has {outlier_count} statistical outliers (outside 1.5 * IQR).",
                        count=outlier_count,
                        affected_ids=affected_ids,
                    )
                )

        # 5. Get AI Suggestions
        automated_fixes = await self._generate_ai_fixes(table_name, issues)

        return DataQualityReport(
            table_name=table_name,
            total_rows_analyzed=total_rows,
            issues=issues,
            automated_fixes=automated_fixes,
        )

    async def _generate_ai_fixes(
        self, table_name: str, issues: List[QualityIssue]
    ) -> List[AutomatedFix]:
        if not issues:
            return []

        sys_msg = SystemMessage(
            content="You are an expert Data Engineer and PostgreSQL DBA.\n"
            "Your job is to analyze the provided list of Data Quality issues for a table.\n"
            "For each major issue, generate an `AutomatedFix` containing a raw SQL script (UPDATE or DELETE) to resolve the issue.\n"
            "For missing values, suggest an UPDATE to set a reasonable default or NULL where appropriate.\n"
            "For outliers, suggest capping them or flagging them.\n"
            "For duplicates, suggest deleting the duplicate keeping the max ID (if applicable).\n"
            "Output valid PostgreSQL."
        )

        issues_data = [i.model_dump() for i in issues]
        human_msg = HumanMessage(
            content=f"Table: {table_name}\nIssues Detected:\n{json.dumps(issues_data, indent=2, default=str)}"
        )

        try:
            log.info("Generating AI data quality fixes")
            result = await self.llm.ainvoke([sys_msg, human_msg])
            return result.fixes
        except Exception as e:
            log.error("Failed to generate AI data quality fixes", error=str(e))
            return []
