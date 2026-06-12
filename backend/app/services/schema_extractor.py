"""
schema_extractor.py
====================
Deep PostgreSQL introspection — produces rich, LLM-ready schema metadata.

Extracts per-table:
  • Column names, types, nullability, defaults
  • Primary keys, foreign keys (with referenced table/column)
  • Approximate row counts (pg_stat_user_tables — no sequential scan)
  • Table-level and column-level comments (pg_description)
  • Index information (for hinting the LLM about filtering opportunities)

Three output representations are generated for each table:
  1. ``to_description()``  — Natural language sentence (used as embedding document)
  2. ``to_ddl()``          — CREATE TABLE DDL fragment (included in LLM prompt)
  3. ``to_relationships()``— FK graph text (used for JOIN hint context)
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Optional

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

log = structlog.get_logger(__name__)


# ── Domain glossary ────────────────────────────────────────────────────────────
# Enriches column names with clinical meaning for better embedding quality.
CLINICAL_GLOSSARY: dict[str, str] = {
    "icd10_code":       "ICD-10-CM diagnostic code",
    "icd9_code":        "ICD-9-CM legacy diagnostic code",
    "cpt_code":         "CPT procedure billing code",
    "ndc_code":         "National Drug Code (medication identifier)",
    "drg_code":         "Diagnosis Related Group for billing",
    "hcc_code":         "Hierarchical Condition Category risk score",
    "snomed_code":      "SNOMED CT clinical terminology code",
    "loinc_code":       "LOINC lab test identifier",
    "admit_date":       "hospital admission date",
    "discharge_date":   "hospital discharge date",
    "dob":              "patient date of birth",
    "date_of_birth":    "patient date of birth",
    "los":              "length of stay in days",
    "readmitted":       "flag indicating 30-day readmission",
    "hba1c":            "glycated haemoglobin (diabetes control marker)",
    "bmi":              "body mass index",
    "systolic_bp":      "systolic blood pressure (mmHg)",
    "diastolic_bp":     "diastolic blood pressure (mmHg)",
    "glucose":          "blood glucose level (mg/dL)",
    "creatinine":       "serum creatinine (kidney function marker)",
    "egfr":             "estimated glomerular filtration rate (kidney function)",
    "troponin":         "cardiac troponin (heart attack marker)",
    "wbc":              "white blood cell count",
    "hgb":              "haemoglobin level",
    "encounter_type":   "type of clinical encounter (inpatient/outpatient/ED)",
    "discharge_disposition": "patient destination after discharge",
    "payer_type":       "insurance/payer category",
    "claim_status":     "billing claim processing status",
    "diagnosis_rank":   "primary vs secondary diagnosis ordering",
}


# ── Data classes ───────────────────────────────────────────────────────────────

@dataclass
class ColumnInfo:
    name: str
    data_type: str
    nullable: bool
    default: Optional[str]
    is_primary_key: bool
    is_foreign_key: bool
    fk_table: Optional[str]
    fk_column: Optional[str]
    comment: Optional[str]
    ordinal: int

    @property
    def clinical_meaning(self) -> Optional[str]:
        return CLINICAL_GLOSSARY.get(self.name.lower())

    @property
    def effective_comment(self) -> Optional[str]:
        return self.comment or self.clinical_meaning

    def to_ddl_line(self) -> str:
        """Single DDL column definition line."""
        type_str = self.data_type.upper()
        parts: list[str] = [f"  {self.name} {type_str}"]
        if self.is_primary_key:
            parts.append("PRIMARY KEY")
        if not self.nullable:
            parts.append("NOT NULL")
        if self.default and "nextval" not in (self.default or ""):
            parts.append(f"DEFAULT {self.default}")
        if self.is_foreign_key and self.fk_table:
            parts.append(f"REFERENCES {self.fk_table}({self.fk_column})")
        if self.effective_comment:
            parts.append(f"-- {self.effective_comment}")
        return " ".join(parts)

    def to_text(self) -> str:
        """Natural language column description for embedding."""
        desc = f"{self.name} ({self.data_type})"
        if self.effective_comment:
            desc += f": {self.effective_comment}"
        if self.is_primary_key:
            desc += " [primary key]"
        if self.is_foreign_key and self.fk_table:
            desc += f" [foreign key → {self.fk_table}.{self.fk_column}]"
        if not self.nullable:
            desc += " [required]"
        return desc


@dataclass
class TableInfo:
    name: str
    schema_name: str
    comment: Optional[str]
    row_count: int
    columns: list[ColumnInfo]
    indexes: list[str] = field(default_factory=list)

    # Populated post-extraction
    related_tables: list[str] = field(default_factory=list)

    @property
    def primary_keys(self) -> list[str]:
        return [c.name for c in self.columns if c.is_primary_key]

    @property
    def foreign_keys(self) -> list[ColumnInfo]:
        return [c for c in self.columns if c.is_foreign_key]

    def schema_hash(self) -> str:
        """SHA-256 fingerprint — used to skip re-indexing unchanged tables."""
        payload = json.dumps(
            {"name": self.name, "cols": [(c.name, c.data_type) for c in self.columns]},
            sort_keys=True,
        )
        return hashlib.sha256(payload.encode()).hexdigest()[:16]

    # ── Three text representations ─────────────────────────────────────────────

    def to_description(self) -> str:
        """
        Natural-language embedding document.
        Dense enough to match diverse paraphrases of the same clinical concept.
        """
        col_text = "; ".join(c.to_text() for c in self.columns)
        fk_text = ""
        if self.foreign_keys:
            fk_text = " Related to: " + ", ".join(
                f"{c.fk_table}" for c in self.foreign_keys if c.fk_table
            ) + "."

        purpose = self.comment or self._infer_purpose()
        return (
            f"Table {self.name}: {purpose} "
            f"Contains columns: {col_text}.{fk_text} "
            f"Approximately {self.row_count:,} records."
        )

    def to_ddl(self) -> str:
        """
        CREATE TABLE DDL — injected verbatim into the LLM system prompt.
        Includes column-level comments inline for clinical context.
        """
        lines: list[str] = []
        if self.comment:
            lines.append(f"-- {self.comment}")
        if self.row_count > 0:
            lines.append(f"-- Approximate row count: {self.row_count:,}")
        lines.append(f"CREATE TABLE {self.name} (")
        lines.extend(c.to_ddl_line() for c in self.columns)
        lines.append(");")

        if self.indexes:
            for idx in self.indexes:
                lines.append(f"-- Index: {idx}")

        return "\n".join(lines)

    def to_schema_section(self) -> str:
        """
        Markdown-formatted schema section for the LLM prompt.
        More readable than raw DDL for instruction-tuned models.
        """
        lines = [f"### {self.name}"]
        if self.comment:
            lines.append(f"> {self.comment}")
        if self.row_count > 0:
            lines.append(f"> ~{self.row_count:,} rows")
        lines.append("")
        for col in self.columns:
            tags: list[str] = []
            if col.is_primary_key:       tags.append("PK")
            if col.is_foreign_key:       tags.append(f"FK→{col.fk_table}")
            if not col.nullable:         tags.append("NOT NULL")
            tag_str = f" `[{', '.join(tags)}]`" if tags else ""
            meaning = f" — {col.effective_comment}" if col.effective_comment else ""
            lines.append(f"- `{col.name}` {col.data_type}{tag_str}{meaning}")
        return "\n".join(lines)

    def to_relationship_text(self) -> str:
        """FK relationship sentences — indexed separately for JOIN retrieval."""
        if not self.foreign_keys:
            return ""
        rels = [
            f"{self.name}.{c.name} references {c.fk_table}.{c.fk_column}"
            for c in self.foreign_keys
            if c.fk_table
        ]
        return f"Table {self.name} joins to: " + "; ".join(rels) + "."

    def _infer_purpose(self) -> str:
        """Heuristic table purpose from name when no comment exists."""
        mapping = {
            "patients":    "stores demographic information for all registered patients",
            "encounters":  "records individual clinical encounters (inpatient, outpatient, ED visits)",
            "diagnoses":   "stores ICD-10 diagnostic codes assigned during encounters",
            "procedures":  "records CPT/surgical procedures performed during encounters",
            "medications": "tracks prescribed and administered medications per encounter",
            "lab_results": "stores laboratory test results (LOINC-coded) per encounter",
            "vital_signs": "records clinical measurements (BP, HR, weight, temperature, SpO2)",
            "claims":      "billing claims submitted to payers per encounter",
            "readmissions":"tracks 30-day hospital readmission events",
            "providers":   "directory of clinical providers (physicians, nurses, specialists)",
            "departments": "hospital departments and care units",
            "facilities":  "hospital sites and facility metadata",
        }
        return mapping.get(self.name, f"stores {self.name.replace('_', ' ')} data")


# ── Extractor ──────────────────────────────────────────────────────────────────

class SchemaExtractor:
    """
    Async PostgreSQL schema extractor.

    Uses information_schema + pg_catalog for maximum compatibility.
    All queries are parameterised; no string formatting for safety.
    """

    SCHEMA = "public"

    # Tables in the allowed query allowlist (must match sql_validation_service.py)
    TARGET_TABLES: list[str] = [
        "patients", "encounters", "diagnoses", "procedures",
        "medications", "lab_results", "vital_signs", "claims",
        "readmissions", "providers", "departments", "facilities",
        "insurance_plans", "allergies", "immunizations",
        "care_plans", "observations",
    ]

    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def extract_all(self) -> list[TableInfo]:
        """Extract full schema metadata for all target tables."""
        tables: list[TableInfo] = []

        row_counts = await self._fetch_row_counts()
        pk_map     = await self._fetch_primary_keys()
        fk_map     = await self._fetch_foreign_keys()
        idx_map    = await self._fetch_indexes()
        tbl_comments = await self._fetch_table_comments()

        for table_name in self.TARGET_TABLES:
            columns = await self._fetch_columns(table_name, pk_map, fk_map)
            if not columns:
                log.debug("Table not found in schema — skipping", table=table_name)
                continue

            table = TableInfo(
                name=table_name,
                schema_name=self.SCHEMA,
                comment=tbl_comments.get(table_name),
                row_count=row_counts.get(table_name, 0),
                columns=columns,
                indexes=idx_map.get(table_name, []),
            )
            tables.append(table)

        # Populate related_tables (both FK directions)
        self._annotate_relationships(tables)

        log.info("Schema extracted", table_count=len(tables))
        return tables

    # ── Private helpers ────────────────────────────────────────────────────────

    async def _fetch_row_counts(self) -> dict[str, int]:
        """Fast approximate row counts from pg_stat — no sequential scans."""
        result = await self._db.execute(text("""
            SELECT relname AS table_name, reltuples::BIGINT AS row_count
            FROM pg_class c
            JOIN pg_namespace n ON n.oid = c.relnamespace
            WHERE n.nspname = 'public'
              AND c.relkind = 'r'
              AND reltuples > 0
        """))
        return {row.table_name: max(0, int(row.row_count)) for row in result.fetchall()}

    async def _fetch_primary_keys(self) -> dict[str, set[str]]:
        """Return {table_name: {pk_col1, pk_col2, ...}}."""
        result = await self._db.execute(text("""
            SELECT
                tc.table_name,
                kcu.column_name
            FROM information_schema.table_constraints tc
            JOIN information_schema.key_column_usage kcu
                ON tc.constraint_name = kcu.constraint_name
               AND tc.table_schema    = kcu.table_schema
            WHERE tc.constraint_type = 'PRIMARY KEY'
              AND tc.table_schema    = 'public'
        """))
        pk_map: dict[str, set[str]] = {}
        for row in result.fetchall():
            pk_map.setdefault(row.table_name, set()).add(row.column_name)
        return pk_map

    async def _fetch_foreign_keys(self) -> dict[str, list[dict]]:
        """Return {table_name: [{column, fk_table, fk_column}, ...]}."""
        result = await self._db.execute(text("""
            SELECT
                kcu.table_name,
                kcu.column_name,
                ccu.table_name  AS fk_table,
                ccu.column_name AS fk_column
            FROM information_schema.table_constraints tc
            JOIN information_schema.key_column_usage kcu
                ON tc.constraint_name = kcu.constraint_name
               AND tc.table_schema    = kcu.table_schema
            JOIN information_schema.constraint_column_usage ccu
                ON ccu.constraint_name = tc.constraint_name
               AND ccu.table_schema    = tc.table_schema
            WHERE tc.constraint_type = 'FOREIGN KEY'
              AND tc.table_schema    = 'public'
        """))
        fk_map: dict[str, list[dict]] = {}
        for row in result.fetchall():
            fk_map.setdefault(row.table_name, []).append({
                "column":    row.column_name,
                "fk_table":  row.fk_table,
                "fk_column": row.fk_column,
            })
        return fk_map

    async def _fetch_indexes(self) -> dict[str, list[str]]:
        """Return {table_name: [index_definition, ...]} for non-PK indexes."""
        result = await self._db.execute(text("""
            SELECT
                t.relname AS table_name,
                i.relname AS index_name,
                ix.indisunique AS is_unique,
                array_to_string(
                    ARRAY(
                        SELECT a.attname
                        FROM pg_attribute a
                        WHERE a.attrelid = t.oid
                          AND a.attnum = ANY(ix.indkey)
                        ORDER BY a.attnum
                    ), ', '
                ) AS columns
            FROM pg_class t
            JOIN pg_index ix ON t.oid = ix.indrelid
            JOIN pg_class i  ON i.oid = ix.indexrelid
            JOIN pg_namespace n ON n.oid = t.relnamespace
            WHERE n.nspname = 'public'
              AND t.relkind = 'r'
              AND NOT ix.indisprimary
        """))
        idx_map: dict[str, list[str]] = {}
        for row in result.fetchall():
            unique = "UNIQUE " if row.is_unique else ""
            idx_map.setdefault(row.table_name, []).append(
                f"{unique}INDEX {row.index_name} ON ({row.columns})"
            )
        return idx_map

    async def _fetch_table_comments(self) -> dict[str, str]:
        """Return {table_name: comment_string} from pg_description."""
        result = await self._db.execute(text("""
            SELECT
                c.relname  AS table_name,
                d.description
            FROM pg_class c
            JOIN pg_namespace n   ON n.oid = c.relnamespace
            LEFT JOIN pg_description d ON d.objoid = c.oid AND d.objsubid = 0
            WHERE n.nspname = 'public'
              AND c.relkind = 'r'
              AND d.description IS NOT NULL
        """))
        return {row.table_name: row.description for row in result.fetchall()}

    async def _fetch_columns(
        self,
        table_name: str,
        pk_map: dict[str, set[str]],
        fk_map: dict[str, list[dict]],
    ) -> list[ColumnInfo]:
        """Fetch ordered columns for a single table with type + nullability."""
        result = await self._db.execute(
            text("""
                SELECT
                    c.column_name,
                    c.data_type,
                    c.is_nullable,
                    c.column_default,
                    c.ordinal_position,
                    col_description(
                        (SELECT oid FROM pg_class WHERE relname = :tname LIMIT 1),
                        c.ordinal_position
                    ) AS col_comment
                FROM information_schema.columns c
                WHERE c.table_name   = :tname
                  AND c.table_schema = 'public'
                ORDER BY c.ordinal_position
            """),
            {"tname": table_name},
        )
        rows = result.fetchall()
        if not rows:
            return []

        pks  = pk_map.get(table_name, set())
        fks  = {fk["column"]: fk for fk in fk_map.get(table_name, [])}

        columns: list[ColumnInfo] = []
        for row in rows:
            fk_info = fks.get(row.column_name, {})
            columns.append(ColumnInfo(
                name          = row.column_name,
                data_type     = row.data_type,
                nullable      = row.is_nullable == "YES",
                default       = row.column_default,
                is_primary_key= row.column_name in pks,
                is_foreign_key= bool(fk_info),
                fk_table      = fk_info.get("fk_table"),
                fk_column     = fk_info.get("fk_column"),
                comment       = row.col_comment,
                ordinal       = row.ordinal_position,
            ))
        return columns

    @staticmethod
    def _annotate_relationships(tables: list[TableInfo]) -> None:
        """Populate TableInfo.related_tables with bidirectional FK references."""
        name_map = {t.name: t for t in tables}
        for table in tables:
            for fk_col in table.foreign_keys:
                if fk_col.fk_table and fk_col.fk_table not in table.related_tables:
                    table.related_tables.append(fk_col.fk_table)
                # Reverse direction
                target = name_map.get(fk_col.fk_table or "")
                if target and table.name not in target.related_tables:
                    target.related_tables.append(table.name)
