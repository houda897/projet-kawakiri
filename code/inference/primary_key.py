from __future__ import annotations

from dataclasses import asdict, dataclass

from core.clickhouse_manager import CH_DB, META_DB, ClickHouseManager
from core.logger import get_logger
from core.meta import clear_metadata_table
from core.schema import q_ident
from inference.composite_key import CompositeKeyEngine
from inference.key_ranking import KeyRankingPolicy, RankedKeyCandidate
from inference.low_cardinality import LowCardinalityAnalyzer

logger = get_logger(__name__)


@dataclass
class PrimaryKeyCandidate:
    """
    Official primary-key candidate selected by the inference engine.
    """

    database_name: str
    table_name: str
    column_name: str
    column_type: str
    rows: int
    null_ratio: float
    uniqueness_ratio: float
    identifiability_score: float
    confidence: float
    reason: str


class PrimaryKeyEngine:
    """
    Infer primary-key candidates from column profiles and identifiability scores.

    This engine is the only component that makes the official primary-key
    decision. Other components provide evidence used for ranking.
    """

    def __init__(self, db: ClickHouseManager):
        self.db = db
        self.low_cardinality_analyzer = LowCardinalityAnalyzer(db)
        self.ranking_policy = KeyRankingPolicy()
        self.composite_key_engine = CompositeKeyEngine(db)

    def infer_candidates(
        self,
        threshold: float = 0.99,
    ) -> list[PrimaryKeyCandidate]:
        """
        Infer official primary-key candidates, including composite keys when needed.
        """

        simple_candidates = self.infer_ranked_simple_candidates(threshold=threshold)

        tables_without_pk = self.find_tables_without_candidates(simple_candidates)

        low_cardinality_columns = self.low_cardinality_analyzer.to_column_name_set(
            self.low_cardinality_analyzer.find_columns()
        )

        composite_candidates = self.composite_key_engine.generate_composite_candidates(
            tables_without_pk=tables_without_pk,
            low_cardinality_columns=low_cardinality_columns,
        )

        logical_table_candidates = self.infer_logical_table_key_candidates(
            threshold=threshold,
            low_cardinality_columns=low_cardinality_columns,
        )

        all_candidates = simple_candidates + composite_candidates + logical_table_candidates
        best_by_table = self.ranking_policy.select_best_by_table(all_candidates)
        best_by_table = self.apply_logical_table_key_overrides(
            best_by_table,
            logical_table_candidates,
        )

        return [self.to_primary_key_candidate(candidate) for candidate in best_by_table.values()]

    def infer_ranked_simple_candidates(
        self,
        threshold: float = 0.99,
    ) -> list[RankedKeyCandidate]:
        """
        Build ranked simple-key candidates from metadata.
        """

        low_cardinality_columns = self.low_cardinality_analyzer.to_column_name_set(
            self.low_cardinality_analyzer.find_columns()
        )

        sql = f"""
        SELECT
            p.database_name,
            p.table_name,
            p.column_name,
            p.column_type,
            p.rows,
            p.null_ratio,
            p.uniqueness_ratio,
            coalesce(i.identifiability_score, 0.0) AS identifiability_score
        FROM {q_ident(META_DB)}.column_profiles AS p
        LEFT JOIN {q_ident(META_DB)}.identifiability_scores AS i
            ON p.database_name = i.database_name
           AND p.table_name = i.table_name
           AND p.column_name = i.column_name
        WHERE p.database_name = %(database)s
          AND p.uniqueness_ratio >= %(threshold)s
          AND p.null_ratio <= 0.000001
          AND NOT startsWith(p.column_name, '__')
        ORDER BY p.table_name, p.column_name
        """

        rows = self.db.query(
            sql,
            parameters={"threshold": threshold, "database": CH_DB},
        ).result_rows

        candidates = []

        for row in rows:
            candidates.append(
                self.ranking_policy.build_candidate(
                    database_name=row[0],
                    table_name=row[1],
                    column_names=(row[2],),
                    column_types=(row[3],),
                    rows=row[4],
                    null_ratio=row[5],
                    uniqueness_ratio=row[6],
                    identifiability_score=row[7],
                    low_cardinality_columns=low_cardinality_columns,
                )
            )

        return self.ranking_policy.rank(candidates)

    def infer_logical_table_key_candidates(
        self,
        *,
        threshold: float,
        low_cardinality_columns: set[tuple[str, str]],
    ) -> list[RankedKeyCandidate]:
        """
        Build key candidates from materialized logical table determinants.

        Logical dimensions are created from a stable determinant. If that
        determinant is composite, a nearly unique single column must not replace
        it, otherwise later joins lose one FK column and can fan out.
        """

        sql = f"""
        SELECT
            logical_table_name,
            determinant_columns
        FROM {q_ident(META_DB)}.logical_tables
        WHERE database_name = %(database)s
          AND logical_table_role = 'DIMENSION_CANDIDATE'
          AND determinant_columns != ''
        ORDER BY logical_table_name
        """

        rows = self.db.query(sql, parameters={"database": CH_DB}).result_rows
        candidates = []

        for table_name, determinant_columns in rows:
            column_names = self.split_columns(determinant_columns)
            if not column_names:
                continue

            column_types = self.load_column_types(table_name, column_names)
            if len(column_types) != len(column_names):
                continue

            rows_count, null_ratio, uniqueness_ratio = self.compute_key_shape(
                table_name,
                column_names,
            )
            if rows_count <= 0:
                continue
            if null_ratio > 0.000001 or uniqueness_ratio < threshold:
                continue

            candidates.append(
                self.ranking_policy.build_candidate(
                    database_name=CH_DB,
                    table_name=table_name,
                    column_names=column_names,
                    column_types=column_types,
                    rows=rows_count,
                    null_ratio=null_ratio,
                    uniqueness_ratio=uniqueness_ratio,
                    identifiability_score=self.load_mean_identifiability_score(
                        table_name,
                        column_names,
                    ),
                    low_cardinality_columns=low_cardinality_columns,
                )
            )

        return self.ranking_policy.rank(candidates)

    def load_column_types(
        self,
        table_name: str,
        column_names: tuple[str, ...],
    ) -> tuple[str, ...]:
        """
        Load ClickHouse types for the requested columns in determinant order.
        """

        sql = """
        SELECT name, type
        FROM system.columns
        WHERE database = %(database)s
          AND table = %(table)s
        """

        rows = self.db.query(
            sql,
            parameters={"database": CH_DB, "table": table_name},
        ).result_rows
        type_by_column = {row[0]: row[1] for row in rows}

        return tuple(
            type_by_column[column_name]
            for column_name in column_names
            if column_name in type_by_column
        )

    def compute_key_shape(
        self,
        table_name: str,
        column_names: tuple[str, ...],
    ) -> tuple[int, float, float]:
        """
        Compute completeness and uniqueness for a determinant tuple.
        """

        null_checks = " OR ".join(
            f"isNull({q_ident(column_name)})" for column_name in column_names
        )
        tuple_expression = ", ".join(q_ident(column_name) for column_name in column_names)

        sql = f"""
        SELECT
            count() AS rows,
            countIf({null_checks}) AS null_rows,
            uniqExact(tuple({tuple_expression})) AS distinct_rows
        FROM {q_ident(CH_DB)}.{q_ident(table_name)}
        """

        row = self.db.query(sql).result_rows[0]
        rows_count = int(row[0] or 0)
        if rows_count <= 0:
            return 0, 1.0, 0.0

        null_ratio = float(row[1] or 0) / rows_count
        uniqueness_ratio = float(row[2] or 0) / rows_count
        return rows_count, null_ratio, uniqueness_ratio

    def load_mean_identifiability_score(
        self,
        table_name: str,
        column_names: tuple[str, ...],
    ) -> float:
        """
        Average stored identifiability evidence for determinant columns.
        """

        quoted_columns = ", ".join(repr(column_name) for column_name in column_names)
        sql = f"""
        SELECT coalesce(avg(identifiability_score), 0.0)
        FROM {q_ident(META_DB)}.identifiability_scores
        WHERE database_name = %(database)s
          AND table_name = %(table)s
          AND column_name IN ({quoted_columns})
        """

        rows = self.db.query(
            sql,
            parameters={"database": CH_DB, "table": table_name},
        ).result_rows
        if not rows:
            return 0.0

        return float(rows[0][0] or 0.0)

    @staticmethod
    def apply_logical_table_key_overrides(
        best_by_table: dict[str, RankedKeyCandidate],
        logical_table_candidates: list[RankedKeyCandidate],
    ) -> dict[str, RankedKeyCandidate]:
        """
        Prefer logical dimension determinants over accidental simple keys.
        """

        for candidate in logical_table_candidates:
            best_by_table[candidate.table_name] = candidate

        return best_by_table

    def find_tables_without_candidates(
        self,
        candidates: list[RankedKeyCandidate],
    ) -> list[str]:
        """
        Find tables that do not already have a simple primary-key candidate.
        """

        sql = f"""
        SELECT DISTINCT table_name
        FROM {q_ident(META_DB)}.column_profiles
        WHERE database_name = %(database)s
          AND NOT startsWith(column_name, '__')
        ORDER BY table_name
        """

        all_tables = {
            row[0] for row in self.db.query(sql, parameters={"database": CH_DB}).result_rows
        }
        tables_with_pk = {candidate.table_name for candidate in candidates}

        return sorted(all_tables - tables_with_pk)

    def to_primary_key_candidate(
        self,
        candidate: RankedKeyCandidate,
    ) -> PrimaryKeyCandidate:
        """
        Convert a ranked candidate into the official primary-key object.
        """

        return PrimaryKeyCandidate(
            database_name=candidate.database_name,
            table_name=candidate.table_name,
            column_name=", ".join(candidate.column_names),
            column_type=", ".join(candidate.column_types),
            rows=candidate.rows,
            null_ratio=candidate.null_ratio,
            uniqueness_ratio=candidate.uniqueness_ratio,
            identifiability_score=candidate.identifiability_score,
            confidence=candidate.confidence,
            reason=(
                f"key_type={self.key_type(candidate)}; "
                "confidence=weighted_uniqueness_and_identifiability; "
                f"ranking={candidate.rank_reason}"
            ),
        )

    def store_candidates(
        self,
        candidates: list[PrimaryKeyCandidate],
    ) -> None:
        """
        Persist primary-key candidates into the metadata table.
        """

        clear_metadata_table(self.db, "primary_key_candidates")

        if not candidates:
            return

        rows = [
            [
                candidate.database_name,
                candidate.table_name,
                candidate.column_name,
                candidate.column_type,
                candidate.rows,
                candidate.null_ratio,
                candidate.uniqueness_ratio,
                candidate.identifiability_score,
                candidate.confidence,
                candidate.reason,
            ]
            for candidate in candidates
        ]

        self.db.insert(
            f"{META_DB}.primary_key_candidates",
            rows,
            column_names=[
                "database_name",
                "table_name",
                "column_name",
                "column_type",
                "rows",
                "null_ratio",
                "uniqueness_ratio",
                "identifiability_score",
                "confidence",
                "reason",
            ],
        )

    def load_candidates(self) -> list[PrimaryKeyCandidate]:
        """
        Load primary-key candidates already stored in metadata.
        """

        sql = f"""
        SELECT
            database_name,
            table_name,
            column_name,
            column_type,
            rows,
            null_ratio,
            uniqueness_ratio,
            identifiability_score,
            confidence,
            reason
        FROM {q_ident(META_DB)}.primary_key_candidates
        WHERE database_name = %(database)s
        ORDER BY table_name, confidence DESC, column_name
        """

        rows = self.db.query(sql, parameters={"database": CH_DB}).result_rows

        return [
            PrimaryKeyCandidate(
                database_name=row[0],
                table_name=row[1],
                column_name=row[2],
                column_type=row[3],
                rows=row[4],
                null_ratio=row[5],
                uniqueness_ratio=row[6],
                identifiability_score=row[7],
                confidence=row[8],
                reason=row[9],
            )
            for row in rows
        ]

    @staticmethod
    def key_type(candidate: RankedKeyCandidate) -> str:
        """
        Return whether the selected key is simple or composite.
        """

        if len(candidate.column_names) > 1:
            return "composite"

        return "simple"

    @staticmethod
    def split_columns(columns: str) -> tuple[str, ...]:
        return tuple(column.strip() for column in columns.split(",") if column.strip())

    @staticmethod
    def print_candidates(candidates: list[PrimaryKeyCandidate]) -> None:
        """
        Log all primary-key candidates.
        """

        if not candidates:
            logger.info("No primary-key candidates found.")
            return

        for candidate in candidates:
            logger.info(
                "\n\nPK | %s.%s -> %s | confidence=%s | uniqueness=%s | reason=%s\n",
                candidate.database_name,
                candidate.table_name,
                candidate.column_name,
                candidate.confidence,
                candidate.uniqueness_ratio,
                candidate.reason,
            )


def candidates_to_dicts(candidates: list[PrimaryKeyCandidate]) -> list[dict]:
    """
    Serialize a list of PrimaryKeyCandidate objects to plain dicts.
    """

    return [asdict(candidate) for candidate in candidates]
