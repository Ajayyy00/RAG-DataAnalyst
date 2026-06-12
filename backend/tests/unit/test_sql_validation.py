import pytest
from app.services.sql_validation_service import SQLValidationService
from app.core.exceptions import SQLValidationError

@pytest.fixture
def validator():
    return SQLValidationService()

def test_valid_select(validator):
    sql = "SELECT patient_id, count(*) FROM encounters GROUP BY patient_id;"
    is_valid, violations, normalized = validator.validate(sql)
    assert is_valid is True
    assert len(violations) == 0
    assert "LIMIT" in normalized.upper()

def test_blocked_keywords_delete(validator):
    sql = "DELETE FROM patients WHERE id = 1;"
    is_valid, violations, normalized = validator.validate(sql)
    assert is_valid is False
    assert any("DELETE" in v for v in violations)
    assert any("SELECT" in v for v in violations)

def test_blocked_keywords_update(validator):
    sql = "UPDATE patients SET first_name = 'Test';"
    is_valid, violations, normalized = validator.validate(sql)
    assert is_valid is False
    assert any("UPDATE" in v for v in violations)

def test_blocked_keywords_drop(validator):
    sql = "DROP TABLE encounters;"
    is_valid, violations, normalized = validator.validate(sql)
    assert is_valid is False
    assert any("DROP" in v for v in violations)

def test_unauthorized_table(validator):
    sql = "SELECT * FROM pg_catalog.pg_tables;"
    is_valid, violations, normalized = validator.validate(sql)
    assert is_valid is False
    assert any("Unauthorized tables" in v for v in violations)

def test_limit_injection(validator):
    sql = "SELECT * FROM patients"
    is_valid, violations, normalized = validator.validate(sql)
    assert is_valid is True
    assert normalized.strip().endswith("LIMIT 1000;")

def test_multiple_statements_injection(validator):
    sql = "SELECT * FROM patients; DROP TABLE patients;"
    is_valid, violations, normalized = validator.validate(sql)
    assert is_valid is False
    assert any("Multiple statements detected" in v for v in violations)

def test_validate_or_raise_success(validator):
    sql = "SELECT id FROM patients LIMIT 10;"
    normalized = validator.validate_or_raise(sql)
    assert "LIMIT 10" in normalized

def test_validate_or_raise_failure(validator):
    sql = "TRUNCATE TABLE patients;"
    with pytest.raises(SQLValidationError):
        validator.validate_or_raise(sql)
