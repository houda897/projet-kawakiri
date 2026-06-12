from __future__ import annotations

import itertools
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

from config.scoring import EVALUATE_CANDIDATES
from core.clickhouse_manager import CH_DB, META_DB, ClickHouseManager
from core.logger import get_logger
from core.meta import clear_metadata_table
from core.schema import is_numeric_type, q_ident

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

    def __init__(self, db: ClickHouseManager):
        self.db = db

    def _to_q_ident_list(self, columns_str: str) -> str:
        return ", ".join(q_ident(c.strip()) for c in columns_str.split(","))

    def _to_is_not_null_cond(self, columns_str: str) -> str:
        return " AND ".join(f"{q_ident(c.strip())} IS NOT NULL" for c in columns_str.split(","))

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

        source_cols = self._to_q_ident_list(source_column)
        target_cols = self._to_q_ident_list(primary_key.column_name)

        source_not_null = self._to_is_not_null_cond(source_column)
        target_not_null = self._to_is_not_null_cond(primary_key.column_name)

        limit_clause = f"LIMIT {limit_rows}" if limit_rows is not None else ""

        sql = f"""
        WITH
            source_values AS (
                SELECT tuple({source_cols}) AS value
                FROM {source_ref}
                WHERE {source_not_null}
                {limit_clause}
            ),
            target_values AS (
                SELECT DISTINCT tuple({target_cols}) AS value
                FROM {target_ref}
                WHERE {target_not_null}
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
        """

        sql = f"""
        SELECT
            table_name,
            column_name,
            column_type
        FROM {q_ident(META_DB)}.column_profiles
        WHERE database_name = %(database)s
          AND null_ratio < 1
          AND NOT startsWith(column_name, '__')
        ORDER BY table_name, column_name
        """

        rows = self.db.query(sql, parameters={"database": CH_DB}).result_rows

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
        max_composite_cols: int = EVALUATE_CANDIDATES.get(
            "COMPOSITE_KEY_COLUMN_RESTRICTION",
            3,
        ),
        limit_rows: int | None = EVALUATE_CANDIDATES.get("JOIN_SAMPLE_ROWS"),
        source_columns: list[SourceColumn] | None = None,
        max_workers: int | None = None,
    ) -> list[JoinPrimaryKeyCandidate]:
        """
        Discover foreign-key relationships against primary-key candidates.
        """

        from datetime import datetime
        from colorama import Fore, Style

        if source_columns is None:
            source_columns = self.load_source_columns()
        stats = self.load_column_stats()
        source_columns = self.prefilter_source_columns(
            primary_keys=primary_keys,
            source_columns=source_columns,
            stats=stats,
        )
        cols_by_table: dict[str, list[SourceColumn]] = defaultdict(list)
        cols_by_table_type: dict[str, dict[str, list[SourceColumn]]] = defaultdict(
            lambda: defaultdict(list)
        )
        for col in source_columns:
            clean_type = self._clean_type(col.column_type)
            cols_by_table[col.table_name].append(col)
            cols_by_table_type[col.table_name][clean_type].append(col)

        jobs: list[tuple[str, str, PrimaryKeyCandidate]] = []
        for primary_key in primary_keys:

            target_cols = [c.strip() for c in primary_key.column_name.split(",")]
            target_types = [self._clean_type(t.strip()) for t in primary_key.column_type.split(",")]
            is_composite = len(target_cols) > 1
            if is_composite and len(target_cols) > max_composite_cols:
                logger.info(
                    "[SKIP] composite PK is too long (%s cols): %s.%s",
                    len(target_cols),
                    primary_key.table_name,
                    primary_key.column_name,
                )
                continue
            for table_name in cols_by_table:

                if table_name == primary_key.table_name:
                    continue
                valid_source_combos = []
                if not is_composite:
                    for src in cols_by_table_type[table_name].get(target_types[0], []):
                        if not self.should_skip_pair((src,), primary_key):
                            valid_source_combos.append(src.column_name)
                else:
                    pools = [
                        cols_by_table_type[table_name].get(target_type, [])
                        for target_type in target_types
                    ]
                    if any(len(pool) == 0 for pool in pools):
                        continue
                    for combo in itertools.product(*pools):
                        if len({col.column_name for col in combo}) != len(combo):
                            continue
                        if self.should_skip_pair(combo, primary_key):
                            continue
                        valid_source_combos.append(", ".join(col.column_name for col in combo))
                for combo_str in valid_source_combos:
                    jobs.append((table_name, combo_str, primary_key))

        if not jobs:
            return []

        def _evaluate(job: tuple[str, str, PrimaryKeyCandidate]) -> JoinPrimaryKeyCandidate:
            table_name, combo_str, primary_key = job
            return self.evaluate_join_to_primary_key(
                source_table=table_name,
                source_column=combo_str,
                primary_key=primary_key,
                limit_rows=limit_rows,
            )

        candidates: list[JoinPrimaryKeyCandidate] = []
        try:
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                for result in executor.map(_evaluate, jobs):
                    if result.join_success_ratio >= min_success_ratio:
                        candidates.append(result)
        finally:
            self.db.close_all()

        return candidates

    def load_column_stats(self) -> dict[tuple[str, str], dict]:
        """
        Load column statistics from column_profiles.
        """

        sql = f"""
        SELECT
            table_name,
            column_name,
            column_type,
            distinct_count,
            min_value,
            max_value
        FROM {q_ident(META_DB)}.column_profiles
        WHERE database_name = %(database)s
          AND null_ratio < 1
          AND NOT startsWith(column_name, '__')
        """

        rows = self.db.query(sql, parameters={"database": CH_DB}).result_rows

        return {
            (row[0], row[1]): {
                "column_type": row[2],
                "distinct_count": row[3],
                "min_value": row[4],
                "max_value": row[5],
            }
            for row in rows
        }

    def prefilter_source_columns(
        self,
        primary_keys: list[PrimaryKeyCandidate],
        source_columns: list[SourceColumn],
        stats: dict[tuple[str, str], dict],
    ) -> list[SourceColumn]:
        """
        Remove source columns that cannot point to any known PK column.
        """

        pk_column_stats = []

        for pk in primary_keys:
            pk_columns = [c.strip() for c in pk.column_name.split(",")]
            pk_types = [self._clean_type(t.strip()) for t in pk.column_type.split(",")]

            for pk_col, pk_type in zip(pk_columns, pk_types, strict=False):
                pk_stat = stats.get((pk.table_name, pk_col))

                if pk_stat:
                    pk_column_stats.append(
                        {
                            "table_name": pk.table_name,
                            "column_name": pk_col,
                            "column_type": pk_type,
                            "distinct_count": pk_stat["distinct_count"],
                            "min_value": pk_stat["min_value"],
                            "max_value": pk_stat["max_value"],
                        }
                    )

        kept = []
        eliminated = 0

        for src in source_columns:
            src_stat = stats.get((src.table_name, src.column_name))

            if not src_stat:
                kept.append(src)
                continue

            src_type = self._clean_type(src.column_type)
            src_distinct = src_stat["distinct_count"]
            src_min = src_stat["min_value"]
            src_max = src_stat["max_value"]
            is_numeric = is_numeric_type(src.column_type)

            passes = False

            for pk_stat in pk_column_stats:
                if pk_stat["table_name"] == src.table_name:
                    continue

                if pk_stat["column_type"] != src_type:
                    continue

                pk_distinct = pk_stat["distinct_count"]
                margin = EVALUATE_CANDIDATES.get("Filter_margin", 1.05)

                if src_distinct > pk_distinct * margin:
                    continue

                if is_numeric and self._has_range_values(
                    src_min,
                    src_max,
                    pk_stat["min_value"],
                    pk_stat["max_value"],
                ):
                    try:
                        if float(src_min) < float(pk_stat["min_value"]):
                            continue

                        if float(src_max) > float(pk_stat["max_value"]):
                            continue

                    except (ValueError, TypeError):
                        pass

                passes = True
                break

            if passes:
                kept.append(src)
            else:
                eliminated += 1

        logger.info(
            "[PREFILTER] %s columns -> %s kept (%s removed)",
            len(source_columns),
            len(kept),
            eliminated,
        )

        return kept

    def store_candidates(
        self,
        candidates: list[JoinPrimaryKeyCandidate],
    ) -> None:
        """
        Store inferred join candidates in metadata.
        """

        clear_metadata_table(self.db, "join_candidates")

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

    @staticmethod
    def _has_range_values(*values: object) -> bool:
        return all(value is not None and value != "" for value in values)

    @classmethod
    def should_skip_pair(
        cls,
        source_combo: tuple[SourceColumn, ...],
        primary_key: PrimaryKeyCandidate,
    ) -> bool:
        """
        Return True when a source combination cannot match the target PK.
        """

        if not source_combo:
            return True

        same_table = source_combo[0].table_name == primary_key.table_name
        if same_table:
            return True

        target_types = [cls._clean_type(t.strip()) for t in primary_key.column_type.split(",")]

        if len(source_combo) != len(target_types):
            return True

        for src, target_type in zip(source_combo, target_types, strict=False):
            if cls._clean_type(src.column_type) != target_type:
                return True

        return False

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