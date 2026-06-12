from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from core.clickhouse_manager import CH_DB, META_DB, ClickHouseManager
from core.schema import q_ident


@dataclass
class LowCardinalityColumn:
    """
    Column with few distinct values compared with the number of rows.

    Low-cardinality columns often represent categories, statuses, countries, or
    hierarchy levels. They help describe tables, but are usually weak primary-key
    candidates by themselves.
    """

    database_name: str
    table_name: str
    column_name: str
    column_type: str
    rows: int
    distinct_count: int
    uniqueness_ratio: float
    null_ratio: float


class LowCardinalityAnalyzer:
    """
    Detect columns that behave like categorical attributes.
    """

    def __init__(self, db: ClickHouseManager):
        self.db = db

    def find_columns(
        self,
        table_name: str | None = None,
        max_uniqueness_ratio: float = 0.2,
        min_rows: int = 10,
    ) -> list[LowCardinalityColumn]:
        """
        Find columns whose distinct values are small relative to table size.
        """

        parameters: dict[str, Any] = {
            "database": CH_DB,
            "max_uniqueness_ratio": max_uniqueness_ratio,
            "min_rows": min_rows,
        }

        table_filter = ""
        if table_name is not None:
            table_filter = "AND table_name = %(table_name)s"
            parameters["table_name"] = table_name

        sql = f"""
        SELECT
            database_name,
            table_name,
            column_name,
            column_type,
            rows,
            distinct_count,
            uniqueness_ratio,
            null_ratio
        FROM {q_ident(META_DB)}.column_profiles
        WHERE database_name = %(database)s
          AND rows >= %(min_rows)s
          AND uniqueness_ratio <= %(max_uniqueness_ratio)s
          AND null_ratio < 1
          AND NOT startsWith(column_name, '__')
          {table_filter}
        ORDER BY table_name, uniqueness_ratio ASC, column_name
        """

        rows = self.db.query(sql, parameters=parameters).result_rows

        return [
            LowCardinalityColumn(
                database_name=row[0],
                table_name=row[1],
                column_name=row[2],
                column_type=row[3],
                rows=row[4],
                distinct_count=row[5],
                uniqueness_ratio=row[6],
                null_ratio=row[7],
            )
            for row in rows
        ]

    @staticmethod
    def to_column_name_set(columns: list[LowCardinalityColumn]) -> set[tuple[str, str]]:
        """
        Convert low-cardinality columns to a set keyed by table and column name.
        """

        return {(column.table_name, column.column_name) for column in columns}
