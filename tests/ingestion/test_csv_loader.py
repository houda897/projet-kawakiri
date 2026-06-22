from __future__ import annotations

import csv
from datetime import date, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import cast
from unittest.mock import MagicMock

import pytest
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


def test_detect_delimiter_fallback_prefers_stable_columns(
    engine: CsvIngestionEngine,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "sample.csv"
    path.write_text(
        "id;comment;score\n1;hello, with comma;10\n2;another, comma;20\n",
        encoding="utf-8",
    )

    def raise_sniff(*args, **kwargs):
        raise csv.Error("cannot sniff")

    monkeypatch.setattr(csv.Sniffer, "sniff", raise_sniff)

    assert engine.detect_delimiter(path) == ";"


def test_read_csv_sample_cleans_headers_and_skips_dirty_rows(
    engine: CsvIngestionEngine,
    tmp_path: Path,
) -> None:
    path = tmp_path / "sample.csv"
    path.write_text(
        "Customer ID;Name\n1;Alice\n---;---\n2;Bob\n",
        encoding="utf-8",
    )

    headers, rows = engine.read_csv_sample(path, ";", sample_size=None)

    assert headers == ["Customer_ID", "Name"]
    assert rows == [
        {"Customer_ID": "1", "Name": "Alice"},
        {"Customer_ID": "2", "Name": "Bob"},
    ]


def test_import_folder_uses_subfolder_name_and_appends_after_first_file(
    engine: CsvIngestionEngine,
    tmp_path: Path,
) -> None:
    folder = tmp_path / "data"
    table_folder = folder / "tickets"
    table_folder.mkdir(parents=True)
    first_file = table_folder / "part1.csv"
    second_file = table_folder / "part2.csv"
    first_file.write_text("id\n1\n", encoding="utf-8")
    second_file.write_text("id\n2\n", encoding="utf-8")

    engine.import_csv_to_clickhouse = MagicMock(return_value={"status": "success"})  # type: ignore[method-assign]

    engine.import_csv_folder_to_clickhouse(folder, if_exists="replace")

    calls = engine.import_csv_to_clickhouse.call_args_list
    assert calls[0].kwargs["table_name"] == "tickets"
    assert calls[0].kwargs["if_exists"] == "replace"
    assert calls[1].kwargs["table_name"] == "tickets"
    assert calls[1].kwargs["if_exists"] == "append"


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
    assert engine.dedupe_names(["a", "a", "b", "a"]) == ["a", "a_2", "b", "a_3"]


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


def test_clean_value_uses_configurable_null_tokens(
    engine: CsvIngestionEngine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setitem(
        INGESTION_SETTINGS,
        "NULL_TOKENS",
        ("", "null", "missing"),
    )

    assert engine.clean_value(" missing ") is None


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
        DetectedColumn(name="created_at", detected_type="DateTime", nullable=False),
        DetectedColumn(name="label", detected_type="Nullable(String)", nullable=True),
    ]


def test_infer_column_types_can_infer_temporal_columns(engine: CsvIngestionEngine) -> None:
    previous_setting = INGESTION_SETTINGS["INFER_TEMPORAL_TYPES"]
    INGESTION_SETTINGS["INFER_TEMPORAL_TYPES"] = True

    try:
        inferred = engine.infer_column_types(
            ["created_at"],
            [
                {"created_at": "2024-01-01 10:00:00"},
                {"created_at": "2024-01-02 11:00:00"},
            ],
        )

        assert inferred == [
            DetectedColumn(name="created_at", detected_type="DateTime", nullable=False),
        ]
    finally:
        INGESTION_SETTINGS["INFER_TEMPORAL_TYPES"] = previous_setting


def test_date_formats_are_configurable(
    engine: CsvIngestionEngine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setitem(INGESTION_SETTINGS, "DATE_FORMATS", ("%d/%m/%Y",))

    assert engine.parse_date("01/02/2024") == date(2024, 2, 1)
    assert engine.is_date("2024-02-01") is False


def test_validate_first_rows_before_import_marks_human_review(
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
    assert "ENGINE = MergeTree" in sql


@pytest.mark.parametrize(
    "value, column, expected",
    [
        ("7", DetectedColumn(name="id", detected_type="Int64", nullable=False), 7),
        ("1,5", DetectedColumn(name="ratio", detected_type="Float64", nullable=False), 1.5),
        (
            "2024-01-31",
            DetectedColumn(name="day", detected_type="Date", nullable=False),
            date(2024, 1, 31),
        ),
        (
            "2024-01-31 10:20:30",
            DetectedColumn(name="moment", detected_type="DateTime", nullable=False),
            datetime(2024, 1, 31, 10, 20, 30),
        ),
        ("hello", DetectedColumn(name="label", detected_type="String", nullable=False), "hello"),
        (
            "null",
            DetectedColumn(name="maybe_id", detected_type="Nullable(Int64)", nullable=True),
            None,
        ),
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


def test_insert_csv_rows_casts_and_inserts_batches(
    engine: CsvIngestionEngine,
    tmp_path: Path,
) -> None:
    path = tmp_path / "rows.csv"
    path.write_text("id;amount\n1;10.5\n2;20.5\n", encoding="utf-8")
    columns = [
        DetectedColumn(name="id", detected_type="Int64", nullable=False),
        DetectedColumn(name="amount", detected_type="Float64", nullable=False),
    ]

    count, skipped_dirty_rows = engine.insert_csv_rows(path, "lab_db", "sales", columns, ";")
    db = cast(MagicMock, engine.db)

    assert count == 2
    assert skipped_dirty_rows == 0
    db.insert.assert_called_once_with(
        "`lab_db`.`sales`",
        [[1, 10.5], [2, 20.5]],
        column_names=["id", "amount"],
    )


def test_insert_csv_rows_counts_rejected_dirty_rows(
    engine: CsvIngestionEngine,
    tmp_path: Path,
) -> None:
    path = tmp_path / "rows.csv"
    path.write_text(
        "id;amount\n1;10.5\n---;---\n2;20.5\n",
        encoding="utf-8",
    )
    columns = [
        DetectedColumn(name="id", detected_type="Int64", nullable=False),
        DetectedColumn(name="amount", detected_type="Float64", nullable=False),
    ]

    count, skipped_dirty_rows = engine.insert_csv_rows(path, "lab_db", "sales", columns, ";")

    assert count == 2
    assert skipped_dirty_rows == 1


def test_is_dirty_row_keeps_business_rows_with_source_values(
    engine: CsvIngestionEngine,
) -> None:
    assert engine.is_dirty_row({"supplier": "Source: Amazon", "amount": "10"}) is False
    assert engine.is_dirty_row({"metadata": "Source: ERP export", "amount": ""}) is True
    assert engine.is_dirty_row({"a": "---", "b": "---"}) is True
    assert engine.is_dirty_row({"a": "", "b": ""}) is True


def test_log_import_metadata_does_not_raise_when_metadata_write_fails(
    engine: CsvIngestionEngine,
) -> None:
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
    engine.log_ingestion_result = MagicMock(side_effect=RuntimeError("meta failed"))  # type: ignore[method-assign]

    engine.log_import_metadata(result, [], sample_check)


def test_log_detected_columns_uses_original_metadata_shape(engine: CsvIngestionEngine) -> None:
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
    columns = [DetectedColumn(name="id", detected_type="Int64", nullable=False)]

    engine.log_detected_columns(result, columns)

    db = cast(MagicMock, engine.db)
    table, rows = db.insert.call_args[0]
    assert table.endswith(".detected_columns")
    assert rows[0] == ["lab_db", "sample", "id", "Int64", False]


def test_table_exists_reads_system_tables(engine: CsvIngestionEngine) -> None:
    db = cast(MagicMock, engine.db)
    db.query.return_value = SimpleNamespace(result_rows=[(1,)])

    assert engine.table_exists("lab_db", "sales") is True
