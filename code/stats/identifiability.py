from __future__ import annotations

from dataclasses import dataclass

from config.scoring import IDENTIFIABILITY_THRESHOLDS, IDENTIFIABILITY_WEIGHTS
from core.clickhouse_manager import META_DB, clickhouse_manager
from core.logger import get_logger
from core.schema import q_ident

logger = get_logger(__name__)


@dataclass
class IdentifiabilityResult:
    """
    Column-level score estimating how strongly a column identifies records.

    This score is descriptive: it does not decide whether a column is a primary
    key. Primary-key decisions remain the responsibility of PrimaryKeyEngine.
    """

    database_name: str
    table_name: str
    column_name: str
    uniqueness_ratio: float
    entropy_ratio: float
    completeness: float
    identifiability_score: float
    diagnostic: str


class IdentifiabilityEngine:
    """
    Compute descriptive identifiability scores from column statistics.
    """

    def __init__(
        self,
        db: clickhouse_manager,
        weight_uniqueness: float = IDENTIFIABILITY_WEIGHTS["uniqueness"],
        weight_entropy: float = IDENTIFIABILITY_WEIGHTS["entropy"],
        weight_completeness: float = IDENTIFIABILITY_WEIGHTS["completeness"],
        threshold_high: float = IDENTIFIABILITY_THRESHOLDS["high"],
        threshold_medium: float = IDENTIFIABILITY_THRESHOLDS["medium"],
        threshold_low: float = IDENTIFIABILITY_THRESHOLDS["low"],
    ):
        self.db = db
        self.weight_uniqueness = weight_uniqueness
        self.weight_entropy = weight_entropy
        self.weight_completeness = weight_completeness
        self.threshold_high = threshold_high
        self.threshold_medium = threshold_medium
        self.threshold_low = threshold_low

        self.validate_weights()

    def validate_weights(self) -> None:
        """
        Ensure the three weights sum to 1.

        Raises ValueError if the sum deviates by more than 0.0001, which would
        silently bias every identifiability score computed by this engine.
        """
        total = (
            self.weight_uniqueness
            + self.weight_entropy
            + self.weight_completeness
        )

        if not 0.9999 <= total <= 1.0001:
            raise ValueError(
                f"Identifiability weights must sum to 1. Current sum: {round(total, 4)}"
            )

    def compute_scores(self) -> list[IdentifiabilityResult]:
        """
        Compute identifiability scores from the latest available column statistics.
        """

        sql = f"""
        SELECT
            database_name,
            table_name,
            column_name,
            rows,
            distinct_count,
            entropy_ratio,
            sparsity
        FROM {q_ident(META_DB)}.column_stats
        WHERE run_ts = (
            SELECT max(run_ts)
            FROM {q_ident(META_DB)}.column_stats
        )
        ORDER BY table_name, column_name
        """

        rows = self.db.query(sql).result_rows
        results = []

        for row in rows:
            database_name = row[0]
            table_name = row[1]
            column_name = row[2]
            total_rows = row[3]
            distinct_count = row[4]
            entropy_ratio = row[5]
            sparsity = row[6]

            uniqueness_ratio = distinct_count / total_rows if total_rows > 0 else 0.0
            completeness = 1 - sparsity

            score = (
                self.weight_uniqueness * uniqueness_ratio
                + self.weight_entropy * entropy_ratio
                + self.weight_completeness * completeness
            )

            results.append(
                IdentifiabilityResult(
                    database_name=database_name,
                    table_name=table_name,
                    column_name=column_name,
                    uniqueness_ratio=round(uniqueness_ratio, 6),
                    entropy_ratio=round(entropy_ratio, 6),
                    completeness=round(completeness, 6),
                    identifiability_score=round(score, 6),
                    diagnostic=self.diagnose(score),
                )
            )

        return results

    def diagnose(self, score: float) -> str:
        """
        Convert a numeric identifiability score into a human-readable diagnostic label.

        Thresholds are configured in config/scoring.py so they can be adjusted
        without touching the engine logic.
        """
        if score >= self.threshold_high:
            return "HIGH_IDENTIFIABILITY"

        if score >= self.threshold_medium:
            return "MEDIUM_IDENTIFIABILITY"

        if score >= self.threshold_low:
            return "LOW_IDENTIFIABILITY"

        return "VERY_LOW_IDENTIFIABILITY"

    def store_scores(self, results: list[IdentifiabilityResult]) -> None:
        """
        Persist identifiability scores into the metadata table.

        Does nothing if the list is empty. Scores are later read by
        PrimaryKeyEngine to rank key candidates.
        """
        if not results:
            return

        rows = [
            [
                result.database_name,
                result.table_name,
                result.column_name,
                result.uniqueness_ratio,
                result.entropy_ratio,
                result.completeness,
                result.identifiability_score,
                result.diagnostic,
            ]
            for result in results
        ]

        self.db.insert(
            f"{META_DB}.identifiability_scores",
            rows,
            column_names=[
                "database_name",
                "table_name",
                "column_name",
                "uniqueness_ratio",
                "entropy_ratio",
                "completeness",
                "identifiability_score",
                "diagnostic",
            ],
        )

    @staticmethod
    def print_scores(results: list[IdentifiabilityResult]) -> None:
        """Log all identifiability scores grouped by table."""
        if not results:
            logger.info("No identifiability scores found.")
            return

        current_table = None

        for result in results:
            if result.table_name != current_table:
                current_table = result.table_name
                logger.info("=== %s ===", result.table_name)

            logger.info(
                "%s | score=%s | diagnostic=%s",
                result.column_name,
                result.identifiability_score,
                result.diagnostic,
            )
