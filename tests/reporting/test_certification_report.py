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
