from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from inference.key_ranking import RankedKeyCandidate
from inference.primary_key import PrimaryKeyCandidate, PrimaryKeyEngine


class FakeQueryResult:
    def __init__(self, rows: list[tuple]):
        self.result_rows = rows


class FakeDb:
    def __init__(self, rows: list[tuple]):
        self.rows = rows
        self.last_sql = ""
        self.last_parameters = {}

    def query(self, sql: str, parameters: dict | None = None) -> FakeQueryResult:
        self.last_sql = sql
        self.last_parameters = parameters or {}
        return FakeQueryResult(self.rows)


def test_primary_key_candidate_stores_all_fields() -> None:
    candidate = PrimaryKeyCandidate(
        database_name="lab_db",
        table_name="customers",
        column_name="customer_id",
        column_type="Int64",
        rows=1000,
        null_ratio=0.0,
        uniqueness_ratio=1.0,
        identifiability_score=0.95,
        confidence=1.0,
        reason="hard_rule=unique_and_complete",
    )

    assert candidate.database_name == "lab_db"
    assert candidate.table_name == "customers"
    assert candidate.column_name == "customer_id"
    assert candidate.column_type == "Int64"
    assert candidate.rows == 1000
    assert candidate.null_ratio == 0.0
    assert candidate.uniqueness_ratio == 1.0
    assert candidate.identifiability_score == 0.95
    assert candidate.confidence == 1.0


def test_primary_key_candidate_with_low_confidence() -> None:
    """Un candidat avec un score d'identifiabilité faible doit quand même être créé."""
    candidate = PrimaryKeyCandidate(
        database_name="lab_db",
        table_name="orders",
        column_name="order_ref",
        column_type="String",
        rows=500,
        null_ratio=0.01,
        uniqueness_ratio=0.99,
        identifiability_score=0.60,
        confidence=0.87,
        reason="hard_rule=unique_and_complete",
    )

    assert candidate.table_name == "orders"
    assert candidate.confidence == 0.87


def test_print_candidates_distinguishes_preliminary_key_candidate() -> None:
    candidate = PrimaryKeyCandidate(
        database_name="lab_db",
        table_name="orders",
        column_name="customer_id",
        column_type="String",
        rows=100,
        null_ratio=0.0,
        uniqueness_ratio=1.0,
        identifiability_score=0.9,
        confidence=1.0,
        reason="preliminary_source_key",
        analysis_scope="SOURCE",
        is_official=False,
    )

    with patch("inference.primary_key.logger.info") as log_info:
        PrimaryKeyEngine.print_candidates([candidate])

    assert log_info.call_args.args[1] == "KEY_CANDIDATE"


def test_load_candidates_reads_stored_primary_keys() -> None:
    db = FakeDb(
        rows=[
            (
                "lab_db",
                "customers",
                "customer_id",
                "Int64",
                1000,
                0.0,
                1.0,
                0.95,
                0.98,
                "stored_candidate",
            )
        ]
    )
    engine = PrimaryKeyEngine(db)  # type: ignore[arg-type]

    candidates = engine.load_candidates()

    assert len(candidates) == 1
    assert candidates[0].table_name == "customers"
    assert candidates[0].column_name == "customer_id"
    assert "primary_key_candidates" in db.last_sql
    assert db.last_parameters["database"]


def test_logical_table_key_overrides_accidental_simple_key() -> None:
    simple_candidate = RankedKeyCandidate(
        database_name="lab_db",
        table_name="logical_shipping",
        column_names=("postal_code",),
        column_types=("String",),
        rows=1000,
        null_ratio=0.0,
        uniqueness_ratio=0.998,
        identifiability_score=0.95,
        key_like_column_count=1,
        numeric_column_count=0,
        measure_like_column_count=0,
        low_cardinality_column_count=0,
        confidence=0.98,
        rank_reason="simple_nearly_unique",
    )
    logical_candidate = RankedKeyCandidate(
        database_name="lab_db",
        table_name="logical_shipping",
        column_names=("postal_code", "city"),
        column_types=("String", "String"),
        rows=1000,
        null_ratio=0.0,
        uniqueness_ratio=1.0,
        identifiability_score=0.96,
        key_like_column_count=1,
        numeric_column_count=0,
        measure_like_column_count=0,
        low_cardinality_column_count=0,
        confidence=0.99,
        rank_reason="logical_dimension_determinant",
    )

    best_by_table = PrimaryKeyEngine.apply_logical_table_key_overrides(
        {"logical_shipping": simple_candidate},
        [logical_candidate],
    )

    assert best_by_table["logical_shipping"].column_names == ("postal_code", "city")


def test_compute_key_shape_requires_complete_exact_tuple() -> None:
    db = MagicMock()
    db.query.return_value = SimpleNamespace(result_rows=[(100, 0, 100)])
    engine = PrimaryKeyEngine(db)

    rows, null_ratio, uniqueness_ratio = engine.compute_key_shape(
        "order_items",
        ("order_id", "line_id"),
    )

    assert rows == 100
    assert null_ratio == 0.0
    assert uniqueness_ratio == 1.0
    sql = db.query.call_args.args[0]
    assert "uniqExact(tuple" in sql
    assert "order_id" in sql and "line_id" in sql


def test_infer_candidates_marks_source_candidates_as_preliminary() -> None:
    db = MagicMock()
    engine = PrimaryKeyEngine(db)
    ranked = RankedKeyCandidate(
        database_name="lab_db",
        table_name="orders",
        column_names=("order_id",),
        column_types=("String",),
        rows=100,
        null_ratio=0.0,
        uniqueness_ratio=1.0,
        identifiability_score=0.95,
        key_like_column_count=1,
        numeric_column_count=0,
        measure_like_column_count=0,
        low_cardinality_column_count=0,
        confidence=1.0,
        rank_reason="exact_source_key",
    )
    engine.infer_ranked_simple_candidates = MagicMock(return_value=[ranked])
    engine.find_tables_without_candidates = MagicMock(return_value=[])
    engine.low_cardinality_analyzer.find_columns = MagicMock(return_value=[])
    engine.low_cardinality_analyzer.to_column_name_set = MagicMock(return_value=set())
    engine.composite_key_engine.generate_composite_candidates = MagicMock(return_value=[])

    candidates = engine.infer_candidates(
        select_best=False,
        analysis_scope="SOURCE",
    )

    assert len(candidates) == 1
    assert candidates[0].analysis_scope == "SOURCE"
    assert candidates[0].is_official is False
    assert candidates[0].column_name == "order_id"


def test_infer_ranked_simple_candidates_rechecks_exact_uniqueness() -> None:
    db = MagicMock()
    db.query.return_value = SimpleNamespace(
        result_rows=[("lab_db", "orders", "order_id", "String", 100, 0.0, 1.0, 0.95)]
    )
    engine = PrimaryKeyEngine(db)
    engine.low_cardinality_analyzer.find_columns = MagicMock(return_value=[])
    engine.compute_key_shape = MagicMock(return_value=(100, 0.0, 1.0))

    candidates = engine.infer_ranked_simple_candidates(table_names={"orders"})

    assert len(candidates) == 1
    assert candidates[0].column_names == ("order_id",)
    engine.compute_key_shape.assert_called_once_with("orders", ("order_id",))


def test_load_column_types_preserves_determinant_order() -> None:
    db = MagicMock()
    db.query.return_value = SimpleNamespace(
        result_rows=[("line_id", "Int64"), ("order_id", "String")]
    )
    engine = PrimaryKeyEngine(db)

    result = engine.load_column_types("items", ("order_id", "line_id"))

    assert result == ("String", "Int64")


def test_infer_logical_table_key_uses_complete_declared_determinant() -> None:
    db = MagicMock()
    db.query.side_effect = [
        SimpleNamespace(result_rows=[("logical_shipping", "postal_code, city")]),
        SimpleNamespace(result_rows=[("postal_code", "String"), ("city", "String")]),
        SimpleNamespace(result_rows=[(100, 0, 100)]),
        SimpleNamespace(result_rows=[(0.92,)]),
    ]
    engine = PrimaryKeyEngine(db)

    candidates = engine.infer_logical_table_key_candidates(
        threshold=0.999999999,
        low_cardinality_columns=set(),
    )

    assert len(candidates) == 1
    assert candidates[0].column_names == ("postal_code", "city")
    assert candidates[0].uniqueness_ratio == 1.0
