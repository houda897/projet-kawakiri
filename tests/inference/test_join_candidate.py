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
