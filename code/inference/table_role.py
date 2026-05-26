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
    has_primary_key: bool
    role: str
    confidence: float
    reason: str


class TableRoleEngine:
    """
    Infer table roles from the adjacency graph.

    A fact table usually points to several dimensions.
    A dimension table usually has a primary key and receives links.
    """

    def __init__(self, db: clickhouse_manager):
        self.db = db

    def infer_roles(self) -> list[TableRoleCandidate]:
        table_rows = self.load_table_row_counts()
        primary_key_tables = self.load_primary_key_tables()
        outgoing_edges = self.load_outgoing_edges()
        incoming_edges = self.load_incoming_edges()

        results = []

        for table_name, row_count in table_rows.items():
            outgoing_count = outgoing_edges.get(table_name, 0)
            incoming_count = incoming_edges.get(table_name, 0)
            has_primary_key = table_name in primary_key_tables

            role, confidence, reason = self.classify_table(
                row_count=row_count,
                outgoing_edges=outgoing_count,
                incoming_edges=incoming_count,
                has_primary_key=has_primary_key,
            )

            results.append(
                TableRoleCandidate(
                    table_name=table_name,
                    row_count=row_count,
                    outgoing_edges=outgoing_count,
                    incoming_edges=incoming_count,
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
        GROUP BY source_table
        """
        #WHERE evidence IN ('CONFIRMED', 'SEMANTIC_CONFIRMED')
        rows = self.db.query(sql).result_rows
        return {row[0]: row[1] for row in rows}

    def load_incoming_edges(self) -> dict[str, int]:
        sql = f"""
        SELECT
            target_table,
            countDistinct(source_table) AS incoming_edges
        FROM {q_ident(META_DB)}.adjacency_edges
        GROUP BY target_table
        """
        # WHERE evidence IN ('CONFIRMED', 'SEMANTIC_CONFIRMED')

        rows = self.db.query(sql).result_rows
        return {row[0]: row[1] for row in rows}

    '''@staticmethod
    def classify_table(
        row_count: int,
        outgoing_edges: int,
        incoming_edges: int,
        has_primary_key: bool,
    ) -> tuple[str, float, str]:
        if outgoing_edges >= 2:
            return (
                "FACT",
                0.85,
                "table_has_multiple_confirmed_links_to_other_tables",
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
    '''
    @staticmethod
    def classify_table(
        row_count: int,
        outgoing_edges: int,
        incoming_edges: int,
        has_primary_key: bool,
    ) -> tuple[str, float, str]:
        if outgoing_edges >= 2 and row_count >= 5:
            return (
                "FACT",
                0.85,
                "table_has_many_rows_and_multiple_links_to_other_tables",
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
                "%s | role=%s | rows=%s | outgoing=%s | incoming=%s | confidence=%s | reason=%s",
                result.table_name,
                result.role,
                result.row_count,
                result.outgoing_edges,
                result.incoming_edges,
                result.confidence,
                result.reason,
            )
