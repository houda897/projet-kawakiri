from unittest.mock import MagicMock

from core.clickhouse_manager import CH_DB
from inference.adjacency import AdjacencyEdge, AdjacencyMatrixEngine
from inference.join_candidate import JoinPrimaryKeyCandidate


class IdentitySemanticEngine:
    def enrich_edges_with_semantics(
        self,
        edges: list[AdjacencyEdge],
    ) -> list[AdjacencyEdge]:
        return edges


def test_build_edges_from_join_candidates() -> None:
    engine = AdjacencyMatrixEngine(db=None, semantic_engine=IdentitySemanticEngine())  # type: ignore[arg-type]

    joins = [
        JoinPrimaryKeyCandidate(
            source_table="sales",
            source_column="customer_id",
            target_table="customers",
            target_column="id",
            source_non_null_rows=100,
            matched_rows=90,
            join_success_ratio=0.9,
        )
    ]

    edges = engine.build_edges_from_join_candidates(joins)

    assert len(edges) == 1
    assert edges[0].source_table == "sales"
    assert edges[0].target_table == "customers"
    assert edges[0].source_columns == ("customer_id",)
    assert edges[0].target_columns == ("id",)
    assert edges[0].join_success_ratio == 0.9


def test_build_matrix_keeps_max_score() -> None:
    engine = AdjacencyMatrixEngine(db=None, semantic_engine=IdentitySemanticEngine())  # type: ignore[arg-type]

    edges = [
        AdjacencyEdge("sales", "date_dim", ("created_at",), ("date",), 0.8, None, "CONFIRMED"),
        AdjacencyEdge("sales", "date_dim", ("updated_at",), ("date",), 0.95, None, "CONFIRMED"),
        AdjacencyEdge("sales", "customers", ("customer_id",), ("id",), 0.99, None, "CONFIRMED"),
        AdjacencyEdge("sales", "weak_dim", ("weak_id",), ("id",), 1.0, None, "WEAK"),
    ]

    matrix = engine.build_matrix(edges)

    # Matrix should collapse duplicate target tables and keep the max ratio
    assert "sales" in matrix
    assert matrix["sales"]["date_dim"] == 0.95
    assert matrix["sales"]["customers"] == 0.99
    assert len(matrix["sales"]) == 2
    assert "weak_dim" not in matrix["sales"]


def test_build_matrix_keeps_profiled_tables_without_edges() -> None:
    engine = AdjacencyMatrixEngine(db=None, semantic_engine=IdentitySemanticEngine())  # type: ignore[arg-type]

    edges = [
        AdjacencyEdge("sales", "customers", ("customer_id",), ("id",), 0.99, None, "CONFIRMED"),
    ]

    matrix = engine.build_matrix(edges, table_names={"sales", "customers", "isolated_reference"})

    assert set(matrix) == {"sales", "customers", "isolated_reference"}
    assert matrix["isolated_reference"] == {}


def test_print_edges_accepts_missing_hybrid_score() -> None:
    edges = [
        AdjacencyEdge("sales", "customers", ("customer_id",), ("id",), 0.99, None, "CONFIRMED"),
    ]

    AdjacencyMatrixEngine.print_edges(edges)


def test_store_edges_scopes_rows_by_database() -> None:
    db = MagicMock()
    engine = AdjacencyMatrixEngine(db=db, semantic_engine=IdentitySemanticEngine())
    edges = [
        AdjacencyEdge("sales", "customers", ("customer_id",), ("id",), 0.99, None, "CONFIRMED"),
    ]

    engine.store_edges(edges)

    assert db.command.call_args.kwargs["parameters"] == {"database": CH_DB}
    inserted_rows = db.insert.call_args.args[1]
    column_names = db.insert.call_args.kwargs["column_names"]
    assert inserted_rows[0][0] == CH_DB
    assert column_names[0] == "database_name"
