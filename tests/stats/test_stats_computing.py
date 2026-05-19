from unittest.mock import MagicMock

from core.schema import Col
from stats.stats_computing import compute_column_stats, ensure_stats_table, is_numeric_type


def test_is_numeric_type_detects_numeric_types() -> None:
    assert is_numeric_type("Int64") is True
    assert is_numeric_type("UInt32") is True
    assert is_numeric_type("Float64") is True
    assert is_numeric_type("Decimal(10, 2)") is True
    assert is_numeric_type("String") is False
    assert is_numeric_type("Date") is False


def test_ensure_stats_table_creates_column_stats_table() -> None:
    db = MagicMock()

    ensure_stats_table(db)

    db.command.assert_called_once()
    sql = db.command.call_args[0][0]

    assert "CREATE TABLE IF NOT EXISTS" in sql
    assert "column_stats" in sql
    assert "entropy_ratio" in sql
    assert "variation_coefficient" in sql
    assert "skewness_score" in sql


def test_compute_column_stats_numeric_column_contains_numeric_metrics() -> None:
    db = MagicMock()
    col = Col(name="price", ch_type="Float64")

    compute_column_stats(
        db=db,
        run_ts="2024-01-01 00:00:00",
        database="lab_db",
        table="products",
        col=col,
    )

    db.command.assert_called_once()
    sql = db.command.call_args[0][0]
    params = db.command.call_args[1]["parameters"]

    assert "INSERT INTO" in sql
    assert "avg(`price`)" in sql
    assert "stddevPop(`price`)" in sql
    assert "skewPop(`price`)" in sql
    assert params["database"] == "lab_db"
    assert params["table"] == "products"
    assert params["column"] == "price"
    assert params["column_type"] == "Float64"


def test_compute_column_stats_string_column_uses_zero_numeric_metrics() -> None:
    db = MagicMock()
    col = Col(name="label", ch_type="String")

    compute_column_stats(
        db=db,
        run_ts="2024-01-01 00:00:00",
        database="lab_db",
        table="products",
        col=col,
    )

    sql = db.command.call_args[0][0]

    assert "0.0 AS avg_value" in sql
    assert "0.0 AS std_value" in sql
    assert "0.0 AS skew_value" in sql
