from profiling.basic_profile import ColumnProfile


def test_column_profile_object_stores_metrics() -> None:
    profile = ColumnProfile(
        database_name="lab_db",
        table_name="customers",
        column_name="customer_id",
        column_type="Int64",
        rows=4,
        non_null_rows=4,
        null_rows=0,
        null_ratio=0.0,
        distinct_count=4,
        uniqueness_ratio=1.0,
        min_value="1",
        max_value="4",
    )

    assert profile.column_name == "customer_id"
    assert profile.uniqueness_ratio == 1.0
    assert profile.null_ratio == 0.0
