from __future__ import annotations

import csv
from datetime import date, datetime
from pathlib import Path

import pytest
from unittest.mock import MagicMock

from config.scoring import INGESTION_SETTINGS
from ingestion.csv_loader import (
    CsvIngestionEngine,
    DetectedColumn,
    IngestionResult,
    SampleCheck,
)


@pytest.fixture
def engine() -> CsvIngestionEngine:
    return CsvIngestionEngine(db=MagicMock())



def test_detect_delimiter_uses_sniffer(engine: CsvIngestionEngine, tmp_path: Path) -> None:
    path = tmp_path / "sample.csv"
    path.write_text("id;name;score\n1;Alice;10\n2;Bob;20\n", encoding="utf-8")

    assert engine.detect_delimiter(path) == ";"


def test_detect_delimiter_falls_back_to_most_frequent_delimiter(
    engine: CsvIngestionEngine,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "sample.csv"
    path.write_text("id\tname\tscore\n1\tAlice\t10\n2\tBob\t20\n", encoding="utf-8")

    def raise_sniff(*args, **kwargs):
        raise csv.Error("cannot sniff")

    monkeypatch.setattr(csv.Sniffer, "sniff", raise_sniff)

    assert engine.detect_delimiter(path) == "\t"


def test_detect_delimiter_fallback_prefers_stable_columns(
    engine: CsvIngestionEngine,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "sample.csv"
    path.write_text(
        "id;comment;score\n"
        "1;hello, with comma;10\n"
        "2;another, comma;20\n",
        encoding="utf-8",
    )

    def raise_sniff(*args, **kwargs):
        raise csv.Error("cannot sniff")

    monkeypatch.setattr(csv.Sniffer, "sniff", raise_sniff)

    assert engine.detect_delimiter(path) == ";"


def test_check_malformed_row_rejects_extra_columns(
    engine: CsvIngestionEngine,
    tmp_path: Path,
) -> None:
    path = tmp_path / "bad.csv"
    row = {"id": "1", "amount": "12", None: ["5"]}

    with pytest.raises(ValueError, match="extra columns detected"):
        engine.check_malformed_row(row, path, 2, ",")


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("  Hello, World!  ", "Hello_World"),
        ("123abc", "col_123abc"),
        ("__a---b__", "a_b"),
        (None, "column"),
    ],
)
def test_clean_identifier(engine: CsvIngestionEngine, raw: str | None, expected: str) -> None:
    assert engine.clean_identifier(raw) == expected


def test_dedupe_names_appends_stable_suffixes(engine: CsvIngestionEngine) -> None:
    assert engine.dedupe_names(["a", "a", "b", "a", "b"]) == [
        "a",
        "a_2",
        "b",
        "a_3",
        "b_2",
    ]


@pytest.mark.parametrize(
    "raw, expected",
    [
        (None, None),
        ("   ", None),
        (" null ", None),
        ("value", "value"),
        ("  spaced value  ", "spaced value"),
    ],
)
def test_clean_value(engine: CsvIngestionEngine, raw: str | None, expected: str | None) -> None:
    assert engine.clean_value(raw) == expected


@pytest.mark.parametrize(
    "value, expected",
    [
        ("12", True),
        ("-3", True),
        ("12.0", False),
        ("1,5", False),
        ("abc", False),
    ],
)
def test_is_int(engine: CsvIngestionEngine, value: str, expected: bool) -> None:
    assert engine.is_int(value) is expected


@pytest.mark.parametrize(
    "value, expected",
    [
        ("12", True),
        ("1.25", True),
        ("1,25", True),
        ("abc", False),
    ],
)
def test_is_float(engine: CsvIngestionEngine, value: str, expected: bool) -> None:
    assert engine.is_float(value) is expected


@pytest.mark.parametrize(
    "value, expected",
    [
        ("2024-01-31", True),
        ("31/01/2024", True),
        ("01/31/2024", True),
        ("2024/01/31", False),
    ],
)
def test_is_date(engine: CsvIngestionEngine, value: str, expected: bool) -> None:
    assert engine.is_date(value) is expected


@pytest.mark.parametrize(
    "value, expected",
    [
        ("2024-01-31 10:20:30", True),
        ("2024-01-31T10:20:30", True),
        ("31/01/2024 10:20:30", True),
        ("2024-01-31", False),
    ],
)
def test_is_datetime(engine: CsvIngestionEngine, value: str, expected: bool) -> None:
    assert engine.is_datetime(value) is expected


def test_infer_column_types_marks_nullable_columns(engine: CsvIngestionEngine) -> None:
    headers = ["id", "amount", "created_at", "label"]
    rows = [
        {"id": "1", "amount": "1,25", "created_at": "2024-01-01 10:00:00", "label": "alpha"},
        {"id": "2", "amount": "2.5", "created_at": "2024-01-02 11:00:00", "label": ""},
        {"id": "3", "amount": "3.0", "created_at": "2024-01-03 12:00:00", "label": None},
    ]

    inferred = engine.infer_column_types(headers, rows)

    assert inferred == [
        DetectedColumn(name="id", detected_type="Int64", nullable=False),
        DetectedColumn(name="amount", detected_type="Float64", nullable=False),
        DetectedColumn(name="created_at", detected_type="String", nullable=False),
        DetectedColumn(name="label", detected_type="Nullable(String)", nullable=True),
    ]


def test_infer_column_types_can_infer_temporal_columns(engine: CsvIngestionEngine) -> None:
    previous_setting = INGESTION_SETTINGS["INFER_TEMPORAL_TYPES"]
    INGESTION_SETTINGS["INFER_TEMPORAL_TYPES"] = True

    try:
        headers = ["created_at"]
        rows = [
            {"created_at": "2024-01-01 10:00:00"},
            {"created_at": "2024-01-02 11:00:00"},
        ]

        inferred = engine.infer_column_types(headers, rows)

        assert inferred == [
            DetectedColumn(name="created_at", detected_type="DateTime", nullable=False),
        ]
    finally:
        INGESTION_SETTINGS["INFER_TEMPORAL_TYPES"] = previous_setting


def test_first_rows_before_import_marks_human_review(
    engine: CsvIngestionEngine,
    tmp_path: Path,
) -> None:
    path = tmp_path / "bad.csv"
    path.write_text("id;amount\n1;12.5\n2;oops\n", encoding="utf-8")

    columns = [
        DetectedColumn(name="id", detected_type="Int64", nullable=False),
        DetectedColumn(name="amount", detected_type="Float64", nullable=False),
    ]

    result = engine.validate_first_rows_before_import(path, ";", columns)

    assert result.needs_human_review is True
    assert "Cannot cast" in result.review_reason


def test_build_create_table_sql_quotes_identifiers(engine: CsvIngestionEngine) -> None:
    columns = [
        DetectedColumn(name="order_id", detected_type="Int64", nullable=False),
        DetectedColumn(name="customer_name", detected_type="String", nullable=False),
    ]

    sql = engine.build_create_table_sql("lab_db", "sales", columns)

    assert "CREATE TABLE IF NOT EXISTS `lab_db`.`sales`" in sql
    assert "`order_id` Int64" in sql
    assert "`customer_name` String" in sql


@pytest.mark.parametrize(
    "value, column, expected",
    [
        ("7", DetectedColumn(name="id", detected_type="Int64", nullable=False), 7),
        ("1,5", DetectedColumn(name="ratio", detected_type="Float64", nullable=False), 1.5),
        ("2024-01-31", DetectedColumn(name="day", detected_type="Date", nullable=False), date(2024, 1, 31)),
        (
            "2024-01-31 10:20:30",
            DetectedColumn(name="moment", detected_type="DateTime", nullable=False),
            datetime(2024, 1, 31, 10, 20, 30),
        ),
        ("hello", DetectedColumn(name="label", detected_type="String", nullable=False), "hello"),
        ("null", DetectedColumn(name="maybe_id", detected_type="Nullable(Int64)", nullable=True), None),
    ],
)
def test_cast_value(
    engine: CsvIngestionEngine,
    value: str | None,
    column: DetectedColumn,
    expected,
) -> None:
    assert engine.cast_value(value, column, 12) == expected


def test_cast_value_rejects_null_for_required_column(engine: CsvIngestionEngine) -> None:
    column = DetectedColumn(name="id", detected_type="Int64", nullable=False)

    with pytest.raises(ValueError, match="NULL value is not allowed"):
        engine.cast_value(None, column, 8)


def test_cast_value_rejects_invalid_conversion(engine: CsvIngestionEngine) -> None:
    column = DetectedColumn(name="amount", detected_type="Float64", nullable=False)

    with pytest.raises(ValueError, match="Cannot cast"):
        engine.cast_value("oops", column, 4)


def test_log_import_metadata_safely_does_not_raise(engine: CsvIngestionEngine) -> None:
    result = IngestionResult(
        source_path="sample.csv",
        target_database="lab_db",
        target_table="sample",
        detected_delimiter=",",
        row_count=1,
        column_count=1,
        status="success",
        error_message="",
    )
    sample_check = SampleCheck(
        sample_rows_checked=1,
        needs_human_review=False,
        review_reason="",
    )
    engine.log_import_metadata = MagicMock(side_effect=RuntimeError("meta failed"))  # type: ignore[method-assign]

    engine.log_import_metadata_safely(result, [], sample_check)
