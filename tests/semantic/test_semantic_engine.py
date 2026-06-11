from unittest.mock import patch

import pytest
from config.scoring import SEMANTIC_THRESHOLDS, SEMANTIC_WEIGHTS
from inference.adjacency import AdjacencyEdge
from semantic.semantic_engine import SemanticEngine


@pytest.fixture
def semantic_engine():
    return SemanticEngine()


def test_normalize_column_name(semantic_engine):
    """Test the normalization of column names and the removal of noise (prefixes/suffixes)."""
    assert semantic_engine.normalize_column_name("CustomerName") == "customername"

    assert semantic_engine.normalize_column_name("First_Name-Last") == "firstnamelast"

    assert semantic_engine.normalize_column_name("id_customer") == "customer"
    assert semantic_engine.normalize_column_name("fk_product_id") == "product"
    assert semantic_engine.normalize_column_name("pk_order") == "order"

    assert semantic_engine.normalize_column_name("customer_id") == "customer"
    assert semantic_engine.normalize_column_name("territory_key") == "territory"
    assert semantic_engine.normalize_column_name("store_fk") == "store"

    assert semantic_engine.normalize_column_name("fk_id_product_key_id") == "product"

    assert semantic_engine.normalize_column_name("") == ""
    assert semantic_engine.normalize_column_name(None) == ""


def test_compute_similarity(semantic_engine):
    """Test the computation of similarity scores between column names."""
    assert semantic_engine.compute_similarity("CustomerID", "customer_id") == 1.0

    score = semantic_engine.compute_similarity("Product", "ProductSub")
    assert 0.0 < score < 1.0

    assert semantic_engine.compute_similarity("OrderDate", "StockDate") == 1.0
    assert semantic_engine.compute_similarity("Date", "ReturnDate") == 1.0


@patch.dict(SEMANTIC_WEIGHTS, {"join_success_ratio": 0.34, "semantic_similarity": 0.66})
@patch.dict(SEMANTIC_THRESHOLDS, {"confirmed": 0.8, "coincidence": 0.5})
def test_enrich_edges_with_semantics(semantic_engine):
    """Test the enrichment of edges with semantic similarity and the assignment of evidence labels."""
    edges = [
        AdjacencyEdge(
            source_table="Sales",
            target_table="Customers",
            source_columns=("CustomerKey",),
            target_columns=("CustomerKey",),
            join_success_ratio=1.0,
            hybrid_score=0.0,
            evidence="",
        ),
        AdjacencyEdge(
            source_table="Returns",
            target_table="Products",
            source_columns=("TerritoryKey",),
            target_columns=("ProductKey",),
            join_success_ratio=1.0,
            hybrid_score=0.0,
            evidence="",
        ),
        AdjacencyEdge(
            source_table="Sales",
            target_table="DimA",
            source_columns=("Price",),
            target_columns=("CustomerName",),
            join_success_ratio=0.95,
            hybrid_score=0.0,
            evidence="",
        ),
    ]

    enriched = semantic_engine.enrich_edges_with_semantics(edges)

    assert enriched[0].evidence == "CONFIRMED"
    assert enriched[0].hybrid_score == 1.0

    assert enriched[1].evidence == "COINCIDENCE"

    assert enriched[2].evidence == "WEAK"
