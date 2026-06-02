from __future__ import annotations

from dataclasses import dataclass

from core.clickhouse_manager import CH_DB, META_DB, clickhouse_manager
from core.logger import get_logger
from core.meta import clear_metadata_table
from core.schema import q_ident

from inference.primary_key import PrimaryKeyCandidate

from core.clickhouse_manager import clickhouse_manager

from config.scoring import EVALUATE_CANDIDATES

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
        max_composite_cols: int = EVALUATE_CANDIDATES["COMPOSITE_KEY_COLUMN_RESTRICTION"],
        source_columns : list[SourceColumn] |None = None
    ) -> list[JoinPrimaryKeyCandidate]:
        import itertools
        from collections import defaultdict

        '''
        Discover all foreign-key relationships across the database.

        For each known primary key, iterates over every other table and identifies
        source columns whose values are statistically covered by that PK, using
        a LEFT JOIN success ratio. Only pairs at or above min_success_ratio are
        returned as valid FK candidates.

        Composite PKs exceeding max_composite_cols are skipped entirely — a PK
        with many columns is almost certainly a fact-table row key rather than
        a referenceable dimension key, and the cartesian product of candidate
        column combinations would be computationally prohibitive.

        Source columns are looked up via a type index (table → type → columns)
        to avoid scanning all columns on every iteration. For composite PKs,
        only combinations where each position has a type-compatible column are
        generated (itertools.product over per-position pools), and combinations
        reusing the same source column are discarded.
        '''

        if source_columns is None :
            source_columns = self.load_source_columns()

        cols_by_table = defaultdict(list)
        cols_by_table_type: dict[str, dict[str, list]] = defaultdict(lambda: defaultdict(list))

        for col in source_columns:
            cols_by_table[col.table_name].append(col)
            cols_by_table_type[col.table_name][self._clean_type(col.column_type)].append(col)

        candidates = []

        for primary_key in primary_keys:
            target_cols  = [c.strip() for c in primary_key.column_name.split(",")]
            target_types = [self._clean_type(t.strip()) for t in primary_key.column_type.split(",")]
            is_composite = len(target_cols) > 1

            if is_composite and len(target_cols) > max_composite_cols:
                logger.info(f"[SKIP] composite PK is too long ({len(target_cols)} cols) : "
                    f"{primary_key.table_name}.{primary_key.column_name}")
                continue

            for table_name in cols_by_table:

                if table_name == primary_key.table_name:
                    continue

                valid_source_combos = []

                if not is_composite:
                    for src in cols_by_table_type[table_name].get(target_types[0], []):
                        valid_source_combos.append(src.column_name)

                else:
                    pools = [
                        cols_by_table_type[table_name].get(t, [])
                        for t in target_types
                    ]
                    if any(len(p) == 0 for p in pools):
                        continue

                    for combo in itertools.product(*pools):

                        if len({c.column_name for c in combo}) != len(combo):
                            continue
                        valid_source_combos.append(", ".join(c.column_name for c in combo))

                for combo_str in valid_source_combos:

                    result = self.evaluate_join_to_primary_key(
                        source_table=table_name,
                        source_column=combo_str,
                        primary_key=primary_key,
                    )
                    if result.join_success_ratio >= min_success_ratio:
                        candidates.append(result)

        return candidates
    
    def load_column_stats(self) -> dict[tuple[str, str], dict]:
        '''
        Load stats from column_profile sorted by (table_name, column_name).
        '''
        sql = f"""
            SELECT
                table_name,
                column_name,
                column_type,
                distinct_count,
                min_value,
                max_value
            FROM {q_ident(META_DB)}.column_profiles
            WHERE null_ratio < 1
            AND NOT startsWith(column_name, '__')
        """
        rows = self.db.query(sql).result_rows
        return {
            (row[0], row[1]): {
                "column_type": row[2],
                "distinct_count": row[3],
                "min_value": row[4],
                "max_value": row[5],
            }
            for row in rows
        }


    def _is_numeric_type(self, col_type: str) -> bool:
        """Retourne True si le type est numérique (Int, Float, Decimal)."""
        cleaned = self._clean_type(col_type)
        return any(cleaned.startswith(t) for t in ("Int", "UInt", "Float", "Decimal"))


    def prefilter_source_columns(
        self,
        primary_keys: list[PrimaryKeyCandidate],
        source_columns: list[SourceColumn],
        stats: dict[tuple[str, str], dict],
    ) -> list[SourceColumn]:
        '''
        Remove source columns that cannot be a FK pointing to any known PK.

        Two statistical filters are applied without issuing any SQL query:
        Cardinality     : a FK column cannot have more distinct values than
                            its target PK column (some values would be unmatched).
        Range           : for numeric types, the source range must be a subset
                            of the PK range — if min(src) < min(pk) or
                            max(src) > max(pk), those values will never join.

        A column is kept if it passes both filters against at least one
        type-compatible PK. Columns with no recorded stats are kept by default
        to avoid false exclusions.
        '''
        pk_stats: dict[tuple[str, str], dict] = {}
        for pk in primary_keys:
            for col_name in [c.strip() for c in pk.column_name.split(",")]:
                key = (pk.table_name, col_name)
                if key in stats:
                    pk_stats[key] = stats[key]

        kept = []
        eliminated = 0

        for src in source_columns:
            src_stat = stats.get((src.table_name, src.column_name))
            if not src_stat:
                kept.append(src)
                continue

            src_distinct = src_stat["distinct_count"]
            src_min      = src_stat["min_value"]
            src_max      = src_stat["max_value"]
            is_numeric   = self._is_numeric_type(src.column_type)

            passes = False
            for pk in primary_keys:
                for pk_col in [c.strip() for c in pk.column_name.split(",")]:

                    # ── Compatibilité structurelle centralisée dans should_skip_pair ──
                    dummy_src = (src,)
                    if self.should_skip_pair(dummy_src, pk):
                        continue

                    pk_stat = pk_stats.get((pk.table_name, pk_col))
                    if not pk_stat:
                        passes = True  # pas de stats PK → on garde par sécurité
                        break

                    # ── Filtre 1 : cardinalité avec marge ──
                    pk_distinct = pk_stat["distinct_count"]
                    if src_distinct > pk_distinct * EVALUATE_CANDIDATES["Filter_margin"]:
                        continue

                    # ── Filtre 2 : plage numérique ──
                    if is_numeric and all([src_min, src_max,
                                        pk_stat["min_value"], pk_stat["max_value"]]):
                        try:
                            if float(src_min) < float(pk_stat["min_value"]):
                                continue
                            if float(src_max) > float(pk_stat["max_value"]):
                                continue
                        except (ValueError, TypeError):
                            pass  # conversion impossible → on ne filtre pas

                    passes = True
                    break

                if passes:
                    break

            if passes:
                kept.append(src)
            else:
                eliminated += 1
                logger.info(f" Col name : {src.column_name}, col type : {src.column_type}, "
                    f"table name : {src.table_name}")

        logger.info(f"[PREFILTER] {len(source_columns)} columns → {len(kept)} kept "
            f"({eliminated} removed)")
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

    @classmethod
    def should_skip_pair(
        cls,
        source_combo: tuple[SourceColumn, ...],
        primary_key: PrimaryKeyCandidate,
    ) -> bool:
        """
        Return True if this source combination / primary-key pair cannot be a valid FK relationship.

        A pair is skipped when the source and target belong to the same table,
        or when their base ClickHouse types are incompatible (e.g. String vs Int64).
        Nullable wrappers are stripped before comparing types.
        """
        if not source_combo:
            return True

        same_table = source_combo[0].table_name == primary_key.table_name
        if same_table:
            return True

        target_types = [cls._clean_type(t.strip()) for t in primary_key.column_type.split(",")]

        if len(source_combo) != len(target_types):
            return True

        for src, t_type in zip(source_combo, target_types, strict=False):
            if cls._clean_type(src.column_type) != t_type:
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
