from __future__ import annotations

from dataclasses import dataclass

from core.clickhouse_manager import CH_DB, META_DB, ClickHouseManager
from core.logger import get_logger
from core.meta import clear_metadata_table, load_confirmed_adjacency_edges
from core.naming import is_key_like_column
from core.schema import normalize_clickhouse_type, q_ident

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

    def __init__(self, db: ClickHouseManager):
        self.db = db

    def infer_roles(self) -> list[TableRoleCandidate]:
        table_rows = self.load_table_row_counts()
        primary_key_tables = self.load_primary_key_tables()
        outgoing_edges = self.load_outgoing_edges()
        incoming_edges = self.load_incoming_edges()
        column_type_counts = self.load_column_type_counts()
        additive_measure_counts = self.load_additive_measure_counts()
        transactional_grain_tables = self.load_transactional_grain_tables()

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
            additive_measure_columns = additive_measure_counts.get(table_name, 0)
            has_transactional_grain = table_name in transactional_grain_tables
            is_lookup_table = self.is_lookup_table(
                row_count=row_count,
                outgoing_edges=outgoing_count,
                incoming_edges=incoming_count,
                has_primary_key=has_primary_key,
                numeric_columns=numeric_columns,
                text_columns=text_columns,
                additive_measure_columns=additive_measure_columns,
            )

            role, confidence, reason = self.classify_table(
                row_count=row_count,
                outgoing_edges=outgoing_count,
                incoming_edges=incoming_count,
                has_primary_key=has_primary_key,
                numeric_columns=numeric_columns,
                text_columns=text_columns,
                date_columns=date_columns,
                additive_measure_columns=additive_measure_columns,
                has_transactional_grain=has_transactional_grain,
                is_lookup_table=is_lookup_table,
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

    def store_roles(self, roles: list[TableRoleCandidate]) -> None:
        """
        Store inferred table roles so downstream steps can consume stable metadata.
        """

        clear_metadata_table(self.db, "table_roles")

        if not roles:
            return

        rows = [
            [
                CH_DB,
                role.table_name,
                role.row_count,
                role.outgoing_edges,
                role.incoming_edges,
                role.numeric_columns,
                role.text_columns,
                role.date_columns,
                role.has_primary_key,
                role.role,
                role.confidence,
                role.reason,
            ]
            for role in roles
        ]

        self.db.insert(
            f"{META_DB}.table_roles",
            rows,
            column_names=[
                "database_name",
                "table_name",
                "row_count",
                "outgoing_edges",
                "incoming_edges",
                "numeric_columns",
                "text_columns",
                "date_columns",
                "has_primary_key",
                "role",
                "confidence",
                "reason",
            ],
        )

    def load_roles(self) -> list[TableRoleCandidate]:
        """
        Load stored table roles from metadata.
        """

        sql = f"""
        SELECT
            table_name,
            row_count,
            outgoing_edges,
            incoming_edges,
            numeric_columns,
            text_columns,
            date_columns,
            has_primary_key,
            role,
            confidence,
            reason
        FROM {q_ident(META_DB)}.table_roles
        WHERE database_name = %(database)s
        ORDER BY table_name
        """

        rows = self.db.query(sql, parameters={"database": CH_DB}).result_rows

        return [
            TableRoleCandidate(
                table_name=row[0],
                row_count=row[1],
                outgoing_edges=row[2],
                incoming_edges=row[3],
                numeric_columns=row[4],
                text_columns=row[5],
                date_columns=row[6],
                has_primary_key=row[7],
                role=row[8],
                confidence=row[9],
                reason=row[10],
            )
            for row in rows
        ]

    def load_table_row_counts(self) -> dict[str, int]:
        sql = f"""
        SELECT
            table_name,
            max(rows) AS row_count
        FROM {q_ident(META_DB)}.column_profiles
        WHERE database_name = %(database)s
        GROUP BY table_name
        """

        rows = self.db.query(sql, parameters={"database": CH_DB}).result_rows
        return {row[0]: row[1] for row in rows}

    def load_primary_key_tables(self) -> set[str]:
        sql = f"""
        SELECT DISTINCT table_name
        FROM {q_ident(META_DB)}.primary_key_candidates
        WHERE database_name = %(database)s
        """

        rows = self.db.query(sql, parameters={"database": CH_DB}).result_rows
        return {row[0] for row in rows}

    def load_transactional_grain_tables(self) -> set[str]:
        """
        Return tables for which a simple or composite key candidate exists.
        """
        return self.load_primary_key_tables()

    def load_outgoing_edges(self) -> dict[str, int]:
        targets_by_source: dict[str, set[str]] = {}

        for edge in load_confirmed_adjacency_edges(self.db):
            targets_by_source.setdefault(edge.source_table, set()).add(edge.target_table)

        return {
            source_table: len(target_tables)
            for source_table, target_tables in targets_by_source.items()
        }

    def load_incoming_edges(self) -> dict[str, int]:
        sources_by_target: dict[str, set[str]] = {}

        for edge in load_confirmed_adjacency_edges(self.db):
            sources_by_target.setdefault(edge.target_table, set()).add(edge.source_table)

        return {
            target_table: len(source_tables)
            for target_table, source_tables in sources_by_target.items()
        }

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
        WHERE database_name = %(database)s
          AND NOT startsWith(column_name, '__')
        GROUP BY table_name
        """

        rows = self.db.query(sql, parameters={"database": CH_DB}).result_rows

        return {
            row[0]: {
                "numeric": row[1],
                "text": row[2],
                "date": row[3],
            }
            for row in rows
        }

    def load_additive_measure_counts(self) -> dict[str, int]:
        """
        Count numeric columns that look usable as measures rather than identifiers.
        """
        sql = f"""
        SELECT
            s.table_name,
            s.column_name,
            s.column_type,
            s.distinct_count,
            s.entropy_ratio,
            s.variation_coefficient,
            p.uniqueness_ratio
        FROM {q_ident(META_DB)}.column_stats AS s
        INNER JOIN (
            SELECT
                table_name,
                max(run_ts) AS max_run_ts
            FROM {q_ident(META_DB)}.column_stats
            WHERE database_name = %(database)s
            GROUP BY table_name
        ) AS latest
            ON s.table_name = latest.table_name
           AND s.run_ts = latest.max_run_ts
        INNER JOIN {q_ident(META_DB)}.column_profiles AS p
            ON s.database_name = p.database_name
           AND s.table_name = p.table_name
           AND s.column_name = p.column_name
        WHERE s.database_name = %(database)s
        """

        rows = self.db.query(sql, parameters={"database": CH_DB}).result_rows
        counts: dict[str, int] = {}

        for row in rows:
            table_name = row[0]
            if self.is_additive_measure_column(
                column_name=row[1],
                column_type=row[2],
                distinct_count=row[3],
                entropy_ratio=row[4],
                variation_coefficient=row[5],
                uniqueness_ratio=row[6],
            ):
                counts[table_name] = counts.get(table_name, 0) + 1

        return counts

    @staticmethod
    def classify_table(
        row_count: int,
        outgoing_edges: int,
        incoming_edges: int,
        has_primary_key: bool,
        numeric_columns: int,
        text_columns: int,
        date_columns: int,
        additive_measure_columns: int | None = None,
        has_transactional_grain: bool = False,
        is_lookup_table: bool = False,
    ) -> tuple[str, float, str]:
        has_additive_signal = additive_measure_columns is None or additive_measure_columns > 0

        if (
            outgoing_edges >= 2
            and row_count >= 5
            and numeric_columns > text_columns
            and has_additive_signal
            and not is_lookup_table
        ):
            return (
                "FACT",
                0.85,
                "table_has_many_links_and_mostly_numeric_columns",
            )

        if (
            outgoing_edges >= 2
            and row_count >= 5
            and has_transactional_grain
            and additive_measure_columns is not None
            and additive_measure_columns > 0
            and not is_lookup_table
        ):
            return (
                "FACT",
                0.8,
                "table_has_transactional_grain_and_additive_measure",
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
    def is_lookup_table(
        row_count: int,
        outgoing_edges: int,
        incoming_edges: int,
        has_primary_key: bool,
        numeric_columns: int,
        text_columns: int,
        additive_measure_columns: int,
    ) -> bool:
        """
        Detect small/descriptive reference tables that should not become facts.
        """
        if not has_primary_key:
            return False

        if additive_measure_columns > 0:
            return False

        return (
            row_count < 100
            and incoming_edges >= 1
            and numeric_columns <= text_columns + outgoing_edges
        )

    @staticmethod
    def is_additive_measure_column(
        column_name: str,
        column_type: str,
        distinct_count: int,
        entropy_ratio: float | None,
        variation_coefficient: float | None,
        uniqueness_ratio: float | None,
    ) -> bool:
        """
        Detect numeric non-key columns with enough distribution to behave as measures.
        """
        if is_key_like_column(column_name):
            return False

        normalized_type = normalize_clickhouse_type(column_type).lower()
        if not (
            normalized_type.startswith("int")
            or normalized_type.startswith("uint")
            or normalized_type.startswith("float")
            or normalized_type.startswith("decimal")
        ):
            return False

        if distinct_count <= 1:
            return False

        if uniqueness_ratio is not None and uniqueness_ratio >= 0.95:
            return False

        entropy = entropy_ratio or 0.0
        variation = abs(variation_coefficient or 0.0)
        return entropy >= 0.05 or variation >= 0.05

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
