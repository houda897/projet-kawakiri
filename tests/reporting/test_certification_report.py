import json
from types import SimpleNamespace
from unittest.mock import MagicMock

from reporting.certification_report import CertificationReportExporter


def make_db() -> MagicMock:
    db = MagicMock()
    db.query.side_effect = [
        SimpleNamespace(
            result_rows=[
                (
                    "star_sales",
                    "STAR",
                    "WARNING",
                    False,
                    90.0,
                    42.0,
                    "sales",
                    "customers,products",
                ),
                (
                    "star_returns",
                    "STAR",
                    "INVALID",
                    False,
                    55.0,
                    31.0,
                    "returns",
                    "products",
                ),
            ]
        ),
        SimpleNamespace(
            result_rows=[
                (
                    "star_sales",
                    "AGGREGATION_STABILITY",
                    "WARNING",
                    "No aggregation stability result found.",
                    "",
                ),
                (
                    "star_returns",
                    "DETERMINISTIC_GRANULARITY",
                    "ERROR",
                    "3 duplicated grain combination(s) found.",
                    "returns",
                ),
            ]
        ),
        SimpleNamespace(
            result_rows=[
                (
                    "geography",
                    "ISOLATED",
                    0.9,
                    "table_has_no_confirmed_relationships",
                ),
            ]
        ),
    ]
    return db


def test_build_report_returns_best_model_and_rule_summary() -> None:
    exporter = CertificationReportExporter(make_db())

    report = exporter.build_report()

    assert report["best_model"]["model_id"] == "star_sales"
    assert report["best_model"]["status"] == "WARNING"
    assert report["best_model"]["missing_rules"] == ["AGGREGATION_STABILITY"]
    assert "STRUCTURAL_VALIDATION" in report["best_model"]["passed_rules"]
    assert len(report["models"]) == 2
    assert report["models"][1]["failed_rules"] == ["DETERMINISTIC_GRANULARITY"]
    assert report["excluded_tables"] == [
        {
            "table_name": "geography",
            "role": "ISOLATED",
            "confidence": 0.9,
            "reason": "table_has_no_confirmed_relationships",
        }
    ]


def test_build_report_requires_certification_results() -> None:
    db = MagicMock()
    db.query.return_value = SimpleNamespace(result_rows=[])
    exporter = CertificationReportExporter(db)

    try:
        exporter.build_report()
    except ValueError as exc:
        assert "Run certify-models" in str(exc)
    else:
        raise AssertionError("Expected ValueError when certification results are missing")


def test_write_json_writes_report_file(tmp_path) -> None:
    exporter = CertificationReportExporter(make_db())
    output_path = tmp_path / "certification_report.json"

    report = exporter.write_json(output_path)

    saved_report = json.loads(output_path.read_text(encoding="utf-8"))
    assert saved_report["best_model"]["model_id"] == report["best_model"]["model_id"]
    assert saved_report["database_name"] == report["database_name"]


def test_format_model_schema_renders_mermaid_diagram() -> None:
    model = {
        "model_id": "star_sales",
        "model_type": "STAR",
        "status": "WARNING",
        "certification_score": 90.0,
        "fact_tables": ["sales"],
        "dimension_tables": ["customers"],
        "issues": [
            {
                "rule_name": "AGGREGATION_STABILITY",
                "severity": "WARNING",
                "table_name": "",
                "message": "No aggregation stability result found.",
            }
        ],
    }
    edges = [
        {
            "source_table": "sales",
            "target_table": "customers",
            "source_columns": "customer_id",
            "target_columns": "customer_id",
            "join_success_ratio": 1.0,
            "depth": 1,
        }
    ]
    excluded_tables = [
        {
            "table_name": "geography",
            "role": "ISOLATED",
            "confidence": 0.9,
            "reason": "table_has_no_confirmed_relationships",
        }
    ]

    schema = CertificationReportExporter.format_model_schema(
        model,
        edges,
        excluded_tables,
    )

    assert schema.startswith("flowchart LR")
    assert "%% Model: star_sales" in schema
    assert "subgraph Facts" in schema
    assert 'sales["sales<br/>FACT"]:::fact' in schema
    assert "subgraph Dimensions" in schema
    assert 'customers["customers<br/>DIMENSION"]:::dimension' in schema
    assert 'sales -->|"customer_id = customer_id<br/>ratio=1"| customers' in schema
    assert "%% AGGREGATION_STABILITY [WARNING] model" in schema
    assert 'geography["geography<br/>ISOLATED"]:::excluded' in schema
    assert "```" not in schema


def test_write_mermaid_schema_writes_mmd_file(tmp_path) -> None:
    db = make_db()
    db.query.side_effect = [
        *db.query.side_effect,
        SimpleNamespace(
            result_rows=[
                ("sales", "customers", "customer_id", "customer_id", 1.0, 1),
            ]
        ),
    ]
    exporter = CertificationReportExporter(db)
    report = exporter.build_report()
    output_path = tmp_path / "model.mmd"

    schema = exporter.write_mermaid_schema(output_path, report)

    assert output_path.read_text(encoding="utf-8") == schema
    assert schema.startswith("flowchart LR")
    assert "sales -->" in schema
