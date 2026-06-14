"""
SQL Validation & Safety Engine
================================
Provides AST-level validation, safety enforcement, SQL injection prevention,
and query complexity scoring for all analyst-generated SQL before execution.

Pipeline:
    1. AST Parse          — strict sqlglot parse with dialect=postgres
    2. Statement Guard    — only SELECT / WITH…SELECT allowed
    3. Blocked DML/DDL    — AST-node + regex dual-layer check
    4. Table Allowlist    — every FROM/JOIN table must be whitelisted
    5. Column Guard       — blocks pg_catalog / information_schema access
    6. Injection Defence  — stacked statements, comment probes, tautologies
    7. LIMIT enforcement  — injects LIMIT if absent
    8. Complexity Score   — penalises joins, subqueries, cross products, etc.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Dict, FrozenSet, List, Optional, Set, Tuple

import sqlglot
import sqlglot.expressions as exp
import sqlglot.errors
import structlog

from app.core.exceptions import SQLValidationError

logger = structlog.get_logger(__name__)


# ──────────────────────────────────────────────────────────────
#  Configuration
# ──────────────────────────────────────────────────────────────

class RiskLevel(Enum):
    LOW    = auto()
    MEDIUM = auto()
    HIGH   = auto()
    CRITICAL = auto()


# Tables the copilot is permitted to query
ALLOWED_TABLES: FrozenSet[str] = frozenset({
    "patients", "encounters", "diagnoses", "procedures",
    "medications", "lab_results", "vital_signs", "claims",
    "readmissions", "providers", "departments", "facilities",
    "copilot_sessions", "copilot_messages",
})

# DML / DDL expression types that are NEVER permitted (AST-level)
BLOCKED_STATEMENT_TYPES: Tuple[type, ...] = (
    exp.Insert, exp.Update, exp.Delete, exp.Drop,
    exp.Create, exp.AlterTable, exp.TruncateTable,
    exp.Merge, exp.Command,  # EXEC / raw commands
)

# Supplementary keyword block list (catches obfuscation the AST may miss)
BLOCKED_KEYWORDS: FrozenSet[str] = frozenset({
    "INSERT", "UPDATE", "DELETE", "DROP", "TRUNCATE", "ALTER",
    "CREATE", "REPLACE", "MERGE", "EXEC", "EXECUTE",
    "GRANT", "REVOKE", "COPY", "VACUUM", "ANALYZE",
    "REINDEX", "CLUSTER", "COMMENT", "SECURITY",
    "CALL", "DO", "LOAD", "IMPORT",
})

# Schemas that analysts should never be able to read
BLOCKED_SCHEMAS: FrozenSet[str] = frozenset({
    "pg_catalog", "information_schema", "pg_toast",
    "pg_temp", "pg_internal",
})

# Regex patterns compiled once at module load
_BLOCKED_KW_RE: Dict[str, re.Pattern] = {
    kw: re.compile(rf"(?<!['\"])\b{re.escape(kw)}\b(?!['\"])", re.IGNORECASE)
    for kw in BLOCKED_KEYWORDS
}

# Injection: stacked statements (;-separated)
_MULTI_STMT_RE = re.compile(r";\s*\S")

# Injection: inline / block comment probes
_COMMENT_PROBE_RE = re.compile(r"(--|#|/\*|\*/)")

# Injection: classic tautology patterns
_TAUTOLOGY_RE = re.compile(
    r"\b(OR|AND)\b\s+[\w']+=\s*[\w']+\s+--"
    r"|'[^']*'\s*=\s*'[^']*'"     # 'a'='a'
    r"|\b1\s*=\s*1\b"             # 1=1
    r"|\b''\s*=\s*''\b",          # ''=''
    re.IGNORECASE,
)

# Complexity scoring weights
_COMPLEXITY_WEIGHTS = {
    "join":        3,   # per JOIN
    "subquery":    4,   # per subselect / derived table
    "cte":         2,   # per CTE
    "aggregate":   1,   # per aggregate function
    "window":      3,   # per window function
    "union":       2,   # per UNION / INTERSECT / EXCEPT
    "cross_join":  8,   # CROSS JOIN is especially expensive
    "distinct":    2,
    "order_by":    1,
    "having":      1,
}
MAX_COMPLEXITY = 30   # queries above this are rejected as too complex


# ──────────────────────────────────────────────────────────────
#  Result dataclass
# ──────────────────────────────────────────────────────────────

@dataclass
class ValidationResult:
    is_valid: bool
    normalized_sql: str
    violations: List[str] = field(default_factory=list)
    warnings: List[str]   = field(default_factory=list)
    complexity_score: int  = 0
    risk_level: RiskLevel  = RiskLevel.LOW
    referenced_tables: Set[str] = field(default_factory=set)
    cte_names: Set[str]         = field(default_factory=set)

    def add_violation(self, msg: str) -> None:
        self.violations.append(msg)
        self.is_valid = False

    def add_warning(self, msg: str) -> None:
        self.warnings.append(msg)


# ──────────────────────────────────────────────────────────────
#  Complexity Scorer
# ──────────────────────────────────────────────────────────────

class ComplexityScorer:
    """Walk AST and assign a numeric complexity score."""

    def score(self, statement: exp.Expression) -> Tuple[int, Dict[str, int]]:
        breakdown: Dict[str, int] = {}

        # Joins
        joins = list(statement.find_all(exp.Join))
        cross = sum(1 for j in joins if j.args.get("kind") == "CROSS")
        inner = len(joins) - cross
        if inner:
            breakdown["join"] = inner
        if cross:
            breakdown["cross_join"] = cross

        # Subqueries / derived tables
        subqueries = [
            n for n in statement.find_all(exp.Subquery)
            if n is not statement  # top-level is not a subquery itself
        ]
        if subqueries:
            breakdown["subquery"] = len(subqueries)

        # CTEs
        ctes = list(statement.find_all(exp.CTE))
        if ctes:
            breakdown["cte"] = len(ctes)

        # Aggregates
        aggs = list(statement.find_all(exp.AggFunc))
        if aggs:
            breakdown["aggregate"] = len(aggs)

        # Window functions
        windows = list(statement.find_all(exp.Window))
        if windows:
            breakdown["window"] = len(windows)

        # UNION / INTERSECT / EXCEPT
        set_ops = list(statement.find_all((exp.Union, exp.Intersect, exp.Except)))
        if set_ops:
            breakdown["union"] = len(set_ops)

        # DISTINCT
        if statement.find(exp.Distinct):
            breakdown["distinct"] = 1

        # ORDER BY
        if statement.find(exp.Order):
            breakdown["order_by"] = 1

        # HAVING
        if statement.find(exp.Having):
            breakdown["having"] = 1

        total = sum(
            _COMPLEXITY_WEIGHTS.get(k, 1) * v
            for k, v in breakdown.items()
        )
        return total, breakdown


# ──────────────────────────────────────────────────────────────
#  Injection Detector
# ──────────────────────────────────────────────────────────────

class InjectionDetector:
    """Heuristic SQL injection & probe detection."""

    def analyse(self, raw_sql: str) -> List[str]:
        findings: List[str] = []

        # 1. Stacked / multi-statement injection
        if _MULTI_STMT_RE.search(raw_sql):
            findings.append(
                "INJECTION: Multiple statements detected (stacked query attack)"
            )

        # 2. Suspicious comment patterns (indicator of injection attempts)
        comment_hits = _COMMENT_PROBE_RE.findall(raw_sql)
        if comment_hits:
            findings.append(
                f"INJECTION: Comment tokens found ({', '.join(set(comment_hits))})"
                " — potential comment-based injection"
            )

        # 3. Classic tautology patterns
        if _TAUTOLOGY_RE.search(raw_sql):
            findings.append(
                "INJECTION: Tautology pattern detected (e.g. OR 1=1, 'a'='a')"
            )

        # 4. Null-byte injection
        if "\x00" in raw_sql:
            findings.append("INJECTION: Null byte detected")

        # 5. Hex / unicode escape abuse
        if re.search(r"0x[0-9a-fA-F]{4,}", raw_sql):
            findings.append("INJECTION: Suspicious hex literal sequence")

        # 6. Excessive nesting depth (deeply nested subqueries are suspicious)
        if raw_sql.count("(") > 25:
            findings.append(
                "INJECTION: Excessive bracket nesting — potential obfuscated query"
            )

        return findings


# ──────────────────────────────────────────────────────────────
#  Main Validation Service
# ──────────────────────────────────────────────────────────────

class SQLValidationService:
    """
    Full SQL validation & safety engine.

    Usage::

        svc = SQLValidationService()
        result = svc.validate(sql)
        if not result.is_valid:
            print(result.violations)

        # Or raise immediately:
        normalised = svc.validate_or_raise(sql)
    """

    def __init__(self) -> None:
        self._scorer   = ComplexityScorer()
        self._detector = InjectionDetector()

    # ── Public API ────────────────────────────────────────────

    def validate(self, sql: str) -> ValidationResult:
        """
        Full validation pipeline.

        Returns a :class:`ValidationResult` with ``is_valid``,
        ``violations``, ``warnings``, ``complexity_score``, and
        ``normalized_sql``.
        """
        normalized = sql.strip()
        result = ValidationResult(is_valid=True, normalized_sql=normalized)

        # Step 1 — Injection pre-check (on raw string before any parsing)
        self._check_injection(sql, result)
        if not result.is_valid:
            # No point continuing if injection is detected
            return result

        # Step 2 — AST parse
        statement = self._parse(sql, result)
        if statement is None:
            return result

        # Step 3 — Statement type guard
        self._check_statement_type(statement, result)

        # Step 4 — Blocked keyword scan (dual-layer: AST + regex)
        self._check_blocked_keywords(sql, statement, result)

        # Step 5 — Table & schema allowlist
        self._check_table_allowlist(statement, result)

        # Step 6 — Blocked schema / system catalog access
        self._check_schema_access(statement, result)

        # Step 7 — Complexity scoring
        self._check_complexity(statement, result)

        # Step 8 — LIMIT enforcement (non-blocking; injects LIMIT)
        self._enforce_limit(sql, statement, result)

        # Assign overall risk level
        result.risk_level = self._compute_risk(result)

        if not result.is_valid:
            logger.warning(
                "SQL validation failed",
                violations=result.violations,
                complexity=result.complexity_score,
                audit_event="hipaa_security_alert",
            )
        else:
            logger.info(
                "SQL validation passed",
                tables=list(result.referenced_tables),
                complexity=result.complexity_score,
                risk=result.risk_level.name,
            )

        return result

    def validate_or_raise(self, sql: str) -> str:
        """Validate and return normalised SQL, or raise :class:`SQLValidationError`."""
        result = self.validate(sql)
        if not result.is_valid:
            raise SQLValidationError(
                "SQL failed safety validation",
                violations=result.violations,
            )
        return result.normalized_sql

    # Legacy 3-tuple interface (backward compat with existing callers)
    def validate_legacy(self, sql: str) -> Tuple[bool, List[str], str]:
        """Return (is_valid, violations, normalized_sql) — legacy shim."""
        r = self.validate(sql)
        return r.is_valid, r.violations, r.normalized_sql

    # ── Private pipeline steps ────────────────────────────────

    def _parse(
        self, sql: str, result: ValidationResult
    ) -> Optional[exp.Expression]:
        """Parse SQL with sqlglot. Returns the first statement or None."""
        try:
            parsed = sqlglot.parse(sql, dialect="postgres", error_level=sqlglot.ErrorLevel.RAISE)
            if not parsed:
                result.add_violation("SQL is empty or could not be parsed")
                return None
            if len(parsed) > 1:
                result.add_violation(
                    f"Multiple statements ({len(parsed)}) detected — only one allowed"
                )
                return None
            return parsed[0]
        except sqlglot.errors.ParseError as exc:
            result.add_violation(f"Syntax error: {exc}")
            return None

    def _check_injection(self, sql: str, result: ValidationResult) -> None:
        """Run heuristic injection detector before AST parse."""
        findings = self._detector.analyse(sql)
        for f in findings:
            result.add_violation(f)

    def _check_statement_type(
        self, statement: exp.Expression, result: ValidationResult
    ) -> None:
        """Ensure only SELECT (or WITH…SELECT) statements are allowed."""
        # WITH is a Select node that starts with CTEs — acceptable
        if isinstance(statement, exp.Select):
            return
        # Some dialects wrap WITH as a separate node; unwrap it
        if isinstance(statement, exp.With):
            return
        # Explicitly blocked DML / DDL
        if isinstance(statement, BLOCKED_STATEMENT_TYPES):
            stmt_name = type(statement).__name__.upper()
            result.add_violation(
                f"Prohibited statement type: {stmt_name} — only SELECT is allowed"
            )
            return
        # Unknown / unhandled statement type
        result.add_violation(
            f"Unexpected statement type: {type(statement).__name__}"
            " — only SELECT statements are permitted"
        )

    def _check_blocked_keywords(
        self, sql: str, statement: exp.Expression, result: ValidationResult
    ) -> None:
        """
        Dual-layer keyword guard:
          a) AST node type check (catches correctly parsed DML)
          b) Regex scan (catches obfuscated / comment-injected variants)
        """
        # a) AST-level: look for any blocked statement node inside the tree
        for blocked_type in BLOCKED_STATEMENT_TYPES:
            nodes = list(statement.find_all(blocked_type))
            if nodes:
                result.add_violation(
                    f"Prohibited AST node detected: {blocked_type.__name__}"
                )

        # b) Regex-level: scan normalised upper-case string
        sql_upper = sql.upper()
        for kw, pattern in _BLOCKED_KW_RE.items():
            if pattern.search(sql_upper):
                result.add_violation(f"Prohibited keyword: {kw}")

    def _check_table_allowlist(
        self, statement: exp.Expression, result: ValidationResult
    ) -> None:
        """Every real table reference must appear in ALLOWED_TABLES."""
        # Collect CTE alias names — they are virtual, not real tables
        result.cte_names = {
            cte.alias.lower()
            for cte in statement.find_all(exp.CTE)
            if cte.alias
        }

        result.referenced_tables = {
            t.name.lower()
            for t in statement.find_all(exp.Table)
            if t.name
        }

        unknown = (
            result.referenced_tables
            - ALLOWED_TABLES
            - result.cte_names
        )
        if unknown:
            result.add_violation(
                f"Unauthorized table(s) referenced: {', '.join(sorted(unknown))}"
            )

    def _check_schema_access(
        self, statement: exp.Expression, result: ValidationResult
    ) -> None:
        """Block access to pg_catalog / information_schema."""
        def _node_str(node) -> str:
            """Safely extract string value from a sqlglot node or plain string."""
            if node is None:
                return ""
            if isinstance(node, str):
                return node.lower()
            # sqlglot Expression node — use .name
            return (getattr(node, "name", None) or "").lower()

        for table in statement.find_all(exp.Table):
            db     = _node_str(table.args.get("db"))
            schema = _node_str(table.args.get("catalog"))
            name   = _node_str(table.name)
            for blocked in BLOCKED_SCHEMAS:
                if blocked in (db, schema, name):
                    result.add_violation(
                        f"Access to system schema '{blocked}' is forbidden"
                    )

    def _check_complexity(
        self, statement: exp.Expression, result: ValidationResult
    ) -> None:
        """Score query complexity and reject if over budget."""
        score, breakdown = self._scorer.score(statement)
        result.complexity_score = score

        if score > MAX_COMPLEXITY:
            result.add_violation(
                f"Query complexity score {score} exceeds maximum {MAX_COMPLEXITY}. "
                f"Breakdown: {breakdown}. Simplify the query (fewer joins/subqueries)."
            )
        elif score > MAX_COMPLEXITY * 0.75:
            result.add_warning(
                f"High query complexity ({score}/{MAX_COMPLEXITY}). "
                "Consider simplifying to improve performance."
            )

    def _enforce_limit(
        self,
        sql: str,
        statement: exp.Expression,
        result: ValidationResult,
    ) -> None:
        """
        Ensure every query has a LIMIT clause.
        If absent, inject LIMIT 1000 and add a warning.
        """
        has_limit = statement.find(exp.Limit) is not None
        if not has_limit:
            bare = result.normalized_sql.rstrip().rstrip(";")
            result.normalized_sql = f"{bare}\nLIMIT 1000;"
            result.add_warning(
                "No LIMIT clause found — LIMIT 1000 automatically injected"
            )
        else:
            # Verify LIMIT is not absurdly large (> 100,000)
            limit_node = statement.find(exp.Limit)
            if limit_node:
                try:
                    limit_val = int(limit_node.expression.this)
                    if limit_val > 100_000:
                        result.add_violation(
                            f"LIMIT {limit_val:,} exceeds the maximum allowed value of 100,000"
                        )
                except (AttributeError, ValueError, TypeError):
                    pass  # Dynamic LIMIT — can't inspect statically

    @staticmethod
    def _compute_risk(result: ValidationResult) -> RiskLevel:
        """Assign overall risk level based on findings."""
        if not result.is_valid:
            # Check if any injection findings exist
            if any("INJECTION" in v for v in result.violations):
                return RiskLevel.CRITICAL
            return RiskLevel.HIGH

        if result.complexity_score > MAX_COMPLEXITY * 0.75:
            return RiskLevel.MEDIUM

        if result.warnings:
            return RiskLevel.LOW

        return RiskLevel.LOW


# ──────────────────────────────────────────────────────────────
#  Convenience function for one-off validation
# ──────────────────────────────────────────────────────────────

def validate_sql(sql: str) -> ValidationResult:
    """Module-level convenience wrapper."""
    return SQLValidationService().validate(sql)
