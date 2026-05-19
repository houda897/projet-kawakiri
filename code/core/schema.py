from __future__ import annotations

from dataclasses import dataclass

from core.manager import CH_DB

EXCLUDE_COL_TYPES_PREFIXES = ("Array", "Map", "Nested", "Tuple", "JSON", "Object")


@dataclass(frozen=True)
class Col:
    name: str
    ch_type: str


def q_ident(x: str) -> str:
    return "`" + x.replace("`", "``") + "`"


def list_tables(client) -> list[str]:
    rows = client.query(
        """
        SELECT name
        FROM system.tables
        WHERE database = %(db)s
          AND engine NOT IN ('View', 'MaterializedView')
        ORDER BY name
        """,
        parameters={"db": CH_DB},
    ).result_rows
    return [r[0] for r in rows]


def list_columns(client, table: str) -> list[Col]:
    rows = client.query(
        """
        SELECT name, type
        FROM system.columns
        WHERE database = %(db)s AND table = %(t)s
        ORDER BY position
        """,
        parameters={"db": CH_DB, "t": table},
    ).result_rows

    cols = []
    for name, typ in rows:
        if typ.startswith(EXCLUDE_COL_TYPES_PREFIXES):
            continue
        cols.append(Col(name=name, ch_type=typ))
    return cols

