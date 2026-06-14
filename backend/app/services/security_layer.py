"""
AI Security Layer
Enforces HIPAA compliance, prevents prompt injections, and redacts PHI.
"""

import re
import structlog
from typing import List, Dict, Any

logger = structlog.get_logger(__name__)

# Heuristic blocked phrases for Prompt Injection
PROMPT_INJECTION_PHRASES = [
    r"ignore previous instructions",
    r"ignore all previous",
    r"you are now a",
    r"system prompt",
    r"jailbreak",
    r"bypassing",
    r"forget what you were told",
    r"drop table",
    r"delete from"
]
PROMPT_INJECTION_RE = re.compile("|".join(PROMPT_INJECTION_PHRASES), re.IGNORECASE)

# PHI Regex Patterns
PHI_PATTERNS = {
    "ssn": re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),
    "phone": re.compile(r"\b\d{3}[-.]?\d{3}[-.]?\d{4}\b"),
    "email": re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b"),
    # MRN is typically formatted specifically, e.g., MRN-12345
    "mrn": re.compile(r"\bMRN-?\d+\b", re.IGNORECASE)
}

# Fields that likely contain PHI
PHI_FIELDS = {"ssn", "social_security", "first_name", "last_name", "mrn", "phone", "email", "address", "dob", "date_of_birth"}

class AISecurityLayer:
    """Security guardrails for LLM interactions and data access."""

    @staticmethod
    def detect_prompt_injection(query: str) -> bool:
        """
        Scan user input for prompt injection and malicious intent.
        Returns True if injection is detected.
        """
        if PROMPT_INJECTION_RE.search(query):
            logger.warning("Prompt injection detected", query_preview=query[:50])
            return True
        return False

    @staticmethod
    def redact_phi(rows: List[Dict[str, Any]], user_role: str) -> List[Dict[str, Any]]:
        """
        Redacts PHI from raw database rows based on user role.
        'analyst' role gets PHI redacted. 'doctor' or 'admin' do not.
        """
        # Define roles that require redaction
        roles_requiring_redaction = {"analyst", "guest", "auditor"}
        
        # We ensure user_role is extracted safely if it's an Enum or string
        role_str = getattr(user_role, "value", user_role) if hasattr(user_role, "value") else str(user_role)
        
        if role_str.lower() not in roles_requiring_redaction:
            return rows

        redacted_rows = []
        redaction_count = 0

        for row in rows:
            redacted_row = {}
            for key, value in row.items():
                if value is None:
                    redacted_row[key] = value
                    continue
                
                # Check column name heuristics
                if key.lower() in PHI_FIELDS:
                    redacted_row[key] = "***REDACTED***"
                    redaction_count += 1
                    continue
                
                # Check value heuristics (regex)
                val_str = str(value)
                original_val_str = val_str
                
                for phi_type, pattern in PHI_PATTERNS.items():
                    val_str = pattern.sub("***REDACTED***", val_str)
                
                if val_str != original_val_str:
                    redacted_row[key] = val_str
                    redaction_count += 1
                else:
                    redacted_row[key] = value
                    
            redacted_rows.append(redacted_row)
            
        if redaction_count > 0:
            logger.info("PHI Redaction applied", fields_redacted=redaction_count, role=role_str)
            
        return redacted_rows
