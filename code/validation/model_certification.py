from __future__ import annotations

from dataclasses import dataclass

from core.clickhouse_manager import CH_DB, META_DB, ClickHouseManager
from core.logger import get_logger
from core.meta import clear_metadata_table
from core.schema import q_ident
from modeling.candidate_builder import DecisionModelCandidateBuilder
from modeling.decision_model import DecisionModelCandidate

logger = get_logger(__name__)


@dataclass(frozen=True)
class CertificationIssue:
    rule_name: str
    severity: str
    message: str
    table_name: str = ""


@dataclass(frozen=True)
class ModelCertificationResult:
    model_id: str
    status: str
    is_certified: bool
    certification_score: float
    parsimony_score: float
    issue_count: int
    issues: tuple[CertificationIssue, ...]


class ModelCertificationEngine:
    """
    Combine ranking and validation results into a final model certification.
    """

    def __init__(self, db: ClickHouseManager):
        self.db = db
        self.candidate_builder = DecisionModelCandidateBuilder(db)

    def certify_stored_candidates(self) -> list[ModelCertificationResult]:
        candidates = self.candidate_builder.load_candidates()

        if not candidates:
            raise ValueError(
                "No decision model candidates found. Run build-model-candidates first."
            )

        parsimony_scores = self.load_parsimony_scores()
        structural_results = self.load_structural_results()
        granularity_results = self.load_granularity_results()
        homogeneity_results = self.load_homogeneity_results()
        stability_results = self.load_stability_results()

        return [
            self.certify_candidate(
                candidate=candidate,
                parsimony_scores=parsimony_scores,
                structural_results=structural_results,
                granularity_results=granularity_results,
                homogeneity_results=homogeneity_results,
                stability_results=stability_results,
            )
            for candidate in candidates
        ]

    def certify_candidate(
        self,
        candidate: DecisionModelCandidate,
        parsimony_scores: dict[str, float],
        structural_results: dict[str, dict],
        granularity_results: dict[str, list[dict]],
        homogeneity_results: dict[str, dict],
        stability_results: dict[str, list[dict]],
    ) -> ModelCertificationResult:
        issues: list[CertificationIssue] = []

        parsimony_score = parsimony_scores.get(candidate.model_id, 0.0)
        if candidate.model_id not in parsimony_scores:
            issues.append(
                CertificationIssue(
                    rule_name="PARSIMONY_RANKING",
                    severity="WARNING",
                    message="No parsimony score found. Run rank-models first.",
                )
            )

        structural = structural_results.get(candidate.model_id)
        if structural is None:
            issues.append(
                CertificationIssue(
                    rule_name="STRUCTURAL_VALIDATION",
                    severity="WARNING",
                    message="No structural validation result found. Run validate-structure first.",
                )
            )
        elif not structural["is_valid"]:
            issues.append(
                CertificationIssue(
                    rule_name="STRUCTURAL_VALIDATION",
                    severity="ERROR",
                    message=(
                        f"Structural validation failed with {structural['issue_count']} "
                        f"issue(s) and {structural['orphan_count']} orphan value(s)."
                    ),
                )
            )

        granularity_reports = granularity_results.get(candidate.model_id)
        if not granularity_reports:
            issues.append(
                CertificationIssue(
                    rule_name="DETERMINISTIC_GRANULARITY",
                    severity="WARNING",
                    message="No granularity validation result found. Run validate-granularity first.",
                )
            )
        else:
            for report in granularity_reports:
                if report["is_valid"]:
                    continue

                issues.append(
                    CertificationIssue(
                        rule_name="DETERMINISTIC_GRANULARITY",
                        severity="ERROR",
                        message=report["reason"],
                        table_name=report["fact_table"],
                    )
                )

        for table_name in candidate.fact_tables + candidate.dimension_tables:
            homogeneity = homogeneity_results.get(table_name)

            if homogeneity is None:
                issues.append(
                    CertificationIssue(
                        rule_name="SEMANTIC_HOMOGENEITY",
                        severity="WARNING",
                        message="No semantic homogeneity result found for this table.",
                        table_name=table_name,
                    )
                )
            elif not homogeneity["is_valid"]:
                issues.append(
                    CertificationIssue(
                        rule_name="SEMANTIC_HOMOGENEITY",
                        severity="ERROR",
                        message=homogeneity["reason"],
                        table_name=table_name,
                    )
                )

        stability_reports = stability_results.get(candidate.model_id)
        if not stability_reports:
            issues.append(
                CertificationIssue(
                    rule_name="AGGREGATION_STABILITY",
                    severity="WARNING",
                    message="No aggregation stability result found. Run the stability validator first.",
                )
            )
        else:
            for report in stability_reports:
                if report["is_stable"]:
                    continue

                issues.append(
                    CertificationIssue(
                        rule_name="AGGREGATION_STABILITY",
                        severity="ERROR",
                        message=(
                            f"{report['fact_table']} -> {report['dimension_table']} "
                            f"is unstable for measure {report['measure_column']}: {report['reason']}."
                        ),
                        table_name=report["fact_table"],
                    )
                )

        status = self.choose_status(issues)
        certification_score = self.calculate_certification_score(issues)

        return ModelCertificationResult(
            model_id=candidate.model_id,
            status=status,
            is_certified=status == "VALID",
            certification_score=certification_score,
            parsimony_score=parsimony_score,
            issue_count=len(issues),
            issues=tuple(issues),
        )

    def store_results(self, results: list[ModelCertificationResult]) -> None:
        clear_metadata_table(self.db, "model_certification_issues")
        clear_metadata_table(self.db, "model_certifications")

        if not results:
            return

        certification_rows = [
            [
                CH_DB,
                result.model_id,
                result.status,
                result.is_certified,
                result.certification_score,
                result.parsimony_score,
                result.issue_count,
            ]
            for result in results
        ]

        issue_rows = [
            [
                CH_DB,
                result.model_id,
                issue.rule_name,
                issue.severity,
                issue.message,
                issue.table_name,
            ]
            for result in results
            for issue in result.issues
        ]

        self.db.insert(
            f"{q_ident(META_DB)}.model_certifications",
            certification_rows,
            column_names=[
                "database_name",
                "model_id",
                "status",
                "is_certified",
                "certification_score",
                "parsimony_score",
                "issue_count",
            ],
        )

        if issue_rows:
            self.db.insert(
                f"{q_ident(META_DB)}.model_certification_issues",
                issue_rows,
                column_names=[
                    "database_name",
                    "model_id",
                    "rule_name",
                    "severity",
                    "message",
                    "table_name",
                ],
            )

    def load_parsimony_scores(self) -> dict[str, float]:
        sql = f"""
        SELECT model_id, parsimony_score
        FROM {q_ident(META_DB)}.decision_model_scores
        WHERE database_name = %(database)s
        """

        rows = self.db.query(sql, parameters={"database": CH_DB}).result_rows
        return {row[0]: float(row[1]) for row in rows}

    def load_structural_results(self) -> dict[str, dict]:
        sql = f"""
        SELECT model_id, is_valid, issue_count, orphan_count
        FROM {q_ident(META_DB)}.decision_model_validations
        WHERE database_name = %(database)s
        """

        rows = self.db.query(sql, parameters={"database": CH_DB}).result_rows
        return {
            row[0]: {
                "is_valid": bool(row[1]),
                "issue_count": int(row[2]),
                "orphan_count": int(row[3]),
            }
            for row in rows
        }

    def load_granularity_results(self) -> dict[str, list[dict]]:
        sql = f"""
        SELECT
            model_id,
            fact_table,
            grain_columns,
            duplicate_count,
            is_valid,
            reason
        FROM {q_ident(META_DB)}.granularity_validations
        WHERE database_name = %(database)s
        """

        rows = self.db.query(sql, parameters={"database": CH_DB}).result_rows
        results: dict[str, list[dict]] = {}

        for row in rows:
            results.setdefault(row[0], []).append(
                {
                    "fact_table": row[1],
                    "grain_columns": row[2],
                    "duplicate_count": int(row[3]),
                    "is_valid": bool(row[4]),
                    "reason": row[5],
                }
            )

        return results

    def load_homogeneity_results(self) -> dict[str, dict]:
        sql = f"""
        SELECT table_name, is_valid, homogeneity_score, issue_count, reason
        FROM {q_ident(META_DB)}.semantic_homogeneity
        WHERE database_name = %(database)s
        """

        rows = self.db.query(sql, parameters={"database": CH_DB}).result_rows
        return {
            row[0]: {
                "is_valid": bool(row[1]),
                "homogeneity_score": float(row[2]),
                "issue_count": int(row[3]),
                "reason": row[4],
            }
            for row in rows
        }

    def load_stability_results(self) -> dict[str, list[dict]]:
        sql = f"""
        SELECT
            model_id,
            fact_table,
            dimension_table,
            measure_column,
            is_stable,
            reason
        FROM {q_ident(META_DB)}.aggregation_stability
        WHERE database_name = %(database)s
        """

        rows = self.db.query(sql, parameters={"database": CH_DB}).result_rows
        results: dict[str, list[dict]] = {}

        for row in rows:
            results.setdefault(row[0], []).append(
                {
                    "fact_table": row[1],
                    "dimension_table": row[2],
                    "measure_column": row[3],
                    "is_stable": bool(row[4]),
                    "reason": row[5],
                }
            )

        return results

    @staticmethod
    def choose_status(issues: list[CertificationIssue]) -> str:
        if any(issue.severity == "ERROR" for issue in issues):
            return "INVALID"

        if any(issue.severity == "WARNING" for issue in issues):
            return "WARNING"

        return "VALID"

    @staticmethod
    def calculate_certification_score(issues: list[CertificationIssue]) -> float:
        score = 100.0

        for issue in issues:
            if issue.severity == "ERROR":
                score -= 35.0
            elif issue.severity == "WARNING":
                score -= 10.0

        return max(0.0, round(score, 2))

    @staticmethod
    def print_results(results: list[ModelCertificationResult]) -> None:
        if not results:
            logger.info("No model certification result found.")
            return

        for result in results:
            logger.info(
                "%s | model=%s | score=%s | issues=%s | parsimony=%s",
                result.status,
                result.model_id,
                result.certification_score,
                result.issue_count,
                result.parsimony_score,
            )

            for issue in result.issues:
                logger.info(
                    "  - %s | %s | %s",
                    issue.rule_name,
                    issue.severity,
                    issue.message,
                )
