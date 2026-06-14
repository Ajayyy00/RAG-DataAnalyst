"""Chart advisor service: determines chart type and config from query results."""

from typing import Any, Dict, List, Optional

import structlog

logger = structlog.get_logger(__name__)


# Column type heuristics
TEMPORAL_KEYWORDS = {
    "date",
    "time",
    "year",
    "month",
    "quarter",
    "week",
    "day",
    "dt",
    "timestamp",
    "period",
}
CATEGORICAL_KEYWORDS = {
    "name",
    "type",
    "status",
    "category",
    "group",
    "dept",
    "facility",
    "icd",
    "cpt",
    "code",
    "desc",
    "payer",
}
NUMERIC_KEYWORDS = {
    "count",
    "total",
    "sum",
    "avg",
    "rate",
    "pct",
    "percent",
    "amount",
    "cost",
    "charge",
    "payment",
    "days",
    "score",
    "value",
    "mean",
    "median",
    "max",
    "min",
}


class ChartGenerationService:
    """Analyses query result columns to recommend the best chart type and config."""

    def _classify_column(self, col: str) -> str:
        """Return 'temporal', 'categorical', or 'numeric' based on column name."""
        col_lower = col.lower()
        if any(kw in col_lower for kw in NUMERIC_KEYWORDS):
            return "numeric"
        if any(kw in col_lower for kw in TEMPORAL_KEYWORDS):
            return "temporal"
        if any(kw in col_lower for kw in CATEGORICAL_KEYWORDS):
            return "categorical"
        return "categorical"  # default

    def _is_numeric_value(self, values: List[Any]) -> bool:
        """Check if a column contains primarily numeric values."""
        numeric_count = sum(
            1
            for v in values[:20]
            if v is not None and str(v).replace(".", "").replace("-", "").isdigit()
        )
        return numeric_count > len(values[:20]) * 0.7

    def recommend(
        self,
        columns: List[str],
        rows: List[List[Any]],
    ) -> Dict[str, Any]:
        """Return a chart configuration dict suitable for Recharts."""
        if not columns or not rows:
            return {"type": "table", "title": "Results", "color": "#3B82F6"}

        col_types = {col: self._classify_column(col) for col in columns}

        numeric_cols = [c for c, t in col_types.items() if t == "numeric"]
        temporal_cols = [c for c, t in col_types.items() if t == "temporal"]
        categorical_cols = [c for c, t in col_types.items() if t == "categorical"]

        # Also check actual values for numeric detection
        for i, col in enumerate(columns):
            col_values = [row[i] for row in rows]
            if self._is_numeric_value(col_values) and col not in numeric_cols:
                numeric_cols.append(col)
                categorical_cols = [c for c in categorical_cols if c != col]

        n_rows = len(rows)
        n_cols = len(columns)

        # ── Decision tree ─────────────────────────────────────
        chart_type = "table"
        x_key: Optional[str] = None
        y_key: Optional[str] = None
        series_keys: List[str] = []

        if n_cols == 1 and numeric_cols:
            # Single metric — KPI card
            chart_type = "kpi"
            y_key = numeric_cols[0]

        elif temporal_cols and numeric_cols:
            # Time series → line chart
            chart_type = "line"
            x_key = temporal_cols[0]
            y_key = numeric_cols[0]
            series_keys = numeric_cols[:3]

        elif categorical_cols and numeric_cols:
            # Categories → bar chart
            chart_type = "bar"
            x_key = categorical_cols[0]
            y_key = numeric_cols[-1]  # The main calculated metric is usually last
            series_keys = [y_key]

        elif n_cols >= 2 and all(
            self._is_numeric_value([row[i] for row in rows]) for i in range(n_cols)
        ):
            # All numeric → scatter
            chart_type = "scatter"
            x_key = columns[0]
            y_key = columns[1]

        title = self._build_title(chart_type, x_key, y_key)

        config = {
            "type": chart_type,
            "x_key": x_key,
            "y_key": y_key,
            "title": title,
            "color": "#3B82F6",
            "multi_series": len(series_keys) > 1,
            "series_keys": series_keys,
            "config": {"animate": True, "legend": len(series_keys) > 1},
        }
        logger.info(
            "Chart type recommended", chart_type=chart_type, x_key=x_key, y_key=y_key
        )
        return config

    def _build_title(
        self, chart_type: str, x_key: Optional[str], y_key: Optional[str]
    ) -> str:
        if y_key and x_key:
            return f"{y_key.replace('_', ' ').title()} by {x_key.replace('_', ' ').title()}"
        if y_key:
            return y_key.replace("_", " ").title()
        return "Query Results"
