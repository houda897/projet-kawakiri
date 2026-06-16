from types import SimpleNamespace
from unittest.mock import MagicMock

from modeling.candidate_builder import DecisionModelCandidateBuilder
from modeling.decision_model import DecisionModelEdge, DecisionModelType


def edge(
    source: str,
    target: str,
    source_col: str = "id",
    target_col: str = "id",
    depth: int = 1,
) -> DecisionModelEdge:
    return DecisionModelEdge(
        source_table=source,
        target_table=target,
        source_columns=(source_col,),
        target_columns=(target_col,),
        join_success_ratio=1.0,
        depth=depth,
    )


def test_build_star_candidate_from_fact_to_dimensions() -> None:
    builder = DecisionModelCandidateBuilder(db=None)  # type: ignore[arg-type]
    roles = {
        "sales": "FACT",
        "customers": "DIMENSION",
        "products": "DIMENSION",
        "returns": "FACT",
    }
    edges = [
        edge("sales", "customers", "customer_id", "customer_id"),
        edge("sales", "products", "product_id", "product_id"),
        edge("customers", "sales", "customer_id", "customer_id"),
    ]
    column_counts = {
        "sales": {"attribute_count": 5, "numeric_attribute_count": 3},
        "customers": {"attribute_count": 4, "numeric_attribute_count": 1},
        "products": {"attribute_count": 6, "numeric_attribute_count": 2},
    }

    candidates = builder.build_star_candidates(roles, edges, column_counts)

    assert len(candidates) == 1
    candidate = candidates[0]
    assert candidate.model_type == DecisionModelType.STAR
    assert candidate.fact_tables == ("sales",)
    assert candidate.dimension_tables == ("customers", "products")
    assert candidate.table_count == 3
    assert candidate.join_count == 2
    assert candidate.attribute_count == 15
    assert candidate.numeric_attribute_count == 6


def test_build_star_candidate_ignores_isolated_tables() -> None:
    builder = DecisionModelCandidateBuilder(db=None)  # type: ignore[arg-type]
    roles = {
        "sales": "FACT",
        "customers": "DIMENSION",
        "geography": "ISOLATED",
    }
    edges = [
        edge("sales", "customers", "customer_id", "customer_id"),
        edge("sales", "geography", "zip_code", "zip_code"),
    ]
    column_counts = {
        "sales": {"attribute_count": 5, "numeric_attribute_count": 3},
        "customers": {"attribute_count": 4, "numeric_attribute_count": 1},
        "geography": {"attribute_count": 5, "numeric_attribute_count": 2},
    }

    candidates = builder.build_star_candidates(roles, edges, column_counts)

    assert len(candidates) == 1
    assert candidates[0].dimension_tables == ("customers",)
    assert candidates[0].table_count == 2


def test_model_id_changes_when_dimensions_change() -> None:
    builder = DecisionModelCandidateBuilder(db=None)  # type: ignore[arg-type]

    candidate_a = builder.to_candidate(
        model_type=DecisionModelType.STAR,
        fact_tables=("sales",),
        dimension_tables=("customers",),
        edges=(edge("sales", "customers", "customer_id", "customer_id"),),
        column_counts={},
    )
    candidate_b = builder.to_candidate(
        model_type=DecisionModelType.STAR,
        fact_tables=("sales",),
        dimension_tables=("products",),
        edges=(edge("sales", "products", "product_id", "product_id"),),
        column_counts={},
    )

    assert candidate_a.model_id != candidate_b.model_id
    assert candidate_a.model_id.startswith("star_sales_")
    assert candidate_b.model_id.startswith("star_sales_")


def test_build_snowflake_candidate_includes_dimension_to_dimension_edges() -> None:
    builder = DecisionModelCandidateBuilder(db=None)  # type: ignore[arg-type]
    roles = {
        "sales": "FACT",
        "products": "DIMENSION",
        "categories": "DIMENSION",
    }
    edges = [
        edge("sales", "products", "product_id", "product_id"),
        edge("products", "categories", "category_id", "category_id"),
    ]
    column_counts = {
        "sales": {"attribute_count": 5, "numeric_attribute_count": 3},
        "products": {"attribute_count": 6, "numeric_attribute_count": 2},
        "categories": {"attribute_count": 2, "numeric_attribute_count": 1},
    }

    candidates = builder.build_snowflake_candidates(roles, edges, column_counts)

    assert len(candidates) == 1
    candidate = candidates[0]
    assert candidate.model_type == DecisionModelType.SNOWFLAKE
    assert candidate.fact_tables == ("sales",)
    assert candidate.dimension_tables == ("categories", "products")
    assert candidate.join_count == 2
    assert {edge.depth for edge in candidate.edges} == {1, 2}


def test_build_constellation_keeps_all_dimensions_of_related_facts() -> None:
    builder = DecisionModelCandidateBuilder(db=None)  # type: ignore[arg-type]
    roles = {
        "sales": "FACT",
        "returns": "FACT",
        "date_dim": "DIMENSION",
        "products": "DIMENSION",
        "customers": "DIMENSION",
    }
    edges = [
        edge("sales", "date_dim", "order_date", "date"),
        edge("sales", "products", "product_id", "product_id"),
        edge("sales", "customers", "customer_id", "customer_id"),
        edge("returns", "date_dim", "return_date", "date"),
        edge("returns", "products", "product_id", "product_id"),
    ]
    column_counts = {
        "sales": {"attribute_count": 5, "numeric_attribute_count": 3},
        "returns": {"attribute_count": 4, "numeric_attribute_count": 2},
        "date_dim": {"attribute_count": 1, "numeric_attribute_count": 0},
        "products": {"attribute_count": 6, "numeric_attribute_count": 2},
        "customers": {"attribute_count": 4, "numeric_attribute_count": 1},
    }

    candidates = builder.build_constellation_candidates(roles, edges, column_counts)

    assert len(candidates) == 1
    candidate = candidates[0]
    assert candidate.model_type == DecisionModelType.CONSTELLATION
    assert candidate.fact_tables == ("returns", "sales")
    assert candidate.dimension_tables == ("customers", "date_dim", "products")
    assert candidate.join_count == 5


def test_load_table_roles_reads_stored_metadata() -> None:
    db = MagicMock()
    db.query.return_value = SimpleNamespace(
        result_rows=[
            ("sales", "FACT"),
            ("customers", "DIMENSION"),
        ]
    )
    builder = DecisionModelCandidateBuilder(db)

    roles = builder.load_table_roles()

    assert roles == {
        "sales": "FACT",
        "customers": "DIMENSION",
    }
    sql = db.query.call_args[0][0]
    assert "table_roles" in sql


def test_load_table_roles_requires_stored_roles() -> None:
    db = MagicMock()
    db.query.return_value = SimpleNamespace(result_rows=[])
    builder = DecisionModelCandidateBuilder(db)

    try:
        builder.load_table_roles()
    except ValueError as exc:
        assert "Run infer-table-roles" in str(exc)
    else:
        raise AssertionError("Expected ValueError when stored table roles are missing")


def test_store_candidates_persists_models_and_edges() -> None:
    db = MagicMock()
    builder = DecisionModelCandidateBuilder(db)
    candidate = builder.to_candidate(
        model_type=DecisionModelType.STAR,
        fact_tables=("sales",),
        dimension_tables=("customers",),
        edges=(edge("sales", "customers", "customer_id", "customer_id"),),
        column_counts={
            "sales": {"attribute_count": 5, "numeric_attribute_count": 3},
            "customers": {"attribute_count": 4, "numeric_attribute_count": 1},
        },
    )

    builder.store_candidates([candidate])

    assert db.command.call_count == 2
    assert db.insert.call_count == 2
    assert db.insert.call_args_list[0][0][0].endswith(".decision_model_candidates")
    assert db.insert.call_args_list[1][0][0].endswith(".decision_model_edges")


def test_store_candidates_clears_metadata_when_empty() -> None:
    db = MagicMock()
    builder = DecisionModelCandidateBuilder(db)

    builder.store_candidates([])

    assert db.command.call_count == 2
    db.insert.assert_not_called()


def test_load_candidates_reconstructs_models_and_edges() -> None:
    db = MagicMock()
    db.query.side_effect = [
        SimpleNamespace(
            result_rows=[
                (
                    "star_sales",
                    "STAR",
                    "sales",
                    "customers,products",
                    3,
                    2,
                    15,
                    6,
                )
            ]
        ),
        SimpleNamespace(
            result_rows=[
                (
                    "star_sales",
                    "sales",
                    "customers",
                    "customer_id",
                    "customer_id",
                    1.0,
                    1,
                ),
                (
                    "star_sales",
                    "sales",
                    "products",
                    "product_id",
                    "product_id",
                    0.98,
                    1,
                ),
            ]
        ),
    ]
    builder = DecisionModelCandidateBuilder(db)

    candidates = builder.load_candidates()

    assert len(candidates) == 1
    candidate = candidates[0]
    assert candidate.model_type == DecisionModelType.STAR
    assert candidate.fact_tables == ("sales",)
    assert candidate.dimension_tables == ("customers", "products")
    assert candidate.table_count == 3
    assert candidate.join_count == 2
    assert len(candidate.edges) == 2
    assert candidate.edges[0].source_columns == ("customer_id",)
