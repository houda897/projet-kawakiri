from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from inference.join_candidate import JoinEngine, JoinPrimaryKeyCandidate, SourceColumn
from inference.primary_key import PrimaryKeyCandidate

# ── Helpers ────────────────────────────────────────────────────────────────────


def make_pk(table: str, column: str, col_type: str = "Int64") -> PrimaryKeyCandidate:
    """Build a minimal PrimaryKeyCandidate for use in tests."""
    return PrimaryKeyCandidate(
        database_name="lab_db",
        table_name=table,
        column_name=column,
        column_type=col_type,
        rows=100,
        null_ratio=0.0,
        uniqueness_ratio=1.0,
        identifiability_score=0.9,
        confidence=0.97,
        reason="hard_rule=unique_and_complete",
    )


def make_source(table: str, column: str, col_type: str = "Int64") -> SourceColumn:
    """Build a minimal SourceColumn for use in tests."""
    return SourceColumn(table_name=table, column_name=column, column_type=col_type)


# ── Tests JoinPrimaryKeyCandidate ──────────────────────────────────────────────


def test_join_candidate_stores_all_metrics() -> None:
    """The dataclass must store all join metrics correctly."""
    candidate = JoinPrimaryKeyCandidate(
        source_table="sales",
        source_column="customer_id",
        target_table="customers",
        target_column="customer_id",
        source_non_null_rows=6,
        matched_rows=6,
        join_success_ratio=1.0,
    )

    assert candidate.source_table == "sales"
    assert candidate.target_table == "customers"
    assert candidate.join_success_ratio == 1.0
    assert candidate.matched_rows == 6


#

# ── Tests JoinEngine.should_skip_pair ─────────────────────────────────────────


def test_should_skip_pair_rejects_same_table() -> None:
    """A column must not be compared against a PK from the same table."""
    source = make_source("sales", "product_id")
    pk = make_pk("sales", "product_id")

    assert JoinEngine.should_skip_pair((source,), pk) is True


def test_should_skip_pair_rejects_incompatible_types() -> None:
    """A String column cannot join an Int64 PK."""
    source = make_source("sales", "product_id", col_type="String")
    pk = make_pk("products", "product_id", col_type="Int64")

    assert JoinEngine.should_skip_pair((source,), pk) is True


def test_should_skip_pair_accepts_compatible_candidate() -> None:
    """Different tables with matching base types form a valid join candidate."""
    source = make_source("sales", "item_id", col_type="Int64")
    pk = make_pk("items", "item_id", col_type="Int64")

    assert JoinEngine.should_skip_pair((source,), pk) is False


def test_should_skip_pair_rejects_different_key_concepts() -> None:
    """A low-level entity key must not join to a higher-level group key."""
    source = make_source("transactions", "ItemKey", col_type="Int64")
    pk = make_pk("item_groups", "ItemGroupKey", col_type="Int64")

    assert JoinEngine.should_skip_pair((source,), pk) is True


def test_should_skip_pair_accepts_source_key_with_general_target_concept() -> None:
    """Role-specific source keys can still point to a general dimension key."""
    source = make_source("sales", "OrderDate", col_type="Date")
    pk = make_pk("calendar", "Date", col_type="Date")

    assert JoinEngine.should_skip_pair((source,), pk) is False


def test_should_skip_pair_accepts_target_key_with_prefix_context() -> None:
    """SalesTerritoryKey and TerritoryKey describe the same terminal concept."""
    source = make_source("sales", "TerritoryKey", col_type="Int64")
    pk = make_pk("territory", "SalesTerritoryKey", col_type="Int64")

    assert JoinEngine.should_skip_pair((source,), pk) is False


def test_should_skip_pair_keeps_generic_target_id_possible() -> None:
    """Generic target ids can still be checked by physical coverage."""
    source = make_source("sales", "customer_id", col_type="Int64")
    pk = make_pk("customers", "id", col_type="Int64")

    assert JoinEngine.should_skip_pair((source,), pk) is False


def test_should_skip_pair_rejects_yearly_table_partitions() -> None:
    """Year slices of the same logical table should not become model edges."""
    source = make_source("transactions_2021", "OrderNumber", col_type="String")
    pk = make_pk("transactions_2022", "OrderNumber", col_type="String")

    assert JoinEngine.should_skip_pair((source,), pk) is True


def test_should_skip_pair_handles_nullable_type() -> None:
    """Nullable(Int64) must be treated as Int64 when comparing types."""
    source = make_source("sales", "item_id", col_type="Nullable(Int64)")
    pk = make_pk("items", "item_id", col_type="Int64")

    assert JoinEngine.should_skip_pair((source,), pk) is False


def test_evaluate_join_to_primary_key_computes_physical_coverage() -> None:
    db = MagicMock()
    db.query.return_value = SimpleNamespace(result_rows=[(10, 9, 0.9)])
    engine = JoinEngine(db)

    result = engine.evaluate_join_to_primary_key(
        source_table="sales",
        source_column="customer_id",
        primary_key=make_pk("customers", "customer_id"),
        limit_rows=100,
    )

    assert result.source_non_null_rows == 10
    assert result.matched_rows == 9
    assert result.join_success_ratio == 0.9
    assert "LIMIT 100" in db.query.call_args.args[0]


def test_evaluate_join_rejects_non_unique_target() -> None:
    engine = JoinEngine(MagicMock())
    primary_key = make_pk("customers", "customer_id")
    primary_key.uniqueness_ratio = 0.99

    with pytest.raises(ValueError, match="strictly unique"):
        engine.evaluate_join_to_primary_key("sales", "customer_id", primary_key)


def test_find_primary_key_returns_exact_target_and_rejects_unknown_target() -> None:
    engine = JoinEngine(MagicMock())
    primary_key = make_pk("customers", "customer_id")

    assert engine.find_primary_key([primary_key], "customers", "customer_id") is primary_key
    with pytest.raises(ValueError, match="No primary-key candidate"):
        engine.find_primary_key([primary_key], "products", "product_id")


def test_evaluate_candidates_keeps_only_successful_join_and_sets_scope() -> None:
    db = MagicMock()
    engine = JoinEngine(db)
    primary_key = make_pk("customers", "customer_id")
    source = make_source("sales", "customer_id")
    evaluated = JoinPrimaryKeyCandidate(
        source_table="sales",
        source_column="customer_id",
        target_table="customers",
        target_column="customer_id",
        source_non_null_rows=10,
        matched_rows=10,
        join_success_ratio=1.0,
    )

    with (
        patch.object(engine, "load_column_stats", return_value={}),
        patch.object(engine, "prefilter_source_columns", return_value=[source]),
        patch.object(engine, "evaluate_join_to_primary_key", return_value=evaluated),
    ):
        results = engine.evaluate_candidates(
            [primary_key],
            source_columns=[source],
            max_workers=1,
            analysis_scope="SOURCE",
        )

    assert results == [evaluated]
    assert results[0].analysis_scope == "SOURCE"
    db.close_all.assert_called_once()


def test_prefilter_rejects_values_outside_numeric_key_domain() -> None:
    engine = JoinEngine(MagicMock())
    primary_key = make_pk("customers", "customer_id")
    valid = make_source("sales", "customer_id")
    invalid = make_source("events", "customer_id")
    stats = {
        ("customers", "customer_id"): {
            "column_type": "Int64",
            "distinct_count": 100,
            "min_value": "1",
            "max_value": "100",
        },
        ("sales", "customer_id"): {
            "column_type": "Int64",
            "distinct_count": 50,
            "min_value": "1",
            "max_value": "80",
        },
        ("events", "customer_id"): {
            "column_type": "Int64",
            "distinct_count": 50,
            "min_value": "1",
            "max_value": "500",
        },
    }

    kept = engine.prefilter_source_columns([primary_key], [valid, invalid], stats)

    assert kept == [valid]


def test_store_and_load_join_candidates_preserves_analysis_scope() -> None:
    db = MagicMock()
    engine = JoinEngine(db)
    candidate = JoinPrimaryKeyCandidate(
        source_table="sales",
        source_column="customer_id",
        target_table="customers",
        target_column="customer_id",
        source_non_null_rows=10,
        matched_rows=10,
        join_success_ratio=1.0,
        analysis_scope="SOURCE",
    )

    engine.store_candidates([candidate], clear_existing=False)

    db.insert.assert_called_once()
    db.query.return_value = SimpleNamespace(
        result_rows=[("sales", "customer_id", "customers", "customer_id", 10, 10, 1.0, "SOURCE")]
    )
    loaded = engine.load_candidates("SOURCE")

    assert loaded == [candidate]
