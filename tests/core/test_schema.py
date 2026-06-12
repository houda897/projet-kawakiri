from core.schema import is_numeric_type, normalize_clickhouse_type, q_ident


def test_q_ident_escapes_clickhouse_identifier() -> None:
    assert q_ident("table") == "`table`"
    assert q_ident("a`b") == "`a``b`"


def test_normalize_clickhouse_type_unwraps_nested_wrappers() -> None:
    assert normalize_clickhouse_type("Nullable(Int64)") == "Int64"
    assert normalize_clickhouse_type("LowCardinality(String)") == "String"
    assert normalize_clickhouse_type("LowCardinality(Nullable(UInt64))") == "UInt64"


def test_is_numeric_type_handles_wrapped_clickhouse_types() -> None:
    assert is_numeric_type("Nullable(Decimal(10, 2))")
    assert is_numeric_type("LowCardinality(Nullable(UInt64))")
    assert not is_numeric_type("Nullable(String)")
