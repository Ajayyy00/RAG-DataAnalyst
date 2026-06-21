"""Unit tests for SQLValidationService — no external dependencies required."""

import pytest

from app.core.exceptions import SQLValidationError
from app.services.sql_validation_service import SQLValidationService


@pytest.fixture
def validator():
    return SQLValidationService()


# ── Valid SELECT queries ───────────────────────────────────────────────────────


class TestValidQueries:
    def test_simple_select(self, validator):
        sql = "SELECT * FROM patients LIMIT 10;"
        valid, violations, _ = validator.validate_legacy(sql)
        assert valid
        assert violations == []

    def test_join_query(self, validator):
        sql = """
            SELECT p.last_name, e.encounter_type, COUNT(*) AS cnt
            FROM patients p
            JOIN encounters e ON e.patient_id = p.id
            GROUP BY p.last_name, e.encounter_type
            LIMIT 50;
        """
        valid, violations, _ = validator.validate_legacy(sql)
        assert valid
        assert violations == []

    def test_cte_query(self, validator):
        sql = """
            WITH monthly AS (
                SELECT DATE_TRUNC('month', admit_date) AS month, COUNT(*) AS visits
                FROM encounters
                GROUP BY month
            )
            SELECT * FROM monthly ORDER BY month LIMIT 12;
        """
        valid, violations, _ = validator.validate_legacy(sql)
        assert valid

    def test_multiple_allowed_tables(self, validator):
        sql = """
            SELECT d.icd10_code, COUNT(*) AS freq
            FROM diagnoses d
            JOIN encounters e ON e.id = d.encounter_id
            JOIN patients p ON p.id = d.patient_id
            GROUP BY d.icd10_code
            ORDER BY freq DESC
            LIMIT 10;
        """
        valid, violations, _ = validator.validate_legacy(sql)
        assert valid

    def test_aggregate_query(self, validator):
        sql = """
            SELECT
                DATE_TRUNC('month', admit_date) AS month,
                AVG(total_charge) AS avg_charge,
                COUNT(*) AS visit_count
            FROM encounters
            GROUP BY month
            ORDER BY month DESC
            LIMIT 24;
        """
        valid, violations, _ = validator.validate_legacy(sql)
        assert valid


# ── Blocked DML / DDL ─────────────────────────────────────────────────────────


class TestBlockedOperations:
    @pytest.mark.parametrize(
        "sql",
        [
            "DELETE FROM patients WHERE id = '123';",
            "DROP TABLE encounters;",
            "INSERT INTO patients (id) VALUES ('abc');",
            "UPDATE patients SET first_name = 'Hack' WHERE 1=1;",
            "TRUNCATE TABLE lab_results;",
            "ALTER TABLE patients ADD COLUMN evil TEXT;",
            "GRANT ALL ON patients TO hacker;",
            "REVOKE SELECT ON patients FROM analyst;",
        ],
    )
    def test_dml_ddl_blocked(self, validator, sql):
        valid, violations, _ = validator.validate_legacy(sql)
        # The query must be rejected with at least one explicit reason. The
        # specific reason may be the statement-type/keyword guard OR the
        # injection guard (e.g. a "WHERE 1=1" tautology short-circuits first).
        assert not valid
        assert len(violations) > 0


# ── Unauthorized tables ───────────────────────────────────────────────────────


class TestUnauthorizedTables:
    def test_unknown_table_blocked(self, validator):
        sql = "SELECT * FROM secret_audit_log LIMIT 10;"
        valid, violations, _ = validator.validate_legacy(sql)
        assert not valid
        assert any("Unauthorized" in v for v in violations)

    def test_users_table_blocked(self, validator):
        """users table holds hashed_passwords — must never be queryable."""
        sql = "SELECT email, hashed_password FROM users LIMIT 10;"
        valid, violations, _ = validator.validate_legacy(sql)
        assert not valid

    def test_information_schema_blocked(self, validator):
        sql = "SELECT table_name FROM information_schema.tables;"
        valid, violations, _ = validator.validate_legacy(sql)
        assert not valid


# ── LIMIT injection ───────────────────────────────────────────────────────────


class TestLimitInjection:
    def test_limit_injected_when_missing(self, validator):
        sql = "SELECT * FROM patients;"
        valid, violations, normalized = validator.validate_legacy(sql)
        assert "LIMIT" in normalized.upper()

    def test_existing_limit_preserved(self, validator):
        sql = "SELECT * FROM patients LIMIT 5;"
        _, _, normalized = validator.validate_legacy(sql)
        assert "LIMIT 5" in normalized

    def test_large_limit_left_intact(self, validator):
        sql = "SELECT id FROM encounters LIMIT 500;"
        _, _, normalized = validator.validate_legacy(sql)
        assert "LIMIT 500" in normalized


# ── Multiple statements / injection guard ─────────────────────────────────────


class TestInjectionGuard:
    def test_multiple_statements_blocked(self, validator):
        sql = "SELECT * FROM patients LIMIT 1; DROP TABLE patients;"
        valid, violations, _ = validator.validate_legacy(sql)
        assert not valid
        assert any("Multiple statements" in v or "Prohibited" in v for v in violations)


# ── validate_or_raise ─────────────────────────────────────────────────────────


class TestValidateOrRaise:
    def test_valid_does_not_raise(self, validator):
        sql = "SELECT id FROM patients LIMIT 1;"
        result = validator.validate_or_raise(sql)
        assert "SELECT" in result.upper()

    def test_invalid_raises_sql_validation_error(self, validator):
        with pytest.raises(SQLValidationError):
            validator.validate_or_raise("DELETE FROM patients;")

    def test_returns_normalized_sql(self, validator):
        sql = "SELECT id FROM patients"  # no LIMIT
        result = validator.validate_or_raise(sql)
        assert "LIMIT" in result.upper()


# ── Pre-compiled patterns performance regression ──────────────────────────────


class TestPrecompiledPatterns:
    def test_patterns_are_precompiled(self):
        """Verify the module-level dict of pre-compiled patterns exists."""
        import re

        from app.services.sql_validation_service import _BLOCKED_KW_RE

        assert len(_BLOCKED_KW_RE) > 0
        for kw, pat in _BLOCKED_KW_RE.items():
            assert isinstance(pat, re.Pattern)

    def test_validation_called_repeatedly_is_consistent(self, validator):
        sql = "SELECT * FROM patients LIMIT 10;"
        for _ in range(10):
            valid, violations, _ = validator.validate_legacy(sql)
            assert valid
            assert violations == []
