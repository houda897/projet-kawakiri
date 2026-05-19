from __future__ import annotations

from dataclasses import asdict, dataclass

from core.logger import get_logger
from core.clickhouse_manager import clickhouse_manager, META_DB
from core.schema import q_ident

logger = get_logger(__name__)


@dataclass
class PrimaryKeyCandidate:
    database_name: str
    table_name: str
    column_name: str
    column_type: str
    rows: int
    null_ratio: float
    uniqueness_ratio: float
    entropy_ratio: float
    identifiability_score: float
    confidence: float
    reason: str



class PrimaryKeyEngine:
    def __init__(self, db: clickhouse_manager):
        self.db = db

    def infer_candidates(
        self,
        threshold: float = 0.99,
    ) -> list[PrimaryKeyCandidate]:
        """
        Infer columns that behave like simple primary keys.
        """
        sql = f"""
        SELECT
            p.database_name,
            p.table_name,
            p.column_name,
            p.column_type,
            p.rows,
            p.null_ratio,
            p.uniqueness_ratio,
            coalesce(i.entropy_ratio, 0.0) AS entropy_ratio,
            coalesce(i.identifiability_score, 0.0) AS identifiability_score,
            round(
                0.7 * p.uniqueness_ratio
                + 0.3 * coalesce(i.identifiability_score, 0.0),
                6
            ) AS confidence
        FROM {q_ident(META_DB)}.column_profiles AS p
        LEFT JOIN {q_ident(META_DB)}.identifiability_scores AS i
            ON p.database_name = i.database_name
        AND p.table_name = i.table_name
        AND p.column_name = i.column_name
        WHERE p.uniqueness_ratio >= %(threshold)s
        AND p.null_ratio <= 0.000001
        AND NOT startsWith(p.column_name, '__')
        ORDER BY p.table_name, confidence DESC, p.column_name
        """


        rows = self.db.query(sql, parameters={"threshold": threshold}).result_rows

        candidates = []
        for row in rows:
            candidates.append(
                PrimaryKeyCandidate(
                    database_name=row[0],
                    table_name=row[1],
                    column_name=row[2],
                    column_type=row[3],
                    rows=row[4],
                    null_ratio=row[5],
                    uniqueness_ratio=row[6],
                    entropy_ratio=row[7],
                    identifiability_score=row[8],
                    confidence=row[9],
                    reason="confidence=uniqueness_ratio*(1-null_ratio)",
                )
            )

        return candidates

    def store_candidates(self, candidates: list[PrimaryKeyCandidate]) -> None:
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
                "confidence",
                "reason",
            ],
        )

    @staticmethod
    def print_candidates(candidates: list[PrimaryKeyCandidate]) -> None:
        if not candidates:
            logger.info("No primary-key candidates found.")
            return

        current_table = None

        for candidate in candidates:
            if candidate.table_name != current_table:
                current_table = candidate.table_name
                logger.info("=== %s ===", candidate.table_name)

            logger.info(
                "%s (%s) | confidence=%s | reason=%s",
                candidate.column_name,
                candidate.column_type,
                candidate.confidence,
                candidate.reason,
            )


def candidates_to_dicts(candidates: list[PrimaryKeyCandidate]) -> list[dict]:
    return [asdict(candidate) for candidate in candidates]
