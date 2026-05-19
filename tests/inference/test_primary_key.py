from inference.primary_key import PrimaryKeyCandidate


def test_primary_key_candidate_object_stores_evidence() -> None:
    candidate = PrimaryKeyCandidate(
        database_name="lab_db",
        table_name="customers",
        column_name="customer_id",
        column_type="Int64",
        rows=1000,
        null_ratio=0.0,
        uniqueness_ratio=1.0,
        confidence=1.0,
        reason="confidence=uniqueness_ratio*(1-null_ratio)",
    )

    assert candidate.table_name == "customers"
    assert candidate.column_name == "customer_id"
    assert candidate.confidence == 1.0
