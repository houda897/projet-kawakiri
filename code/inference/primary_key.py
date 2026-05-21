from __future__ import annotations

from dataclasses import asdict, dataclass

from core.clickhouse_manager import META_DB, clickhouse_manager
from core.logger import get_logger
from core.schema import q_ident

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

    def infer_candidates(
        self,
        threshold: float = 0.99,
    ) -> list[PrimaryKeyCandidate]:
        """
        Infer official simple primary-key candidates.
        """

        ranked_candidates = self.infer_ranked_simple_candidates(threshold=threshold)
        best_by_table = self.ranking_policy.select_best_by_table(ranked_candidates)

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
        WHERE p.uniqueness_ratio >= %(threshold)s
          AND p.null_ratio <= 0.000001
          AND NOT startsWith(p.column_name, '__')
        ORDER BY p.table_name, p.column_name
        """

        rows = self.db.query(sql, parameters={"threshold": threshold}).result_rows

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
                "hard_rule=unique_and_complete; "
                "confidence=0.7*uniqueness_ratio+0.3*identifiability_score; "
                f"ranking={candidate.rank_reason}"
            ),
        )

    def store_candidates(
        self,
        candidates: list[PrimaryKeyCandidate],
    ) -> None:
        """
        Persist primary-key candidates into the metadata table.

        Does nothing when the list is empty. Stored candidates are later read
        by JoinEngine to evaluate FK relationships.
        """
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

    @staticmethod
    def print_candidates(candidates: list[PrimaryKeyCandidate]) -> None:
        """Log all primary-key candidates grouped by table."""
        if not candidates:
            logger.info("No primary-key candidates found.")
            return

        current_table = None

        for candidate in candidates:
            if candidate.table_name != current_table:
                current_table = candidate.table_name
                logger.info("=== %s ===", candidate.table_name)

            logger.info(
                "%s (%s) | confidence=%s | identifiability=%s | reason=%s",
                candidate.column_name,
                candidate.column_type,
                candidate.confidence,
                candidate.identifiability_score,
                candidate.reason,
            )


def candidates_to_dicts(candidates: list[PrimaryKeyCandidate]) -> list[dict]:
    """Serialize a list of PrimaryKeyCandidate objects to plain dicts."""
    return [asdict(candidate) for candidate in candidates]
