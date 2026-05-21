from inference.primary_key import PrimaryKeyCandidate


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
