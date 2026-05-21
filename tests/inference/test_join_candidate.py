from inference.join_candidate import JoinPrimaryKeyCandidate, JoinEngine, SourceColumn
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


# ── Tests JoinEngine.should_skip_pair ─────────────────────────────────────────

def test_should_skip_pair_rejects_same_table() -> None:
    """A column must not be compared against a PK from the same table."""
    source = make_source("sales", "product_id")
    pk = make_pk("sales", "product_id")  

    assert JoinEngine.should_skip_pair(source, pk) is True


def test_should_skip_pair_rejects_incompatible_types() -> None:
    """A String column cannot join an Int64 PK."""
    source = make_source("sales", "product_id", col_type="String")
    pk = make_pk("products", "product_id", col_type="Int64") 

    assert JoinEngine.should_skip_pair(source, pk) is True


def test_should_skip_pair_accepts_compatible_candidate() -> None:
    """Different tables with matching base types form a valid join candidate."""
    source = make_source("sales", "product_id", col_type="Int64")
    pk = make_pk("products", "product_id", col_type="Int64")

    assert JoinEngine.should_skip_pair(source, pk) is False


def test_should_skip_pair_handles_nullable_type() -> None:
    """Nullable(Int64) must be treated as Int64 when comparing types."""
    source = make_source("sales", "product_id", col_type="Nullable(Int64)")
    pk = make_pk("products", "product_id", col_type="Int64")

    assert JoinEngine.should_skip_pair(source, pk) is False
