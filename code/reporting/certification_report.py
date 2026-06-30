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
        coverage = self.build_coverage(best_model)

        return {
            "database_name": CH_DB,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "best_model": best_model,
            "models": models,
            "excluded_tables": excluded_tables,
            "coverage": coverage,
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

    def build_coverage(self, best_model: dict) -> dict:
        """
        Explain what is shown in the certified model and what remains outside it.
        """
        certified_tables = set(best_model["fact_tables"] + best_model["dimension_tables"])
        logical_tables = self.load_logical_tables()
        logical_tables_outside_model = [
            table
            for table in logical_tables
            if table["logical_table_name"] not in certified_tables
        ]

        covered_columns = self.load_covered_source_columns()
        uncovered_columns = [
            column
            for column in self.load_source_columns()
            if (column["source_table"], column["column_name"]) not in covered_columns
        ]

        return {
            "certified_model_tables": sorted(certified_tables),
            "logical_tables": logical_tables,
            "logical_tables_outside_model": logical_tables_outside_model,
            "uncovered_columns": uncovered_columns,
        }

    def load_logical_tables(self) -> list[dict]:
        sql = f"""
        SELECT
            logical_table_name,
            source_table,
            group_name,
            determinant_columns,
            logical_table_role
        FROM {q_ident(META_DB)}.logical_tables
        WHERE database_name = %(database)s
        ORDER BY logical_table_name
        """

        rows = self.db.query(sql, parameters={"database": CH_DB}).result_rows
        return [
            {
                "logical_table_name": row[0],
                "source_table": row[1],
                "group_name": row[2],
                "determinant_columns": self.split_columns(row[3]),
                "logical_table_role": row[4],
            }
            for row in rows
        ]

    def load_covered_source_columns(self) -> set[tuple[str, str]]:
        sql = f"""
        SELECT DISTINCT
            source_table,
            column_name
        FROM {q_ident(META_DB)}.logical_table_columns
        WHERE database_name = %(database)s
        ORDER BY source_table, column_name
        """

        rows = self.db.query(sql, parameters={"database": CH_DB}).result_rows
        return {(row[0], row[1]) for row in rows}

    def load_source_columns(self) -> list[dict]:
        sql = f"""
        SELECT
            table_name,
            column_name,
            column_type
        FROM {q_ident(META_DB)}.column_profiles
        WHERE database_name = %(database)s
          AND NOT startsWith(table_name, 'logical_')
          AND NOT startsWith(column_name, '__')
        ORDER BY table_name, column_name
        """

        rows = self.db.query(sql, parameters={"database": CH_DB}).result_rows
        return [
            {
                "source_table": row[0],
                "column_name": row[1],
                "column_type": row[2],
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

    def load_model_columns(self, table_names: list[str]) -> dict[str, list[dict]]:
        """
        Return profiled columns for the tables shown in the diagram.
        """
        if not table_names:
            return {}

        sql = f"""
        SELECT
            table_name,
            column_name,
            column_type
        FROM {q_ident(META_DB)}.column_profiles
        WHERE database_name = %(database)s
          AND table_name IN %(table_names)s
          AND NOT startsWith(column_name, '__')
        ORDER BY table_name, column_name
        """

        rows = self.db.query(
            sql,
            parameters={"database": CH_DB, "table_names": tuple(table_names)},
        ).result_rows
        columns_by_table: dict[str, list[dict]] = {table_name: [] for table_name in table_names}

        for row in rows:
            columns_by_table.setdefault(row[0], []).append(
                {
                    "column_name": row[1],
                    "column_type": row[2],
                }
            )

        return columns_by_table

    def build_best_model_schema(self, report: dict | None = None) -> str:
        """
        Build a readable schema for the selected model in the certification report.
        """
        if report is None:
            report = self.build_report()

        best_model = report["best_model"]
        edges = self.load_model_edges(best_model["model_id"])
        coverage = report.get("coverage", {})
        outside_table_names = [
            table["logical_table_name"]
            for table in coverage.get("logical_tables_outside_model", [])
        ]
        table_names = (
            best_model["fact_tables"]
            + best_model["dimension_tables"]
            + outside_table_names
            + [table["table_name"] for table in report.get("excluded_tables", [])]
        )
        columns_by_table = self.load_model_columns(table_names)
        return self.format_model_schema(
            model=best_model,
            edges=edges,
            excluded_tables=report.get("excluded_tables", []),
            columns_by_table=columns_by_table,
            coverage=coverage,
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
        columns_by_table: dict[str, list[dict]] | None = None,
        coverage: dict | None = None,
    ) -> str:
        columns_by_table = columns_by_table or {}
        coverage = coverage or {}

        lines = [
            "erDiagram",
            f"  %% Model: {model['model_id']}",
            f"  %% Type: {model['model_type']}",
            f"  %% Status: {model['status']} | score={model['certification_score']}",
        ]

        fact_tables = model.get("fact_tables", [])
        dimension_tables = model.get("dimension_tables", [])
        outside_logical_tables = coverage.get("logical_tables_outside_model", [])
        table_aliases = CertificationReportExporter.build_mermaid_table_aliases(
            fact_tables,
            dimension_tables,
            excluded_tables,
            outside_logical_tables,
        )
        table_roles = {
            **{table: "FACT" for table in fact_tables},
            **{table: "DIMENSION" for table in dimension_tables},
            **{table["table_name"]: table["role"] for table in excluded_tables},
            **{
                table["logical_table_name"]: table["logical_table_role"]
                for table in outside_logical_tables
            },
        }

        lines.append("  %% Certified model tables")
        for table in fact_tables + dimension_tables:
            lines.extend(
                CertificationReportExporter.format_er_table(
                    table,
                    table_aliases[table],
                    table_roles[table],
                    columns_by_table.get(table, []),
                    edges,
                )
            )

        if outside_logical_tables:
            lines.append("  %% Other logical tables outside certified model")
            for logical_table in outside_logical_tables:
                table_name = logical_table["logical_table_name"]
                lines.extend(
                    CertificationReportExporter.format_er_table(
                        table_name,
                        table_aliases[table_name],
                        table_roles[table_name],
                        columns_by_table.get(table_name, []),
                        edges,
                    )
                )

        if excluded_tables:
            lines.append("  %% Excluded isolated tables")
            for table in excluded_tables:
                table_name = table["table_name"]
                lines.extend(
                    CertificationReportExporter.format_er_table(
                        table_name,
                        table_aliases[table_name],
                        table_roles[table_name],
                        columns_by_table.get(table_name, []),
                        edges,
                    )
                )

        for edge in edges:
            lines.append(CertificationReportExporter.format_er_relation(edge, table_aliases))

        uncovered_columns = coverage.get("uncovered_columns", [])
        if uncovered_columns:
            lines.append("  %% Uncovered source columns")
            for column in uncovered_columns:
                lines.append(
                    "  %% "
                    f"{column['source_table']}.{column['column_name']} "
                    f"({column['column_type']})"
                )

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
    def format_er_table(
        table_name: str,
        table_alias: str,
        table_role: str,
        columns: list[dict],
        edges: list[dict],
    ) -> list[str]:
        lines = [f"  {table_alias} {{"]

        if not columns:
            lines.append(f"    string {table_role}")
        else:
            for column in columns:
                column_name = column["column_name"]
                markers = CertificationReportExporter.column_markers(
                    table_name,
                    column_name,
                    edges,
                )
                marker_text = f" {markers}" if markers else ""
                lines.append(
                    "    "
                    f"{CertificationReportExporter.mermaid_type(column['column_type'])} "
                    f"{CertificationReportExporter.mermaid_column_name(column_name)}"
                    f"{marker_text}"
                )

        lines.append("  }")
        lines.append(f"  %% {table_alias}: {table_role} source={table_name}")
        return lines

    @staticmethod
    def format_er_relation(edge: dict, table_aliases: dict[str, str]) -> str:
        parent = table_aliases.get(
            edge["target_table"],
            CertificationReportExporter.mermaid_node_id(edge["target_table"]),
        )
        child = table_aliases.get(
            edge["source_table"],
            CertificationReportExporter.mermaid_node_id(edge["source_table"]),
        )
        source_columns = str(edge["source_columns"]).replace('"', "'")
        target_columns = str(edge["target_columns"]).replace('"', "'")
        ratio = f"{edge['join_success_ratio']:.4g}"
        label = f"{source_columns} = {target_columns}; ratio={ratio}"
        return f"  {parent} ||--o{{ {child} : \"{label}\""

    @staticmethod
    def build_mermaid_table_aliases(
        fact_tables: list[str],
        dimension_tables: list[str],
        excluded_tables: list[dict],
        outside_logical_tables: list[dict] | None = None,
    ) -> dict[str, str]:
        outside_logical_tables = outside_logical_tables or []
        aliases = {}

        for index, table_name in enumerate(fact_tables, start=1):
            aliases[table_name] = (
                "FACT_TABLE" if len(fact_tables) == 1 else f"FACT_TABLE_{index}"
            )

        for index, table_name in enumerate(dimension_tables, start=1):
            aliases[table_name] = f"DIMENSION_TABLE_{index}"

        for index, table in enumerate(excluded_tables, start=1):
            aliases[table["table_name"]] = f"EXCLUDED_TABLE_{index}"

        for index, table in enumerate(outside_logical_tables, start=1):
            aliases[table["logical_table_name"]] = f"OTHER_LOGICAL_TABLE_{index}"

        return aliases

    @staticmethod
    def column_markers(
        table_name: str,
        column_name: str,
        edges: list[dict],
    ) -> str:
        markers = []
        for edge in edges:
            if table_name == edge["target_table"] and column_name in CertificationReportExporter.split_columns(
                str(edge["target_columns"])
            ):
                markers.append("PK")
            if table_name == edge["source_table"] and column_name in CertificationReportExporter.split_columns(
                str(edge["source_columns"])
            ):
                markers.append("FK")
        return ",".join(dict.fromkeys(markers))

    @staticmethod
    def mermaid_type(column_type: str) -> str:
        normalized = re.sub(r"[^0-9A-Za-z_]+", "_", column_type).strip("_")
        return normalized or "string"

    @staticmethod
    def mermaid_column_name(column_name: str) -> str:
        normalized = re.sub(r"[^0-9A-Za-z_]+", "_", column_name).strip("_")
        if not normalized or normalized[0].isdigit():
            normalized = f"column_{normalized}"
        return normalized
