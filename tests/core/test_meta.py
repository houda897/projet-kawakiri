from types import SimpleNamespace
from unittest.mock import MagicMock

from core.meta import load_confirmed_adjacency_edges


def test_load_confirmed_adjacency_edges_filters_by_database() -> None:
    db = MagicMock()
    db.query.return_value = SimpleNamespace(
        result_rows=[
            ("sales", "customers", "customer_id", "id", 0.99),
        ]
    )

    edges = load_confirmed_adjacency_edges(db, database="dataset_a")

    assert len(edges) == 1
    assert edges[0].source_table == "sales"
    assert db.query.call_args.kwargs["parameters"] == {"database": "dataset_a"}
