from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class DataQualityAnalyzeRequest(BaseModel):
    table_name: str = Field(..., description="The name of the table to analyze")
    limit: int = Field(10000, description="Max rows to fetch for analysis")


class QualityIssue(BaseModel):
    type: str = Field(
        ..., description="Type of issue: missing, duplicate, outlier, invalid"
    )
    column: Optional[str] = Field(None, description="Affected column if applicable")
    description: str = Field(..., description="Human readable description")
    count: int = Field(0, description="Number of affected rows")
    affected_ids: List[Any] = Field(
        default=[], description="List of primary keys affected (up to a limit)"
    )


class AutomatedFix(BaseModel):
    description: str = Field(..., description="What the fix does")
    sql_script: str = Field(
        ..., description="Raw SQL UPDATE/DELETE statement to fix the issue"
    )


class DataQualityReport(BaseModel):
    table_name: str
    total_rows_analyzed: int
    issues: List[QualityIssue]
    automated_fixes: List[AutomatedFix]
