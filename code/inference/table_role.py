from __future__ import annotations

from dataclasses import dataclass

from core.clickhouse_manager import META_DB, clickhouse_manager
from core.logger import get_logger
from core.schema import q_ident

logger = get_logger(__name__)


@dataclass
class TableRoleCandidate:
    """
    Inferred role of a table in a decision model.
    """

    table_name: str
    row_count: int
    outgoing_edges: int
    incoming_edges: int
    numeric_columns: int
    text_columns: int
    date_columns: int
    has_primary_key: bool
    role: str
    confidence: float
    reason: str


class TableRoleEngine:
    """
    Infer table roles from the adjacency graph.

    A fact table usually points to several dimensions and carries mostly
    numeric measures. A dimension table usually has a primary key and descriptive
    columns, and can also point to other dimensions in a snowflake schema.
    """

    def __init__(self, db: clickhouse_manager):
        self.db = db

    def infer_roles(self) -> list[TableRoleCandidate]:
        table_rows = self.load_table_row_counts()
        primary_key_tables = self.load_primary_key_tables()
        outgoing_edges = self.load_outgoing_edges()
        incoming_edges = self.load_incoming_edges()
        column_type_counts = self.load_column_type_counts()

        results = []

        for table_name, row_count in table_rows.items():
            outgoing_count = outgoing_edges.get(table_name, 0)
            incoming_count = incoming_edges.get(table_name, 0)
            has_primary_key = table_name in primary_key_tables

            type_counts = column_type_counts.get(
                table_name,
                {"numeric": 0, "text": 0, "date": 0},
            )
            numeric_columns = type_counts["numeric"]
            text_columns = type_counts["text"]
            date_columns = type_counts["date"]

            role, confidence, reason = self.classify_table(
                row_count=row_count,
                outgoing_edges=outgoing_count,
                incoming_edges=incoming_count,
                has_primary_key=has_primary_key,
                numeric_columns=numeric_columns,
                text_columns=text_columns,
                date_columns=date_columns,
            )

            results.append(
                TableRoleCandidate(
                    table_name=table_name,
                    row_count=row_count,
                    outgoing_edges=outgoing_count,
                    incoming_edges=incoming_count,
                    numeric_columns=numeric_columns,
                    text_columns=text_columns,
                    date_columns=date_columns,
                    has_primary_key=has_primary_key,
                    role=role,
                    confidence=confidence,
                    reason=reason,
                )
            )

        return sorted(results, key=lambda result: result.table_name)

    def load_table_row_counts(self) -> dict[str, int]:
        sql = f"""
        SELECT
            table_name,
            max(rows) AS row_count
        FROM {q_ident(META_DB)}.column_profiles
        GROUP BY table_name
        """

        rows = self.db.query(sql).result_rows
        return {row[0]: row[1] for row in rows}

    def load_primary_key_tables(self) -> set[str]:
        sql = f"""
        SELECT DISTINCT table_name
        FROM {q_ident(META_DB)}.primary_key_candidates
        """

        rows = self.db.query(sql).result_rows
        return {row[0] for row in rows}

    def load_outgoing_edges(self) -> dict[str, int]:
        sql = f"""
        SELECT
            source_table,
            countDistinct(target_table) AS outgoing_edges
        FROM {q_ident(META_DB)}.adjacency_edges
        WHERE evidence IN ('CONFIRMED', 'SEMANTIC_CONFIRMED')
        GROUP BY source_table
        """

        rows = self.db.query(sql).result_rows
        return {row[0]: row[1] for row in rows}

    def load_incoming_edges(self) -> dict[str, int]:
        sql = f"""
        SELECT
            target_table,
            countDistinct(source_table) AS incoming_edges
        FROM {q_ident(META_DB)}.adjacency_edges
        WHERE evidence IN ('CONFIRMED', 'SEMANTIC_CONFIRMED')
        GROUP BY target_table
        """

        rows = self.db.query(sql).result_rows
        return {row[0]: row[1] for row in rows}

    def load_column_type_counts(self) -> dict[str, dict[str, int]]:
        sql = f"""
        SELECT
            table_name,
            countIf(
                position(column_type, 'Int') > 0
                OR position(column_type, 'UInt') > 0
                OR position(column_type, 'Float') > 0
                OR position(column_type, 'Decimal') > 0
            ) AS numeric_columns,
            countIf(position(column_type, 'String') > 0) AS text_columns,
            countIf(position(column_type, 'Date') > 0) AS date_columns
        FROM {q_ident(META_DB)}.column_profiles
        WHERE NOT startsWith(column_name, '__')
        GROUP BY table_name
        """

        rows = self.db.query(sql).result_rows

        return {
            row[0]: {
                "numeric": row[1],
                "text": row[2],
                "date": row[3],
            }
            for row in rows
        }

    @staticmethod
    def classify_table(
        row_count: int,
        outgoing_edges: int,
        incoming_edges: int,
        has_primary_key: bool,
        numeric_columns: int,
        text_columns: int,
        date_columns: int,
    ) -> tuple[str, float, str]:
        if outgoing_edges >= 2 and row_count >= 5 and numeric_columns > text_columns:
            return (
                "FACT",
                0.85,
                "table_has_many_links_and_mostly_numeric_columns",
            )

        if outgoing_edges >= 1 and has_primary_key and text_columns >= numeric_columns:
            return (
                "DIMENSION",
                0.75,
                "table_has_links_but_mostly_descriptive_columns",
            )

        if has_primary_key and incoming_edges >= 1:
            return (
                "DIMENSION",
                0.85,
                "table_has_primary_key_and_is_referenced_by_other_tables",
            )

        if has_primary_key:
            return (
                "DIMENSION",
                0.65,
                "table_has_primary_key_but_few_confirmed_links",
            )

        return (
            "UNKNOWN",
            0.4,
            "not_enough_evidence_to_choose_fact_or_dimension",
        )

    @staticmethod
    def print_roles(results: list[TableRoleCandidate]) -> None:
        if not results:
            logger.info("No table roles inferred.")
            return

        for result in results:
            logger.info(
                "%s | role=%s | rows=%s | outgoing=%s | incoming=%s | "
                "numeric=%s | text=%s | date=%s | confidence=%s | reason=%s",
                result.table_name,
                result.role,
                result.row_count,
                result.outgoing_edges,
                result.incoming_edges,
                result.numeric_columns,
                result.text_columns,
                result.date_columns,
                result.confidence,
                result.reason,
            )