from unittest.mock import MagicMock

from core.schema import Col
from profiling.basic_profile import ColumnProfile, ProfileEngine


# ── Tests compute_basic_profile_for_column ────────────────────────────────────

def test_compute_basic_profile_returns_a_column_profile() -> None:
    """The result must be a ColumnProfile populated with the values returned by ClickHouse."""
    db = MagicMock()
    # Simulate the ClickHouse response tuple:
    # (rows, non_null_rows, null_rows, null_ratio, distinct_count, uniqueness_ratio, min, max)
    db.query.return_value.result_rows = [
        (100, 98, 2, 0.02, 95, 0.969, "1", "999")
    ]

    engine = ProfileEngine(db)
    col = Col(name="customer_id", ch_type="Int64")
    profile = engine.compute_basic_profile_for_column("customers", col)

    assert isinstance(profile, ColumnProfile)
    assert profile.table_name == "customers"
    assert profile.column_name == "customer_id"
    assert profile.column_type == "Int64"
    assert profile.rows == 100
    assert profile.non_null_rows == 98
    assert profile.null_rows == 2
    assert profile.null_ratio == 0.02
    assert profile.distinct_count == 95
    assert profile.min_value == "1"
    assert profile.max_value == "999"


def test_compute_basic_profile_rounds_ratios() -> None:
    """Ratios must be rounded to 6 decimal places."""
    db = MagicMock()
    db.query.return_value.result_rows = [
        (1000, 999, 1, 0.001000001, 999, 0.9999999, "a", "z")
    ]

    engine = ProfileEngine(db)
    col = Col(name="label", ch_type="String")
    profile = engine.compute_basic_profile_for_column("products", col)

    # Values must be rounded to at most 6 decimal places.
    assert len(str(profile.null_ratio).split(".")[-1]) <= 7


# ── Tests insert_column_profiles ─────────────────────────────────────────────

def test_insert_column_profiles_calls_db_insert() -> None:
    """The method must issue exactly one db.insert call."""
    db = MagicMock()
    engine = ProfileEngine(db)

    profiles = [
        ColumnProfile(
            database_name="lab_db",
            table_name="customers",
            column_name="customer_id",
            column_type="Int64",
            rows=100,
            non_null_rows=100,
            null_rows=0,
            null_ratio=0.0,
            distinct_count=100,
            uniqueness_ratio=1.0,
            min_value="1",
            max_value="100",
        )
    ]

    engine.insert_column_profiles(profiles)

    db.insert.assert_called_once()
    # Verify that the target table name is correct.
    call_args = db.insert.call_args[0]
    assert "column_profiles" in call_args[0]


def test_insert_column_profiles_does_nothing_when_empty() -> None:
    """No INSERT must be issued when the profile list is empty."""
    db = MagicMock()
    engine = ProfileEngine(db)

    engine.insert_column_profiles([])

    db.insert.assert_not_called()
