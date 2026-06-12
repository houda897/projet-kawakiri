from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from core.clickhouse_manager import CH_DB, META_DB, ClickHouseManager
from core.schema import q_ident

EXPECTED_RULES = (
    "PARSIMONY_RANKING",
    "STRUCTURAL_VALIDATION",
    "DETERMINISTIC_GRANULARITY",
    "SEMANTIC_HOMOGENEITY",
    "AGGREGATION_STABILITY",
)


class CertificationReportExporter:
    """
    Export stored model certification results as a final JSON report.
    """

    def __init__(self, db: ClickHouseManager):
        self.db = db

    def build_report(self) -> dict:
        certifications = self.load_certifications()

        if not certifications:
            raise ValueError("No model certification result found. Run certify-models first.")

        issues_by_model = self.load_issues()
        models = [
            self.build_model_report(certification, issues_by_model)
            for certification in certifications
        ]
        best_model = self.select_best_model(models)

        return {
            "database_name": CH_DB,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "best_model": best_model,
            "models": models,
        }

    def build_model_report(
        self,
        certification: dict,
        issues_by_model: dict[str, list[dict]],
    ) -> dict:
        issues = issues_by_model.get(certification["model_id"], [])
        issue_rules = {issue["rule_name"] for issue in issues}
        failed_rules = sorted(
            {issue["rule_name"] for issue in issues if issue["severity"] == "ERROR"}
        )
        missing_rules = sorted(
            {
                issue["rule_name"]
                for issue in issues
                if issue["severity"] == "WARNING" and issue["message"].lower().startswith("no ")
            }
        )
        warning_rules = sorted(
            {issue["rule_name"] for issue in issues if issue["severity"] == "WARNING"}
        )
        passed_rules = [rule for rule in EXPECTED_RULES if rule not in issue_rules]

        return {
            "model_id": certification["model_id"],
            "model_type": certification["model_type"],
            "status": certification["status"],
            "is_certified": certification["is_certified"],
            "certification_score": certification["certification_score"],
            "parsimony_score": certification["parsimony_score"],
            "fact_tables": certification["fact_tables"],
            "dimension_tables": certification["dimension_tables"],
            "passed_rules": passed_rules,
            "failed_rules": failed_rules,
            "missing_rules": missing_rules,
            "warning_rules": warning_rules,
            "issues": issues,
        }

    def load_certifications(self) -> list[dict]:
        sql = f"""
        SELECT
            c.model_id,
            m.model_type,
            c.status,
            c.is_certified,
            c.certification_score,
            c.parsimony_score,
            m.fact_tables,
            m.dimension_tables
        FROM {q_ident(META_DB)}.model_certifications AS c
        INNER JOIN {q_ident(META_DB)}.decision_model_candidates AS m
            ON c.database_name = m.database_name
           AND c.model_id = m.model_id
        WHERE c.database_name = %(database)s
        ORDER BY
            if(c.status = 'VALID', 0, if(c.status = 'WARNING', 1, 2)),
            c.certification_score DESC,
            c.parsimony_score DESC,
            c.model_id
        """

        rows = self.db.query(sql, parameters={"database": CH_DB}).result_rows

        return [
            {
                "model_id": row[0],
                "model_type": row[1],
                "status": row[2],
                "is_certified": bool(row[3]),
                "certification_score": float(row[4]),
                "parsimony_score": float(row[5]),
                "fact_tables": self.split_columns(row[6]),
                "dimension_tables": self.split_columns(row[7]),
            }
            for row in rows
        ]

    def load_issues(self) -> dict[str, list[dict]]:
        sql = f"""
        SELECT
            model_id,
            rule_name,
            severity,
            message,
            table_name
        FROM {q_ident(META_DB)}.model_certification_issues
        WHERE database_name = %(database)s
        ORDER BY model_id, severity, rule_name, table_name
        """

        rows = self.db.query(sql, parameters={"database": CH_DB}).result_rows
        issues: dict[str, list[dict]] = {}

        for row in rows:
            issues.setdefault(row[0], []).append(
                {
                    "rule_name": row[1],
                    "severity": row[2],
                    "message": row[3],
                    "table_name": row[4],
                }
            )

        return issues

    def write_json(self, path: str | Path) -> dict:
        report = self.build_report()
        output_path = Path(path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(
            json.dumps(report, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        return report

    @staticmethod
    def select_best_model(models: list[dict]) -> dict:
        return models[0]

    @staticmethod
    def split_columns(columns: str) -> list[str]:
        return [column.strip() for column in columns.split(",") if column.strip()]
