from __future__ import annotations

from dataclasses import dataclass

from core.clickhouse_manager import CH_DB

EXCLUDE_COL_TYPES_PREFIXES = ("Array", "Map", "Nested", "Tuple", "JSON", "Object")


@dataclass(frozen=True)
class Col:
    name: str
    ch_type: str


def q_ident(x: str) -> str:
    """Wrap a ClickHouse identifier in backticks and escape any existing backticks."""
    return "`" + x.replace("`", "``") + "`"


def list_tables(client, database: str = CH_DB) -> list[str]:
    """Return the names of all regular (non-view) tables in the given database."""
    rows = client.query(
        """
        SELECT name
        FROM system.tables
        WHERE database = %(db)s
          AND engine NOT IN ('View', 'MaterializedView')
        ORDER BY name
        """,
        parameters={"db": database},
    ).result_rows
    return [r[0] for r in rows]


def list_columns(client, table: str, database: str = CH_DB) -> list[Col]:
    """Return the columns of a table, excluding complex types (Array, Map, Tuple, …)."""
    rows = client.query(
        """
        SELECT name, type
        FROM system.columns
        WHERE database = %(db)s AND table = %(t)s
        ORDER BY position
        """,
        parameters={"db": database, "t": table},
    ).result_rows

    cols = []
    for name, typ in rows:
        if typ.startswith(EXCLUDE_COL_TYPES_PREFIXES):
            continue
        cols.append(Col(name=name, ch_type=typ))
    return cols


def get_columns_name(client, database: str, table: str) -> list[str]:
    """Return the list of column names for a given table."""
    rows = client.query(
        """
        SELECT name
        FROM system.columns
        WHERE database = %(db)s AND table = %(t)s
        ORDER BY position
        """,
        parameters={"db": database, "t": table},
    ).result_rows
    return [r[0] for r in rows]
