from modeling.decision_model import (
    DecisionModelCandidate,
    DecisionModelEdge,
    DecisionModelType,
)
from validation.topology import TopologyValidator


def edge(source: str, target: str, depth: int = 1) -> DecisionModelEdge:
    return DecisionModelEdge(
        source_table=source,
        target_table=target,
        source_columns=("id",),
        target_columns=("id",),
        join_success_ratio=1.0,
        depth=depth,
    )


def candidate(
    model_type: DecisionModelType,
    facts: tuple[str, ...],
    dimensions: tuple[str, ...],
    edges: tuple[DecisionModelEdge, ...],
) -> DecisionModelCandidate:
    return DecisionModelCandidate(
        model_type=model_type,
        fact_tables=facts,
        dimension_tables=dimensions,
        edges=edges,
        table_count=len(set(facts) | set(dimensions)),
        join_count=len(edges),
        attribute_count=0,
        numeric_attribute_count=0,
    )


def test_topology_accepts_simple_star_model() -> None:
    model = candidate(
        model_type=DecisionModelType.STAR,
        facts=("sales",),
        dimensions=("customers", "products"),
        edges=(
            edge("sales", "customers"),
            edge("sales", "products"),
        ),
    )

    issues = TopologyValidator().validate(model)

    assert issues == []


def test_topology_rejects_fact_to_fact_edge() -> None:
    model = candidate(
        model_type=DecisionModelType.CONSTELLATION,
        facts=("sales", "returns"),
        dimensions=("products",),
        edges=(
            edge("sales", "products"),
            edge("sales", "returns"),
        ),
    )

    issues = TopologyValidator().validate(model)

    assert {issue.rule_name for issue in issues} == {"NO_FACT_TO_FACT_EDGE"}


def test_topology_rejects_cycles() -> None:
    model = candidate(
        model_type=DecisionModelType.SNOWFLAKE,
        facts=("sales",),
        dimensions=("products", "categories"),
        edges=(
            edge("sales", "products"),
            edge("products", "categories", depth=2),
            edge("categories", "products", depth=2),
        ),
    )

    issues = TopologyValidator().validate(model)

    assert "NO_CYCLE" in {issue.rule_name for issue in issues}


def test_cycle_detection_handles_large_acyclic_graph_without_recursion_error() -> None:
    graph = {f"node_{index}": [f"node_{index + 1}"] for index in range(1_500)}

    cycles = TopologyValidator.detect_cycles(graph)

    assert cycles == []
