"""Dashboard generation schemas."""
from __future__ import annotations
from typing import Any, Dict, List, Optional
from pydantic import BaseModel


class PanelSize(BaseModel):
    col_span: int = 2
    row_span: int = 2


class DashboardPanel(BaseModel):
    id: str
    title: str
    subtitle: str = ""
    sql: Optional[str] = None
    columns: List[str] = []
    rows: List[List[Any]] = []
    row_count: Optional[int] = None
    chart_type: Optional[str] = None
    chart_data: List[Dict[str, Any]] = []
    x_key: Optional[str] = None
    y_key: Optional[str] = None
    series_keys: List[str] = []
    insight_summary: str = ""
    error: Optional[str] = None
    size: PanelSize = PanelSize()
    col_start: int = 1
    row_start: int = 1


class DashboardLayout(BaseModel):
    grid_cols: int = 6
    panel_count: int = 0
    success_count: int = 0


class DashboardResponse(BaseModel):
    id: str
    title: str
    request: str
    summary: str = ""
    panels: List[DashboardPanel] = []
    layout: DashboardLayout = DashboardLayout()
    total_rows: int = 0


class DashboardGenerateRequest(BaseModel):
    request: str
    max_panels: int = 5
