"""Unit tests for ChartGenerationService — no external dependencies."""

import pytest

from app.services.chart_generation_service import ChartGenerationService


@pytest.fixture
def advisor():
    return ChartGenerationService()


# ── KPI ───────────────────────────────────────────────────────────────────────


class TestKPI:
    def test_single_numeric_column_gives_kpi(self, advisor):
        config = advisor.recommend(["total_count"], [[1234]])
        assert config["type"] == "kpi"
        assert config["y_key"] == "total_count"

    def test_single_rate_column_gives_kpi(self, advisor):
        config = advisor.recommend(["readmission_rate"], [[0.142]])
        assert config["type"] == "kpi"

    def test_single_avg_gives_kpi(self, advisor):
        config = advisor.recommend(["avg_los_days"], [[4.3]])
        assert config["type"] == "kpi"


# ── Line chart ────────────────────────────────────────────────────────────────


class TestLineChart:
    def test_temporal_plus_numeric_gives_line(self, advisor):
        columns = ["month", "visit_count"]
        rows = [["2024-01", 120], ["2024-02", 145], ["2024-03", 98]]
        config = advisor.recommend(columns, rows)
        assert config["type"] == "line"
        assert config["x_key"] == "month"
        assert config["y_key"] == "visit_count"

    def test_date_column_triggers_line(self, advisor):
        columns = ["admission_date", "avg_los_days"]
        rows = [["2024-01-01", 3.2], ["2024-01-02", 4.1], ["2024-01-03", 2.9]]
        config = advisor.recommend(columns, rows)
        assert config["type"] == "line"

    def test_year_column_triggers_line(self, advisor):
        columns = ["year", "total_claims"]
        rows = [[2022, 1450], [2023, 1620], [2024, 880]]
        config = advisor.recommend(columns, rows)
        assert config["type"] == "line"

    def test_line_multi_series(self, advisor):
        columns = ["month", "inpatient_count", "outpatient_count"]
        rows = [["Jan", 100, 400], ["Feb", 120, 380], ["Mar", 90, 420]]
        config = advisor.recommend(columns, rows)
        assert config["type"] == "line"
        assert len(config["series_keys"]) >= 1


# ── Bar chart ─────────────────────────────────────────────────────────────────


class TestBarChart:
    def test_many_categories_gives_bar(self, advisor):
        columns = ["department_name", "readmission_rate"]
        rows = [[f"Dept {i}", i * 0.1] for i in range(1, 10)]
        config = advisor.recommend(columns, rows)
        assert config["type"] == "bar"
        assert config["x_key"] == "department_name"

    def test_bar_has_correct_y_key(self, advisor):
        columns = ["icd10_code", "frequency"]
        rows = [[f"A{i:02d}", i * 5] for i in range(1, 9)]
        config = advisor.recommend(columns, rows)
        assert config["type"] == "bar"
        assert config["y_key"] == "frequency"

    def test_multi_numeric_bar_has_series_keys(self, advisor):
        columns = ["dept_name", "total_count", "avg_cost"]
        rows = [[f"Dept {i}", i * 10, i * 100] for i in range(1, 8)]
        config = advisor.recommend(columns, rows)
        assert config["type"] == "bar"
        assert len(config["series_keys"]) >= 1
        assert config["multi_series"] == (len(config["series_keys"]) > 1)


# ── Pie chart ─────────────────────────────────────────────────────────────────


class TestPieChart:
    def test_few_categories_gives_pie(self, advisor):
        columns = ["insurance_type", "patient_count"]
        rows = [["Medicare", 450], ["Medicaid", 320], ["Commercial", 280]]
        config = advisor.recommend(columns, rows)
        assert config["type"] == "pie"

    def test_exactly_six_rows_pie(self, advisor):
        columns = ["status", "count"]
        rows = [[f"Status{i}", i * 10] for i in range(1, 7)]
        config = advisor.recommend(columns, rows)
        assert config["type"] == "pie"

    def test_seven_rows_gives_bar_not_pie(self, advisor):
        columns = ["dept", "count"]
        rows = [[f"Dept{i}", i * 10] for i in range(1, 8)]
        config = advisor.recommend(columns, rows)
        assert config["type"] == "bar"


# ── Scatter chart ─────────────────────────────────────────────────────────────


class TestScatterChart:
    def test_two_numeric_columns_gives_scatter(self, advisor):
        columns = ["age", "length_of_stay"]
        rows = [[45, 3], [62, 7], [38, 2], [71, 9], [55, 5]]
        config = advisor.recommend(columns, rows)
        assert config["type"] == "scatter"
        assert config["x_key"] == "age"
        assert config["y_key"] == "length_of_stay"


# ── Fallback table ────────────────────────────────────────────────────────────


class TestFallback:
    def test_empty_data_gives_table(self, advisor):
        config = advisor.recommend([], [])
        assert config["type"] == "table"

    def test_empty_rows_gives_table(self, advisor):
        config = advisor.recommend(["col1", "col2"], [])
        assert config["type"] == "table"


# ── Config structure ──────────────────────────────────────────────────────────


class TestConfigStructure:
    def test_all_required_keys_present(self, advisor):
        columns = ["dept_name", "visit_count"]
        rows = [[f"Dept {i}", i * 5] for i in range(1, 8)]
        config = advisor.recommend(columns, rows)
        for key in (
            "type",
            "x_key",
            "y_key",
            "title",
            "color",
            "multi_series",
            "series_keys",
            "config",
        ):
            assert key in config, f"Missing key: {key}"

    def test_title_is_human_readable(self, advisor):
        columns = ["encounter_type", "avg_charge_amount"]
        rows = [["Inpatient", 1200.0], ["Outpatient", 340.0]]
        config = advisor.recommend(columns, rows)
        assert isinstance(config["title"], str)
        assert len(config["title"]) > 0
        assert "_" not in config["title"]  # should be human-readable, not snake_case

    def test_color_is_hex(self, advisor):
        columns = ["dept", "count"]
        rows = [[f"D{i}", i] for i in range(1, 8)]
        config = advisor.recommend(columns, rows)
        assert config["color"].startswith("#")
