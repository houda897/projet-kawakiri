from __future__ import annotations

from dataclasses import dataclass

from core.clickhouse_manager import CH_DB, META_DB, ClickHouseManager
from core.logger import get_logger
from core.meta import clear_metadata_table
from core.schema import q_ident
from inference.functional_group_builder import FunctionalColumnGroup
from modeling.fact_dimension_builder import (
    DIMENSION_CANDIDATE,
    FactDimensionBuilder,
    LogicalTablePlan,
)

logger = get_logger(__name__)


@dataclass(frozen=True)
class LogicalTable:
    database_name: str
    logical_table_name: str
    source_table: str
    group_name: str
    determinant_columns: tuple[str, ...]
    columns: tuple[str, ...]
    logical_table_role: str = DIMENSION_CANDIDATE
    distinct_rows: bool = True


class LogicalTableBuilder:
    """
    Materialize functional column groups as ClickHouse logical tables.
    """

    def __init__(self, db: ClickHouseManager):
        self.db = db

    def build_logical_tables(self) -> list[LogicalTable]:
        plans = FactDimensionBuilder(self.db).build_plans()
        logical_tables = []

        for plan in plans:
            logical_table = self.plan_to_logical_table(plan)
            self.materialize(logical_table)
            logical_tables.append(logical_table)

        self.store_logical_tables(logical_tables)
        return logical_tables

    def to_logical_table(self, group: FunctionalColumnGroup) -> LogicalTable:
        return LogicalTable(
            database_name=group.database_name,
            logical_table_name=group.group_name,
            source_table=group.source_table,
            group_name=group.group_name,
            determinant_columns=group.determinant_columns,
            columns=group.all_columns,
            logical_table_role=DIMENSION_CANDIDATE,
            distinct_rows=True,
        )

    def plan_to_logical_table(self, plan: LogicalTablePlan) -> LogicalTable:
        return LogicalTable(
            database_name=plan.database_name,
            logical_table_name=plan.logical_table_name,
            source_table=plan.source_table,
            group_name=plan.group_name,
            determinant_columns=plan.determinant_columns,
            columns=plan.columns,
            logical_table_role=plan.logical_table_role,
            distinct_rows=plan.distinct_rows,
        )

    def materialize(
        self,
        logical_table: LogicalTable,
        group: FunctionalColumnGroup | None = None,
    ) -> None:
        source_table = group.source_table if group is not None else logical_table.source_table
        source_ref = f"{q_ident(CH_DB)}.{q_ident(source_table)}"
        target_ref = f"{q_ident(CH_DB)}.{q_ident(logical_table.logical_table_name)}"
        columns_sql = ", ".join(q_ident(column) for column in logical_table.columns)
        distinct_sql = "DISTINCT " if logical_table.distinct_rows else ""

        self.db.command(f"DROP TABLE IF EXISTS {target_ref}")
        self.db.command(
            f"""
            CREATE TABLE {target_ref}
            ENGINE = MergeTree
            ORDER BY tuple()
            AS
            SELECT {distinct_sql}{columns_sql}
            FROM {source_ref}
            """
        )

    def store_logical_tables(self, logical_tables: list[LogicalTable]) -> None:
        clear_metadata_table(self.db, "logical_tables")
        clear_metadata_table(self.db, "logical_table_columns")

        if not logical_tables:
            return

        table_rows = [
            [
                logical_table.database_name,
                logical_table.logical_table_name,
                logical_table.source_table,
                logical_table.group_name,
                ",".join(logical_table.determinant_columns),
                logical_table.logical_table_role,
            ]
            for logical_table in logical_tables
        ]
        column_rows = [
            [
                logical_table.database_name,
                logical_table.logical_table_name,
                logical_table.source_table,
                logical_table.group_name,
                column,
                column in logical_table.determinant_columns,
            ]
            for logical_table in logical_tables
            for column in logical_table.columns
        ]

        self.db.insert(
            f"{META_DB}.logical_tables",
            table_rows,
            column_names=[
                "database_name",
                "logical_table_name",
                "source_table",
                "group_name",
                "determinant_columns",
                "logical_table_role",
            ],
        )
        self.db.insert(
            f"{META_DB}.logical_table_columns",
            column_rows,
            column_names=[
                "database_name",
                "logical_table_name",
                "source_table",
                "group_name",
                "column_name",
                "is_determinant",
            ],
        )

    def load_logical_tables(self) -> list[LogicalTable]:
        sql = f"""
        SELECT
            t.database_name,
            t.logical_table_name,
            t.source_table,
            t.group_name,
            t.determinant_columns,
            t.logical_table_role,
            groupArray(c.column_name) AS columns
        FROM {q_ident(META_DB)}.logical_tables AS t
        INNER JOIN {q_ident(META_DB)}.logical_table_columns AS c
            ON t.database_name = c.database_name
           AND t.logical_table_name = c.logical_table_name
        WHERE t.database_name = %(database)s
        GROUP BY
            t.database_name,
            t.logical_table_name,
            t.source_table,
            t.group_name,
            t.determinant_columns,
            t.logical_table_role
        ORDER BY t.logical_table_name
        """

        rows = self.db.query(sql, parameters={"database": CH_DB}).result_rows
        return [
            LogicalTable(
                database_name=row[0],
                logical_table_name=row[1],
                source_table=row[2],
                group_name=row[3],
                determinant_columns=self.split_columns(row[4]),
                logical_table_role=row[5],
                columns=tuple(row[6]),
            )
            for row in rows
        ]

    @staticmethod
    def split_columns(columns: str) -> tuple[str, ...]:
        return tuple(column.strip() for column in columns.split(",") if column.strip())

    @staticmethod
    def print_logical_tables(logical_tables: list[LogicalTable]) -> None:
        if not logical_tables:
            logger.info("No logical tables materialized.")
            return

        for logical_table in logical_tables:
            logger.info(
                "%s | role=%s | source=%s | determinants=%s | columns=%s",
                logical_table.logical_table_name,
                logical_table.logical_table_role,
                logical_table.source_table,
                ", ".join(logical_table.determinant_columns),
                ", ".join(logical_table.columns),
            )
