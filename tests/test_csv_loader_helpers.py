from __future__ import annotations

import csv
import sys
from datetime import date, datetime
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
CODE_DIR = ROOT / "code"
if str(CODE_DIR) not in sys.path:
    sys.path.insert(0, str(CODE_DIR))

from ingestion.csv_loader import (  # noqa: E402
    DetectedColumn,
    build_create_table_sql,
    cast_value,
    check_malformed_row,
    clean_identifier,
    clean_value,
    dedupe_names,
    detect_delimiter,
    infer_column_types,
    is_date,
    is_datetime,
    is_float,
    is_int,
    validate_first_rows_before_import,
)


def test_detect_delimiter_uses_sniffer(tmp_path: Path) -> None:
    path = tmp_path / "sample.csv"
    path.write_text("id;name;score\n1;Alice;10\n2;Bob;20\n", encoding="utf-8")

    assert detect_delimiter(path) == ";"


def test_detect_delimiter_falls_back_to_most_frequent_delimiter(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "sample.csv"
    path.write_text("id\tname\tscore\n1\tAlice\t10\n2\tBob\t20\n", encoding="utf-8")

    def raise_sniff(*args, **kwargs):
        raise csv.Error("cannot sniff")

    monkeypatch.setattr(csv.Sniffer, "sniff", raise_sniff)

    assert detect_delimiter(path) == "\t"


def test_check_malformed_row_rejects_extra_columns(tmp_path: Path) -> None:
    path = tmp_path / "bad.csv"
    row = {"id": "1", "amount": "12", None: ["5"]}

    with pytest.raises(ValueError, match="colonnes en trop"):
        check_malformed_row(row, path, 2, ",")


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("  Hello, World!  ", "Hello_World"),
        ("123abc", "col_123abc"),
        ("__a---b__", "a_b"),
        (None, "column"),
    ],
)
def test_clean_identifier(raw: str | None, expected: str) -> None:
    assert clean_identifier(raw) == expected


def test_dedupe_names_appends_stable_suffixes() -> None:
    assert dedupe_names(["a", "a", "b", "a", "b"]) == ["a", "a_2", "b", "a_3", "b_2"]


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
def test_clean_value(raw: str | None, expected: str | None) -> None:
    assert clean_value(raw) == expected


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
def test_is_int(value: str, expected: bool) -> None:
    assert is_int(value) is expected


@pytest.mark.parametrize(
    "value, expected",
    [
        ("12", True),
        ("1.25", True),
        ("1,25", True),
        ("abc", False),
    ],
)
def test_is_float(value: str, expected: bool) -> None:
    assert is_float(value) is expected


@pytest.mark.parametrize(
    "value, expected",
    [
        ("2024-01-31", True),
        ("31/01/2024", True),
        ("01/31/2024", True),
        ("2024/01/31", False),
    ],
)
def test_is_date(value: str, expected: bool) -> None:
    assert is_date(value) is expected


@pytest.mark.parametrize(
    "value, expected",
    [
        ("2024-01-31 10:20:30", True),
        ("2024-01-31T10:20:30", True),
        ("31/01/2024 10:20:30", True),
        ("2024-01-31", False),
    ],
)
def test_is_datetime(value: str, expected: bool) -> None:
    assert is_datetime(value) is expected


def test_infer_column_types_marks_nullable_columns() -> None:
    headers = ["id", "amount", "created_at", "label"]
    rows = [
        {
            "id": "1",
            "amount": "1,25",
            "created_at": "2024-01-01 10:00:00",
            "label": "alpha",
        },
        {
            "id": "2",
            "amount": "2.5",
            "created_at": "2024-01-02 11:00:00",
            "label": "",
        },
        {
            "id": "3",
            "amount": "3.0",
            "created_at": "2024-01-03 12:00:00",
            "label": None,
        },
    ]

    inferred = infer_column_types(headers, rows)

    assert inferred == [
        DetectedColumn(name="id", detected_type="Int64", nullable=False),
        DetectedColumn(name="amount", detected_type="Float64", nullable=False),
        DetectedColumn(name="created_at", detected_type="DateTime", nullable=False),
        DetectedColumn(name="label", detected_type="Nullable(String)", nullable=True),
    ]


def test_first_rows_before_import_marks_human_review(tmp_path: Path) -> None:
    path = tmp_path / "bad.csv"
    path.write_text("id;amount\n1;12.5\n2;oops\n", encoding="utf-8")

    columns = [
        DetectedColumn(name="id", detected_type="Int64", nullable=False),
        DetectedColumn(name="amount", detected_type="Float64", nullable=False),
    ]

    result = validate_first_rows_before_import(path, ";", columns)

    assert result["needs_human_review"] is True
    assert "Cast impossible" in result["review_reason"]


def test_build_create_table_sql_quotes_identifiers() -> None:
    columns = [
        DetectedColumn(name="order_id", detected_type="Int64", nullable=False),
        DetectedColumn(name="customer_name", detected_type="String", nullable=False),
    ]

    sql = build_create_table_sql("lab_db", "sales", columns)

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
def test_cast_value(value: str | None, column: DetectedColumn, expected) -> None:
    assert cast_value(value, column, 12) == expected


def test_cast_value_rejects_null_for_required_column() -> None:
    column = DetectedColumn(name="id", detected_type="Int64", nullable=False)

    with pytest.raises(ValueError, match=r"Valeur NULL interdite ligne 8, colonne 'id' de type Int64"):
        cast_value(None, column, 8)


def test_cast_value_rejects_invalid_conversion() -> None:
    column = DetectedColumn(name="amount", detected_type="Float64", nullable=False)

    with pytest.raises(ValueError, match=r"Cast impossible ligne 4, colonne 'amount', valeur 'oops' vers Float64"):
        cast_value("oops", column, 4)
