from __future__ import annotations

from dataclasses import dataclass

from core.clickhouse_manager import CH_DB, META_DB, clickhouse_manager
from core.logger import get_logger
from core.schema import q_ident

from inference.primary_key import PrimaryKeyCandidate

logger = get_logger(__name__)


@dataclass
class JoinPrimaryKeyCandidate:
    """
    Empirical relationship between a source column and a primary-key candidate.

    The success ratio measures the fraction of non-null source rows whose value
    is present in the target key domain.
    """

    source_table: str
    source_column: str
    target_table: str
    target_column: str
    source_non_null_rows: int
    matched_rows: int
    join_success_ratio: float


@dataclass
class SourceColumn:
    """Profiled column that can be evaluated as a possible foreign key."""

    table_name: str
    column_name: str
    column_type: str


class JoinEngine:
    """
    Evaluate physical joins between profiled columns and primary-key candidates.
    """

    def __init__(self, db: clickhouse_manager):
        self.db = db

    def evaluate_join_to_primary_key(
        self,
        source_table: str,
        source_column: str,
        primary_key: PrimaryKeyCandidate,
        limit_rows: int | None = None,
    ) -> JoinPrimaryKeyCandidate:
        """
        Measure whether a source column is covered by a primary-key candidate.
        """

        source_ref = f"{q_ident(CH_DB)}.{q_ident(source_table)}"
        target_ref = f"{q_ident(CH_DB)}.{q_ident(primary_key.table_name)}"
        source_col = q_ident(source_column)
        target_col = q_ident(primary_key.column_name)

        limit_clause = f"LIMIT {limit_rows}" if limit_rows is not None else ""

        sql = f"""
        WITH
            source_values AS (
                SELECT {source_col} AS value
                FROM {source_ref}
                WHERE {source_col} IS NOT NULL
                {limit_clause}
            ),
            target_values AS (
                SELECT DISTINCT {target_col} AS value
                FROM {target_ref}
                WHERE {target_col} IS NOT NULL
            )
        SELECT
            count() AS source_non_null_rows,
            countIf(t.value IS NOT NULL) AS matched_rows,
            if(
                source_non_null_rows = 0,
                0.0,
                matched_rows / toFloat64(source_non_null_rows)
            ) AS join_success_ratio
        FROM source_values AS s
        LEFT JOIN target_values AS t
            ON s.value = t.value
        """

        row = self.db.query(sql).result_rows[0]

        return JoinPrimaryKeyCandidate(
            source_table=source_table,
            source_column=source_column,
            target_table=primary_key.table_name,
            target_column=primary_key.column_name,
            source_non_null_rows=row[0],
            matched_rows=row[1],
            join_success_ratio=round(row[2], 6),
        )

    def evaluate_join_by_target(
        self,
        source_table: str,
        source_column: str,
        target_table: str,
        target_column: str,
        primary_keys: list[PrimaryKeyCandidate],
    ) -> JoinPrimaryKeyCandidate:
        """
        Evaluate a join between a source column and a named target key.

        Looks up the PrimaryKeyCandidate from the provided list, then delegates
        to evaluate_join_to_primary_key.
        """
        primary_key = self.find_primary_key(
            primary_keys=primary_keys,
            target_table=target_table,
            target_column=target_column,
        )

        return self.evaluate_join_to_primary_key(
            source_table=source_table,
            source_column=source_column,
            primary_key=primary_key,
        )

    def find_primary_key(
        self,
        primary_keys: list[PrimaryKeyCandidate],
        target_table: str,
        target_column: str,
    ) -> PrimaryKeyCandidate:
        """
        Return the PrimaryKeyCandidate that matches table and column names.

        Raises ValueError if no match is found, which means profiling and
        primary-key inference must be run before calling this method.
        """
        for primary_key in primary_keys:
            if primary_key.table_name == target_table and primary_key.column_name == target_column:
                return primary_key

        raise ValueError(
            f"No primary-key candidate found for {target_table}.{target_column}. "
            "Run profiling and primary-key inference first."
        )

    def load_source_columns(self) -> list[SourceColumn]:
        """
        Load all profiled columns that are eligible foreign-key candidates.

        Excludes columns with 100% nulls and internal columns prefixed with '__'.
        """
        sql = f"""
        SELECT
            table_name,
            column_name,
            column_type
        FROM {q_ident(META_DB)}.column_profiles
        WHERE null_ratio < 1
          AND NOT startsWith(column_name, '__')
        ORDER BY table_name, column_name
        """

        rows = self.db.query(sql).result_rows

        return [
            SourceColumn(
                table_name=row[0],
                column_name=row[1],
                column_type=row[2],
            )
            for row in rows
        ]

    def evaluate_candidates(
        self,
        primary_keys: list[PrimaryKeyCandidate],
        min_success_ratio: float = 0.95,
    ) -> list[JoinPrimaryKeyCandidate]:
        """
        Discover all foreign-key relationships in the database.

        For each profiled column, tests whether it is covered by any known
        primary key using a LEFT JOIN. Only pairs with a join success ratio
        above min_success_ratio are kept.

        This is the main entry point for building the adjacency matrix used
        to infer the star-schema topology.
        """
        source_columns = self.load_source_columns()
        candidates = []

        for source in source_columns:
            for primary_key in primary_keys:
                if self.should_skip_pair(source, primary_key):
                    continue

                result = self.evaluate_join_to_primary_key(
                    source_table=source.table_name,
                    source_column=source.column_name,
                    primary_key=primary_key,
                )

                if result.join_success_ratio >= min_success_ratio:
                    candidates.append(result)

        return candidates

    def store_candidates(
        self,
        candidates: list[JoinPrimaryKeyCandidate],
    ) -> None:
        """
        Store inferred join candidates in metadata.
        """

        if not candidates:
            return

        rows = [
            [
                candidate.source_table,
                candidate.source_column,
                candidate.target_table,
                candidate.target_column,
                candidate.source_non_null_rows,
                candidate.matched_rows,
                candidate.join_success_ratio,
            ]
            for candidate in candidates
        ]

        self.db.insert(
            f"{META_DB}.join_candidates",
            rows,
            column_names=[
                "source_table",
                "source_column",
                "target_table",
                "target_column",
                "source_non_null_rows",
                "matched_rows",
                "join_success_ratio",
            ],
        )


    def load_candidates(self) -> list[JoinPrimaryKeyCandidate]:
        """
        Load stored join candidates from metadata.
        """

        sql = f"""
        SELECT
            source_table,
            source_column,
            target_table,
            target_column,
            source_non_null_rows,
            matched_rows,
            join_success_ratio
        FROM {q_ident(META_DB)}.join_candidates
        ORDER BY source_table, target_table, source_column, target_column
        """

        rows = self.db.query(sql).result_rows

        return [
            JoinPrimaryKeyCandidate(
                source_table=row[0],
                source_column=row[1],
                target_table=row[2],
                target_column=row[3],
                source_non_null_rows=row[4],
                matched_rows=row[5],
                join_success_ratio=row[6],
            )
            for row in rows
        ]

    @staticmethod
    def _clean_type(ch_type: str) -> str:
        """Strip Nullable() wrapper to compare base physical types."""
        return ch_type.removeprefix("Nullable(").removesuffix(")")

    @classmethod
    def should_skip_pair(
        cls,
        source: SourceColumn,
        primary_key: PrimaryKeyCandidate,
    ) -> bool:
        """
        Return True if this source / primary-key pair cannot be a valid FK relationship.

        A pair is skipped when the source and target belong to the same table,
        or when their base ClickHouse types are incompatible (e.g. String vs Int64).
        Nullable wrappers are stripped before comparing types.
        """
        same_table = source.table_name == primary_key.table_name

        source_base = cls._clean_type(source.column_type)
        target_base = cls._clean_type(primary_key.column_type)
        incompatible_type = source_base != target_base

        return same_table or incompatible_type

    @staticmethod
    def print_result(result: JoinPrimaryKeyCandidate) -> None:
        log_join_result(result)

    @staticmethod
    def print_candidates(candidates: list[JoinPrimaryKeyCandidate]) -> None:
        log_join_candidates(candidates)


def log_join_result(result: JoinPrimaryKeyCandidate) -> None:
    """Log the result of a single join evaluation."""
    logger.info(
        "%s.%s -> %s.%s",
        result.source_table,
        result.source_column,
        result.target_table,
        result.target_column,
    )
    logger.info("Source non-null rows : %s", result.source_non_null_rows)
    logger.info("Matched rows         : %s", result.matched_rows)
    logger.info("Join success ratio   : %s", result.join_success_ratio)


def log_join_candidates(candidates: list[JoinPrimaryKeyCandidate]) -> None:
    """Log all join candidates found during inference."""
    if not candidates:
        logger.info("No join candidates found.")
        return

    for candidate in candidates:
        logger.info(
            "%s.%s -> %s.%s | ratio=%s",
            candidate.source_table,
            candidate.source_column,
            candidate.target_table,
            candidate.target_column,
            candidate.join_success_ratio,
        )
