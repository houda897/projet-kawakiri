from __future__ import annotations

from dataclasses import asdict, dataclass

from core.clickhouse_manager import CH_DB, META_DB, clickhouse_manager
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

    def __init__(self, db: clickhouse_manager):
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

        all_candidates = simple_candidates + composite_candidates
        best_by_table = self.ranking_policy.select_best_by_table(all_candidates)

        return [
            self.to_primary_key_candidate(candidate)
            for candidate in best_by_table.values()
        ]

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
            row[0]
            for row in self.db.query(sql, parameters={"database": CH_DB}).result_rows
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
            reason=(f"key_type={self.key_type(candidate)}; "
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
    def print_candidates(candidates: list[PrimaryKeyCandidate]) -> None:
        """
        Log all primary-key candidates.
        """
        from colorama import Fore,Style
        if not candidates:
            logger.info("No primary-key candidates found.")
            return

        for candidate in candidates:
            tab = f'{candidate.database_name}.{candidate.table_name}'
            pk = Fore.YELLOW + f'{candidate.column_name}' + Style.RESET_ALL
            logger.info(f'{tab:<40} -> {pk:<15} | confidence={candidate.confidence:<5} | uniqueness={candidate.uniqueness_ratio:<5} | reason={candidate.reason}')


def candidates_to_dicts(candidates: list[PrimaryKeyCandidate]) -> list[dict]:
    """
    Serialize a list of PrimaryKeyCandidate objects to plain dicts.
    """

    return [asdict(candidate) for candidate in candidates]
