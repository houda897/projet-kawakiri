from __future__ import annotations

from dataclasses import asdict, dataclass

from core.client import META_DB
from core.schema import q_ident


@dataclass
class PrimaryKeyCandidate:
    """Candidate primary key inferred from column profiling metrics."""

    database_name: str
    table_name: str
    column_name: str
    column_type: str
    rows: int
    null_ratio: float
    uniqueness_ratio: float
    confidence: float
    reason: str


class PrimaryKeyEngine:
    def __init__(self, client):
        self.client = client

    def infer_candidates(
        self,
        threshold: float = 0.99,
    ) -> list[PrimaryKeyCandidate]:
        """
        Infer simple primary-key candidates from stored column profiles.
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
            round(uniqueness_ratio * (1 - null_ratio), 6) AS confidence
        FROM {q_ident(META_DB)}.column_profiles
        WHERE uniqueness_ratio >= %(threshold)s
        AND null_ratio <= 0.000001
        AND NOT startsWith(column_name, '__')
        ORDER BY table_name, confidence DESC, column_name
        """

        rows = self.client.query(sql, parameters={"threshold": threshold}).result_rows

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
                    confidence=row[7],
                    reason="confidence=uniqueness_ratio*(1-null_ratio)",
                )
            )

        return candidates

    def store_candidates(
        self,
        candidates: list[PrimaryKeyCandidate],
    ) -> None:
        if not candidates:
            return

        rows_to_insert = [
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

        self.client.insert(
            f"{META_DB}.primary_key_candidates",
            rows_to_insert,
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
        """
        Print inferred primary-key candidates in a compact human-readable format.
        """
        if not candidates:
            print("No primary-key candidates found.")
            return

        current_table = None
        for candidate in candidates:
            if candidate.table_name != current_table:
                current_table = candidate.table_name
                print(f"\n=== {candidate.table_name} ===")

            print(
                f"{candidate.column_name} "
                f"({candidate.column_type}) | "
                f"confidence={candidate.confidence} | "
                f"reason={candidate.reason}"
            )


def candidates_to_dicts(candidates: list[PrimaryKeyCandidate]) -> list[dict]:
    """
    Convert candidate objects to dictionaries for serialization or tests.
    """
    return [asdict(candidate) for candidate in candidates]
