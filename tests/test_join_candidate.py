from inference.join_candidate import JoinPrimaryKeyCandidate


def test_join_primary_key_candidate_stores_metrics() -> None:
    candidate = JoinPrimaryKeyCandidate(
        source_table="sales",
        source_column="customer_id",
        target_table="customers",
        target_column="customer_id",
        source_non_null_rows=6,
        matched_rows=6,
        join_success_ratio=1.0,
    )

    assert candidate.source_table == "sales"
    assert candidate.target_table == "customers"
    assert candidate.join_success_ratio == 1.0
