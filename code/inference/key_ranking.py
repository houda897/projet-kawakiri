from __future__ import annotations

from dataclasses import dataclass

from config.scoring import PK_WEIGHTS


@dataclass
class RankedKeyCandidate:
    """
    Key candidate enriched with ranking evidence.

    The ranking favors minimal keys first, then candidates with more numeric
    attributes and stronger statistical evidence.
    """

    database_name: str
    table_name: str
    column_names: tuple[str, ...]
    column_types: tuple[str, ...]
    rows: int
    null_ratio: float
    uniqueness_ratio: float
    identifiability_score: float
    numeric_column_count: int
    low_cardinality_column_count: int
    confidence: float
    rank_reason: str


class KeyRankingPolicy:
    """
    Rank key candidates according to the project selection rule.
    """

    def build_candidate(
        self,
        *,
        database_name: str,
        table_name: str,
        column_names: tuple[str, ...],
        column_types: tuple[str, ...],
        rows: int,
        null_ratio: float,
        uniqueness_ratio: float,
        identifiability_score: float,
        low_cardinality_columns: set[tuple[str, str]],
    ) -> RankedKeyCandidate:
        """
        Build a ranked candidate from structural and statistical evidence.
        """

        numeric_count = self.count_numeric_columns(column_types)

        low_cardinality_count = sum(
            1
            for column_name in column_names
            if (table_name, column_name) in low_cardinality_columns
        )

        confidence = round(
            PK_WEIGHTS["uniqueness"] * uniqueness_ratio
            + PK_WEIGHTS["identifiability"] * identifiability_score,
            6,
        )

        return RankedKeyCandidate(
            database_name=database_name,
            table_name=table_name,
            column_names=column_names,
            column_types=column_types,
            rows=rows,
            null_ratio=null_ratio,
            uniqueness_ratio=uniqueness_ratio,
            identifiability_score=identifiability_score,
            numeric_column_count=numeric_count,
            low_cardinality_column_count=low_cardinality_count,
            confidence=confidence,
            rank_reason=(
                "rank=minimal_columns,numeric_preference,"
                "uniqueness,completeness,identifiability"
            ),
        )

    def rank(
        self,
        candidates: list[RankedKeyCandidate],
    ) -> list[RankedKeyCandidate]:
        """
        Sort candidates by the agreed selection rule.
        """

        return sorted(
            candidates,
            key=lambda candidate: (
                len(candidate.column_names),
                -candidate.numeric_column_count,
                candidate.low_cardinality_column_count,
                -candidate.uniqueness_ratio,
                candidate.null_ratio,
                -candidate.identifiability_score,
                -candidate.confidence,
            ),
        )

    def select_best_by_table(
        self,
        candidates: list[RankedKeyCandidate],
    ) -> dict[str, RankedKeyCandidate]:
        """
        Keep only the best ranked candidate for each table.
        """

        best_by_table = {}

        for candidate in self.rank(candidates):
            if candidate.table_name not in best_by_table:
                best_by_table[candidate.table_name] = candidate

        return best_by_table

    @classmethod
    def count_numeric_columns(cls, column_types: tuple[str, ...]) -> int:
        return sum(1 for column_type in column_types if cls.is_numeric_type(column_type))

    @classmethod
    def is_numeric_type(cls, column_type: str) -> bool:
        base_type = cls.normalize_type(column_type)

        return base_type.startswith(("Int", "UInt", "Float", "Decimal"))

    @staticmethod
    def normalize_type(column_type: str) -> str:
        return column_type.removeprefix("Nullable(").removesuffix(")")