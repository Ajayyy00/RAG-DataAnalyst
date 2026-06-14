from typing import List

from pydantic import BaseModel, Field


class SQLExplanation(BaseModel):
    summary: str = Field(
        ...,
        description="High-level explanation of what the query does in simple terms.",
    )
    tables_used: List[str] = Field(
        ..., description="List of tables involved and why they are used."
    )
    joins: List[str] = Field(
        ..., description="Explanation of how the tables are linked together."
    )
    filters: List[str] = Field(
        ...,
        description="Explanation of the WHERE clauses, e.g. 'Filtering for admissions after Jan 1st 2024'.",
    )
    aggregations: List[str] = Field(
        ...,
        description="Explanation of GROUP BY, COUNT, SUM, etc. or 'None' if not applicable.",
    )
