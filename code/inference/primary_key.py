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


def infer_primary_key_candidates(
    client,
    threshold: float = 0.99,
) -> list[PrimaryKeyCandidate]:
    """
    Infer simple primary-key candidates from stored column profiles.

    A column is considered a simple primary-key candidate when it is complete
    and nearly unique. The confidence score combines uniqueness and non-null
    density, making the rule explicit and reproducible.
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


    rows = client.query(sql, parameters={"threshold": threshold}).result_rows

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
                reason="complete_and_unique_column",
            )
        )

    return candidates


def print_primary_key_candidates(candidates: list[PrimaryKeyCandidate]) -> None:
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
