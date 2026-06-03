from types import SimpleNamespace
from unittest.mock import MagicMock

from generation.sql_view_generator import SQLViewGenerator


def test_load_table_roles_reads_stored_metadata() -> None:
    db = MagicMock()
    db.query.return_value = SimpleNamespace(
        result_rows=[
            ("sales", "FACT"),
            ("customers", "DIMENSION"),
        ]
    )
    generator = SQLViewGenerator(db)

    roles = generator.load_table_roles()

    assert roles == {
        "sales": "FACT",
        "customers": "DIMENSION",
    }
    sql = db.query.call_args[0][0]
    assert "table_roles" in sql


def test_load_table_roles_requires_stored_roles() -> None:
    db = MagicMock()
    db.query.return_value = SimpleNamespace(result_rows=[])
    generator = SQLViewGenerator(db)

    try:
        generator.load_table_roles()
    except ValueError as exc:
        assert "Run infer-table-roles" in str(exc)
    else:
        raise AssertionError("Expected ValueError when stored table roles are missing")
