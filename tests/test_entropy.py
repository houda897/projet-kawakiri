from profiling.entropy import EntropyResult


def test_entropy_result_object_stores_metrics() -> None:
    result = EntropyResult(
        db="lab_db",
        table="sales",
        column="sale_id",
        ch_type="Int64",
        rows=10,
        non_null_rows=10,
        distinct_count=10,
        entropy=3.3219,
    )

    assert result.column == "sale_id"
    assert result.entropy == 3.3219
    assert result.distinct_count == 10
