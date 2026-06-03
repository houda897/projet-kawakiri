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
