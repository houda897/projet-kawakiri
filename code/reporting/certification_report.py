from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path

from core.clickhouse_manager import CH_DB, META_DB, ClickHouseManager
from core.logger import get_logger
from core.schema import q_ident

logger = get_logger(__name__)

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
        excluded_tables = self.load_excluded_tables()
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
            "excluded_tables": excluded_tables,
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

    def load_excluded_tables(self) -> list[dict]:
        """
        Return tables deliberately kept outside inferred decision models.
        """
        sql = f"""
        SELECT
            table_name,
            role,
            confidence,
            reason
        FROM {q_ident(META_DB)}.table_roles
        WHERE database_name = %(database)s
          AND role = 'ISOLATED'
        ORDER BY table_name
        """

        rows = self.db.query(sql, parameters={"database": CH_DB}).result_rows

        return [
            {
                "table_name": row[0],
                "role": row[1],
                "confidence": float(row[2]),
                "reason": row[3],
            }
            for row in rows
        ]

    def load_model_edges(self, model_id: str) -> list[dict]:
        """
        Return the joins that compose a stored decision model.
        """
        sql = f"""
        SELECT
            source_table,
            target_table,
            source_columns,
            target_columns,
            join_success_ratio,
            depth
        FROM {q_ident(META_DB)}.decision_model_edges
        WHERE database_name = %(database)s
          AND model_id = %(model_id)s
        ORDER BY depth, source_table, target_table
        """

        rows = self.db.query(
            sql,
            parameters={"database": CH_DB, "model_id": model_id},
        ).result_rows

        return [
            {
                "source_table": row[0],
                "target_table": row[1],
                "source_columns": row[2],
                "target_columns": row[3],
                "join_success_ratio": float(row[4]),
                "depth": int(row[5]),
            }
            for row in rows
        ]

    def build_best_model_schema(self, report: dict | None = None) -> str:
        """
        Build a readable schema for the selected model in the certification report.
        """
        if report is None:
            report = self.build_report()

        best_model = report["best_model"]
        edges = self.load_model_edges(best_model["model_id"])
        return self.format_model_schema(
            model=best_model,
            edges=edges,
            excluded_tables=report.get("excluded_tables", []),
        )

    def print_best_model_schema(self, report: dict | None = None) -> str:
        """
        Print the selected model as a Mermaid diagram and return that text.
        """
        schema = self.build_best_model_schema(report)
        logger.info("=== inferred model schema (Mermaid) ===\n%s", schema)
        return schema

    def write_mermaid_schema(
        self,
        path: str | Path,
        report: dict | None = None,
    ) -> str:
        """
        Write the selected model schema as a Mermaid file and return its content.
        """
        schema = self.build_best_model_schema(report)
        output_path = Path(path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(schema, encoding="utf-8")
        logger.info("Mermaid model schema exported: %s", output_path)
        return schema

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

    @staticmethod
    def format_model_schema(
        model: dict,
        edges: list[dict],
        excluded_tables: list[dict],
    ) -> str:
        table_names = (
            model.get("fact_tables", [])
            + model.get("dimension_tables", [])
            + [table["table_name"] for table in excluded_tables]
        )
        node_ids = {
            table_name: CertificationReportExporter.mermaid_node_id(table_name)
            for table_name in table_names
        }

        lines = [
            "flowchart LR",
            f"  %% Model: {model['model_id']}",
            f"  %% Type: {model['model_type']}",
            f"  %% Status: {model['status']} | score={model['certification_score']}",
            "  classDef fact fill:#dbeafe,stroke:#1d4ed8,stroke-width:2px,color:#111827",
            "  classDef dimension fill:#dcfce7,stroke:#15803d,stroke-width:2px,color:#111827",
            "  classDef excluded fill:#f3f4f6,stroke:#6b7280,stroke-dasharray: 4 3,color:#374151",
        ]

        fact_tables = model.get("fact_tables", [])
        if fact_tables:
            lines.append("  subgraph Facts")
            for table in fact_tables:
                lines.append(
                    f"    {node_ids[table]}[\"{CertificationReportExporter.mermaid_label(table, 'FACT')}\"]:::fact"
                )
            lines.append("  end")

        dimension_tables = model.get("dimension_tables", [])
        if dimension_tables:
            lines.append("  subgraph Dimensions")
            for table in dimension_tables:
                lines.append(
                    f"    {node_ids[table]}[\"{CertificationReportExporter.mermaid_label(table, 'DIMENSION')}\"]:::dimension"
                )
            lines.append("  end")

        if excluded_tables:
            lines.append("  subgraph Excluded")
            for table in excluded_tables:
                table_name = table["table_name"]
                lines.append(
                    f"    {node_ids[table_name]}[\"{CertificationReportExporter.mermaid_label(table_name, table['role'])}\"]:::excluded"
                )
            lines.append("  end")

        for edge in edges:
            source = node_ids.get(
                edge["source_table"],
                CertificationReportExporter.mermaid_node_id(edge["source_table"]),
            )
            target = node_ids.get(
                edge["target_table"],
                CertificationReportExporter.mermaid_node_id(edge["target_table"]),
            )
            label = CertificationReportExporter.mermaid_edge_label(edge)
            lines.append(f"  {source} -->|\"{label}\"| {target}")

        issues = model.get("issues", [])
        if issues:
            lines.append("  %% Certification issues")
            for issue in issues:
                table_name = issue.get("table_name") or "model"
                lines.append(
                    f"  %% {issue['rule_name']} [{issue['severity']}] "
                    f"{table_name}: {issue['message']}"
                )

        return "\n".join(lines)

    @staticmethod
    def mermaid_node_id(table_name: str) -> str:
        node_id = re.sub(r"\W+", "_", table_name).strip("_")
        if not node_id or node_id[0].isdigit():
            node_id = f"table_{node_id}"
        return node_id

    @staticmethod
    def mermaid_label(table_name: str, table_role: str) -> str:
        escaped_name = table_name.replace('"', "'")
        escaped_role = table_role.replace('"', "'")
        return f"{escaped_name}<br/>{escaped_role}"

    @staticmethod
    def mermaid_edge_label(edge: dict) -> str:
        source_columns = str(edge["source_columns"]).replace('"', "'")
        target_columns = str(edge["target_columns"]).replace('"', "'")
        ratio = f"{edge['join_success_ratio']:.4g}"
        return f"{source_columns} = {target_columns}<br/>ratio={ratio}"
