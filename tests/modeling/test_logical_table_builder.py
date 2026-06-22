from inference.functional_group_builder import FunctionalColumnGroup
from modeling.logical_table_builder import LogicalTableBuilder


class FakeDb:
    def __init__(self):
        self.commands = []
        self.inserts = []

    def command(self, sql: str):
        self.commands.append(sql)

    def insert(self, table: str, rows: list, column_names: list[str]):
        self.inserts.append((table, rows, column_names))


def test_materialize_logical_group_uses_distinct_projection() -> None:
    db = FakeDb()
    builder = LogicalTableBuilder(db)
    group = FunctionalColumnGroup(
        database_name="lab_db",
        source_table="observations",
        group_name="logical_observations_station_id",
        determinant_columns=("station_id",),
        dependent_columns=("station_name", "latitude"),
        confidence=0.8,
        reason="functional_dependency",
    )
    logical_table = builder.to_logical_table(group)

    builder.materialize(logical_table, group)

    create_sql = db.commands[1]
    assert "CREATE TABLE" in create_sql
    assert "SELECT DISTINCT" in create_sql
    assert "`station_id`, `station_name`, `latitude`" in create_sql


def test_store_logical_tables_records_table_and_column_metadata() -> None:
    db = FakeDb()
    builder = LogicalTableBuilder(db)
    group = FunctionalColumnGroup(
        database_name="lab_db",
        source_table="observations",
        group_name="logical_observations_fact",
        determinant_columns=("station_id", "date_id"),
        dependent_columns=("temperature",),
        confidence=0.75,
        reason="functional_dependency_group",
    )

    builder.store_logical_tables([builder.to_logical_table(group)])

    assert len(db.inserts) == 2
    table_insert = db.inserts[0]
    column_insert = db.inserts[1]
    assert table_insert[1][0][1] == "logical_observations_fact"
    assert table_insert[1][0][4] == "station_id,date_id"
    assert "determinant_columns" in table_insert[2]
    assert "is_determinant" in column_insert[2]
    assert len(column_insert[1]) == 3
