from inference.key_ranking import KeyRankingPolicy


# ── Tests is_numeric_type ──────────────────────────────────────────────────────

def test_is_numeric_type_detects_numbers() -> None:
    policy = KeyRankingPolicy()

    assert policy.is_numeric_type("Int64") is True
    assert policy.is_numeric_type("UInt32") is True
    assert policy.is_numeric_type("Float64") is True
    assert policy.is_numeric_type("Decimal(10, 2)") is True


def test_is_numeric_type_rejects_non_numbers() -> None:
    policy = KeyRankingPolicy()

    assert policy.is_numeric_type("String") is False
    assert policy.is_numeric_type("Date") is False
    assert policy.is_numeric_type("DateTime") is False


def test_is_numeric_type_handles_nullable() -> None:
    """Nullable(Float64) must be recognised as numeric."""
    policy = KeyRankingPolicy()

    assert policy.is_numeric_type("Nullable(Float64)") is True


# ── Tests count_numeric_columns ───────────────────────────────────────────────

def test_count_numeric_columns_counts_correctly() -> None:
    policy = KeyRankingPolicy()

    assert policy.count_numeric_columns(("Int64", "String", "Float64")) == 2
    assert policy.count_numeric_columns(("String", "Date")) == 0
    assert policy.count_numeric_columns(("Int64",)) == 1


# ── Tests build_candidate ─────────────────────────────────────────────────────

def test_build_candidate_computes_confidence() -> None:
    """Confidence must follow: 0.7 * uniqueness_ratio + 0.3 * identifiability_score."""
    policy = KeyRankingPolicy()

    candidate = policy.build_candidate(
        database_name="lab_db",
        table_name="customers",
        column_names=("customer_id",),
        column_types=("Int64",),
        rows=1000,
        null_ratio=0.0,
        uniqueness_ratio=1.0,
        identifiability_score=1.0,
        low_cardinality_columns=set(),
    )

    # 0.7 * 1.0 + 0.3 * 1.0 = 1.0
    assert candidate.confidence == 1.0
    assert candidate.numeric_column_count == 1
    assert candidate.low_cardinality_column_count == 0


def test_build_candidate_penalises_low_cardinality_columns() -> None:
    """A low-cardinality column must increment low_cardinality_column_count."""
    policy = KeyRankingPolicy()

    candidate = policy.build_candidate(
        database_name="lab_db",
        table_name="orders",
        column_names=("status",),
        column_types=("String",),
        rows=500,
        null_ratio=0.0,
        uniqueness_ratio=0.05,
        identifiability_score=0.1,
        low_cardinality_columns={("orders", "status")},  # flagged as low-cardinality
    )

    assert candidate.low_cardinality_column_count == 1


# ── Tests rank ────────────────────────────────────────────────────────────────

def test_rank_prefers_minimal_keys() -> None:
    """A single-column key must be ranked above a composite key at equal score."""
    policy = KeyRankingPolicy()

    single_key = policy.build_candidate(
        database_name="db", table_name="t",
        column_names=("id",), column_types=("Int64",),
        rows=100, null_ratio=0.0, uniqueness_ratio=1.0,
        identifiability_score=0.8, low_cardinality_columns=set(),
    )
    composite_key = policy.build_candidate(
        database_name="db", table_name="t",
        column_names=("col_a", "col_b"), column_types=("Int64", "String"),
        rows=100, null_ratio=0.0, uniqueness_ratio=1.0,
        identifiability_score=0.8, low_cardinality_columns=set(),
    )

    ranked = policy.rank([composite_key, single_key])

    # The single-column key (1 column) must come first.
    assert ranked[0].column_names == ("id",)


# ── Tests select_best_by_table ────────────────────────────────────────────────

def test_select_best_by_table_returns_one_candidate_per_table() -> None:
    """Only the best candidate per table must be kept."""
    policy = KeyRankingPolicy()

    c1 = policy.build_candidate(
        database_name="db", table_name="orders",
        column_names=("order_id",), column_types=("Int64",),
        rows=500, null_ratio=0.0, uniqueness_ratio=1.0,
        identifiability_score=0.9, low_cardinality_columns=set(),
    )
    c2 = policy.build_candidate(
        database_name="db", table_name="orders",
        column_names=("order_code",), column_types=("String",),
        rows=500, null_ratio=0.0, uniqueness_ratio=1.0,
        identifiability_score=0.5, low_cardinality_columns=set(),
    )

    best = policy.select_best_by_table([c1, c2])

    assert len(best) == 1
    assert "orders" in best
    # order_id (Int64, numeric) must be preferred over order_code (String).
    assert best["orders"].column_names == ("order_id",)
