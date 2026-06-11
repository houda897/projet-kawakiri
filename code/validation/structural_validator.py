from __future__ import annotations

from core.clickhouse_manager import CH_DB, META_DB, clickhouse_manager
from core.logger import get_logger
from core.meta import clear_metadata_table
from modeling.candidate_builder import DecisionModelCandidateBuilder
from modeling.decision_model import DecisionModelCandidate

from validation.referential_integrity import ReferentialIntegrityValidator
from validation.structural_report import (
    StructuralValidationIssue,
    StructuralValidationResult,
)
from validation.topology import TopologyValidator

logger = get_logger(__name__)


class StructuralValidator:
    """
    Validate stored decision-model candidates against structural rules.
    """

    def __init__(self, db: clickhouse_manager):
        self.db = db
        self.candidate_builder = DecisionModelCandidateBuilder(db)
        self.topology_validator = TopologyValidator()
        self.integrity_validator = ReferentialIntegrityValidator(db)

    def validate_stored_candidates(self) -> list[StructuralValidationResult]:
        candidates = self.candidate_builder.load_candidates()

        if not candidates:
            raise ValueError(
                "No decision model candidates found. Run build-model-candidates first."
            )

        return [self.validate_candidate(candidate) for candidate in candidates]

    def validate_candidate(
        self,
        candidate: DecisionModelCandidate,
    ) -> StructuralValidationResult:
        issues = []
        issues.extend(self.topology_validator.validate(candidate))
        issues.extend(self.integrity_validator.validate(candidate))

        return self.to_result(candidate, issues)

    def store_results(self, results: list[StructuralValidationResult]) -> None:
        clear_metadata_table(self.db, "decision_model_validation_issues")
        clear_metadata_table(self.db, "decision_model_validations")

        if not results:
            return

        validation_rows = [
            [
                CH_DB,
                result.model_id,
                result.is_valid,
                result.issue_count,
                result.orphan_count,
            ]
            for result in results
        ]
        issue_rows = [
            [
                CH_DB,
                issue.model_id,
                issue.rule_name,
                issue.severity,
                issue.message,
                issue.source_table,
                issue.target_table,
                issue.orphan_count,
            ]
            for result in results
            for issue in result.issues
        ]

        self.db.insert(
            f"{META_DB}.decision_model_validations",
            validation_rows,
            column_names=[
                "database_name",
                "model_id",
                "is_valid",
                "issue_count",
                "orphan_count",
            ],
        )

        if issue_rows:
            self.db.insert(
                f"{META_DB}.decision_model_validation_issues",
                issue_rows,
                column_names=[
                    "database_name",
                    "model_id",
                    "rule_name",
                    "severity",
                    "message",
                    "source_table",
                    "target_table",
                    "orphan_count",
                ],
            )

    @staticmethod
    def to_result(
        candidate: DecisionModelCandidate,
        issues: list[StructuralValidationIssue],
    ) -> StructuralValidationResult:
        orphan_count = sum(issue.orphan_count for issue in issues)

        return StructuralValidationResult(
            model_id=candidate.model_id,
            is_valid=not issues,
            issue_count=len(issues),
            orphan_count=orphan_count,
            issues=tuple(issues),
        )

    @staticmethod
    def print_results(results: list[StructuralValidationResult]) -> None:
        if not results:
            logger.info("No structural validation results found.")
            return

        for result in results:
            status = "VALID" if result.is_valid else "INVALID"
            logger.info(
                "%s | model=%s | issues=%s | orphans=%s",
                status,
                result.model_id,
                result.issue_count,
                result.orphan_count,
            )

            for issue in result.issues:
                logger.info(
                    "  - %s | %s | %s",
                    issue.rule_name,
                    issue.severity,
                    issue.message,
                )
