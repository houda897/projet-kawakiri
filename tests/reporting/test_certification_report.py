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
        SimpleNamespace(
            result_rows=[
                ("sales", "raw_sales", "sales_group", "sale_id", "FACT_CANDIDATE"),
                ("customers", "raw_customers", "customers_group", "customer_id", "DIMENSION_CANDIDATE"),
                ("products", "raw_products", "products_group", "product_id", "DIMENSION_CANDIDATE"),
                ("returns", "raw_returns", "returns_group", "return_id", "FACT_CANDIDATE"),
                ("audit_logical", "audit", "audit_group", "audit_id", "DIMENSION_CANDIDATE"),
            ]
        ),
        SimpleNamespace(
            result_rows=[
                ("raw_sales", "sale_id"),
                ("raw_sales", "amount"),
                ("raw_customers", "customer_id"),
                ("raw_customers", "customer_name"),
            ]
        ),
        SimpleNamespace(
            result_rows=[
                ("raw_sales", "sale_id", "Int64"),
                ("raw_sales", "amount", "Float64"),
                ("raw_customers", "customer_id", "Int64"),
                ("raw_customers", "customer_name", "String"),
                ("raw_customers", "country", "String"),
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
    assert report["coverage"]["certified_model_tables"] == ["customers", "products", "sales"]
    assert [
        table["logical_table_name"]
        for table in report["coverage"]["logical_tables_outside_model"]
    ] == ["returns", "audit_logical"]
    assert report["coverage"]["uncovered_columns"] == [
        {
            "source_table": "raw_customers",
            "column_name": "country",
            "column_type": "String",
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
        columns_by_table={
            "sales": [
                {"column_name": "sale_id", "column_type": "Int64"},
                {"column_name": "customer_id", "column_type": "Int64"},
                {"column_name": "amount", "column_type": "Float64"},
            ],
            "customers": [
                {"column_name": "customer_id", "column_type": "Int64"},
                {"column_name": "customer_name", "column_type": "String"},
            ],
            "geography": [
                {"column_name": "country", "column_type": "String"},
            ],
            "returns": [
                {"column_name": "return_id", "column_type": "Int64"},
            ],
        },
        coverage={
            "logical_tables_outside_model": [
                {
                    "logical_table_name": "returns",
                    "logical_table_role": "FACT_CANDIDATE",
                }
            ],
            "uncovered_columns": [
                {
                    "source_table": "raw_customers",
                    "column_name": "country",
                    "column_type": "String",
                }
            ],
        },
    )

    assert schema.startswith("erDiagram")
    assert "%% Model: star_sales" in schema
    assert "FACT_TABLE {" in schema
    assert "%% FACT_TABLE: FACT source=sales" in schema
    assert "Float64 amount" in schema
    assert "DIMENSION_TABLE_1 {" in schema
    assert "%% DIMENSION_TABLE_1: DIMENSION source=customers" in schema
    assert "Int64 customer_id PK" in schema
    assert 'DIMENSION_TABLE_1 ||--o{ FACT_TABLE : "customer_id = customer_id; ratio=1"' in schema
    assert "%% AGGREGATION_STABILITY [WARNING] model" in schema
    assert "%% Other logical tables outside certified model" in schema
    assert "OTHER_LOGICAL_TABLE_1 {" in schema
    assert "EXCLUDED_TABLE_1 {" in schema
    assert "%% Uncovered source columns" in schema
    assert "%% raw_customers.country (String)" in schema
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
        SimpleNamespace(
            result_rows=[
                ("sales", "amount", "Float64"),
                ("sales", "customer_id", "Int64"),
                ("customers", "customer_id", "Int64"),
                ("customers", "customer_name", "String"),
                ("returns", "return_id", "Int64"),
                ("audit_logical", "audit_id", "Int64"),
                ("geography", "country", "String"),
            ]
        ),
    ]
    exporter = CertificationReportExporter(db)
    report = exporter.build_report()
    output_path = tmp_path / "model.mmd"

    schema = exporter.write_mermaid_schema(output_path, report)

    assert output_path.read_text(encoding="utf-8") == schema
    assert schema.startswith("erDiagram")
    assert "DIMENSION_TABLE_1 ||--o{ FACT_TABLE" in schema
    assert "Float64 amount" in schema
