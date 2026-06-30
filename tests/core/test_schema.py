from core.schema import (
    is_continuous_numeric_type,
    is_numeric_type,
    is_temporal_type,
    list_tables,
    normalize_clickhouse_type,
    q_ident,
)


class FakeQueryResult:
    def __init__(self, rows: list[tuple]):
        self.result_rows = rows


class FakeDb:
    def __init__(self):
        self.last_sql = ""

    def query(self, sql: str, parameters: dict | None = None) -> FakeQueryResult:
        self.last_sql = sql
        return FakeQueryResult([("observations",)])


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


def test_is_continuous_numeric_type_handles_wrapped_clickhouse_types() -> None:
    assert is_continuous_numeric_type("Nullable(Decimal(10, 2))")
    assert is_continuous_numeric_type("LowCardinality(Nullable(Float64))")
    assert not is_continuous_numeric_type("UInt64")


def test_is_temporal_type_handles_wrapped_clickhouse_types() -> None:
    assert is_temporal_type("Nullable(Date)")
    assert is_temporal_type("LowCardinality(Nullable(DateTime64(3)))")
    assert not is_temporal_type("String")


def test_list_tables_excludes_internal_logical_tables_by_default() -> None:
    db = FakeDb()

    tables = list_tables(db)

    assert tables == ["observations"]
    assert "NOT startsWith(name, 'logical_')" in db.last_sql


def test_list_tables_can_include_internal_logical_tables() -> None:
    db = FakeDb()

    list_tables(db, include_internal=True)

    assert "NOT startsWith(name, 'logical_')" not in db.last_sql
