from __future__ import annotations

from dataclasses import dataclass

from core.clickhouse_manager import CH_DB, META_DB, clickhouse_manager
from core.logger import get_logger
from core.meta import clear_metadata_table
from core.schema import q_ident
from modeling.candidate_builder import DecisionModelCandidateBuilder
from modeling.decision_model import DecisionModelCandidate

logger = get_logger(__name__)


@dataclass(frozen=True)
class GranularityValidationResult:
    model_id: str
    fact_table: str
    grain_columns: tuple[str, ...]
    duplicate_count: int
    is_valid: bool
    reason: str


class GranularityValidator:
    """
    Validate that each fact row is identified by its dimension keys.
    """

    def __init__(self, db: clickhouse_manager, database: str = CH_DB):
        self.db = db
        self.database = database
        self.candidate_builder = DecisionModelCandidateBuilder(db)

    def validate_stored_candidates(self) -> list[GranularityValidationResult]:
        candidates = self.candidate_builder.load_candidates()

        if not candidates:
            raise ValueError(
                "No decision model candidates found. Run build-model-candidates first."
            )

        results = []
        for candidate in candidates:
            results.extend(self.validate(candidate))

        return results

    def validate(
        self,
        candidate: DecisionModelCandidate,
    ) -> list[GranularityValidationResult]:
        results = []

        for fact_table in candidate.fact_tables:
            grain_columns = self.build_fact_grain(candidate, fact_table)

            if not grain_columns:
                results.append(
                    GranularityValidationResult(
                        model_id=candidate.model_id,
                        fact_table=fact_table,
                        grain_columns=(),
                        duplicate_count=0,
                        is_valid=False,
                        reason="No dimension key found to define the fact grain.",
                    )
                )
                continue

            duplicate_count = self.count_duplicate_grain_rows(
                fact_table=fact_table,
                grain_columns=grain_columns,
            )
            is_valid = duplicate_count == 0

            reason = (
                "Fact grain is deterministic."
                if is_valid
                else f"{duplicate_count} duplicated grain combination(s) found."
            )

            results.append(
                GranularityValidationResult(
                    model_id=candidate.model_id,
                    fact_table=fact_table,
                    grain_columns=grain_columns,
                    duplicate_count=duplicate_count,
                    is_valid=is_valid,
                    reason=reason,
                )
            )

        return results

    @staticmethod
    def build_fact_grain(
        candidate: DecisionModelCandidate,
        fact_table: str,
    ) -> tuple[str, ...]:
        grain_columns = []

        for edge in candidate.edges:
            if edge.source_table != fact_table:
                continue

            if edge.target_table not in candidate.dimension_tables:
                continue

            for column in edge.source_columns:
                if column not in grain_columns:
                    grain_columns.append(column)

        return tuple(grain_columns)

    def count_duplicate_grain_rows(
        self,
        fact_table: str,
        grain_columns: tuple[str, ...],
    ) -> int:
        sql = self.build_duplicate_grain_sql(fact_table, grain_columns)
        row = self.db.query(sql).result_rows[0]
        return int(row[0])

    def build_duplicate_grain_sql(
        self,
        fact_table: str,
        grain_columns: tuple[str, ...],
    ) -> str:
        if not grain_columns:
            raise ValueError("Granularity validation requires at least one grain column.")

        selected_columns = ", ".join(q_ident(column) for column in grain_columns)
        not_null_condition = " AND ".join(
            f"{q_ident(column)} IS NOT NULL"
            for column in grain_columns
        )

        return f"""
        SELECT count()
        FROM (
            SELECT {selected_columns}
            FROM {q_ident(self.database)}.{q_ident(fact_table)}
            WHERE {not_null_condition}
            GROUP BY {selected_columns}
            HAVING count() > 1
        )
        """

    def store_results(self, results: list[GranularityValidationResult]) -> None:
        clear_metadata_table(self.db, "granularity_validations")

        if not results:
            return

        rows = [
            [
                CH_DB,
                result.model_id,
                result.fact_table,
                ", ".join(result.grain_columns),
                result.duplicate_count,
                result.is_valid,
                result.reason,
            ]
            for result in results
        ]

        self.db.insert(
            f"{q_ident(META_DB)}.granularity_validations",
            rows,
            column_names=[
                "database_name",
                "model_id",
                "fact_table",
                "grain_columns",
                "duplicate_count",
                "is_valid",
                "reason",
            ],
        )

    @staticmethod
    def print_results(results: list[GranularityValidationResult]) -> None:
        if not results:
            logger.info("No granularity validation results found.")
            return

        for result in results:
            status = "VALID" if result.is_valid else "INVALID"
            logger.info(
                "%s | model=%s | fact=%s | grain=%s | duplicates=%s | %s",
                status,
                result.model_id,
                result.fact_table,
                ", ".join(result.grain_columns),
                result.duplicate_count,
                result.reason,
            )
