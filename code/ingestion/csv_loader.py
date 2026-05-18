from __future__ import annotations

import csv
from dataclasses import dataclass, asdict
from datetime import date, datetime
from pathlib import Path

from core.client import CH_DB, META_DB
from core.meta import ensure_meta_schema
from core.schema import q_ident


NULL_TOKENS = {"", "null", "none", "nan", "na", "n/a"}
DELIMITERS = [",", ";", "\t"]


@dataclass
class DetectedColumn:
    name: str
    detected_type: str
    nullable: bool


@dataclass
class IngestionResult:
    source_path: str
    target_database: str
    target_table: str
    detected_delimiter: str
    row_count: int
    column_count: int
    status: str
    error_message: str


def import_csv_to_clickhouse(
    client,
    csv_path: str | Path,
    table_name: str | None = None,
    database: str = CH_DB,
    sample_size: int = 5000,
) -> dict:
    """
    Import a CSV file into ClickHouse using automatic schema inference.

    The function detects the CSV delimiter, reads a bounded sample of rows,
    infers ClickHouse-compatible column types, validates the first rows, creates
    the target table, inserts the full file, and records ingestion metadata.
    """

    path = Path(csv_path)
    table = table_name or clean_identifier(path.stem)

    delimiter = ","
    columns: list[DetectedColumn] = []
    row_count = 0
    sample_check = {
        "sample_rows_checked": 0,
        "needs_human_review": False,
        "review_reason": "",
    }

    try:
        ensure_meta_schema(client)

        delimiter = detect_delimiter(path)
        headers, sample_rows = read_csv_sample(path, delimiter, sample_size)
        columns = infer_column_types(headers, sample_rows)

        sample_check = validate_first_rows_before_import(path, delimiter, columns)

        if sample_check["needs_human_review"]:
            result = IngestionResult(
                source_path=str(path),
                target_database=database,
                target_table=table,
                detected_delimiter=delimiter,
                row_count=0,
                column_count=len(columns),
                status="needs_human_review",
                error_message=sample_check["review_reason"],
            )

            log_ingestion_result(client, result)
            log_detected_columns(client, result, columns)
            log_ingestion_source(client, result, sample_check)

            print(f"Import bloqué : intervention humaine requise pour {path}")
            print(sample_check["review_reason"])
            return asdict(result)

        create_database(client, database)
        create_table(client, database, table, columns)

        row_count = insert_csv_rows(client, path, database, table, columns, delimiter)

        result = IngestionResult(
            source_path=str(path),
            target_database=database,
            target_table=table,
            detected_delimiter=delimiter,
            row_count=row_count,
            column_count=len(columns),
            status="success",
            error_message="",
        )

    except Exception as exc:
        result = IngestionResult(
            source_path=str(path),
            target_database=database,
            target_table=table,
            detected_delimiter=delimiter,
            row_count=row_count,
            column_count=len(columns),
            status="failed",
            error_message=str(exc),
        )

        log_ingestion_result(client, result)
        if columns:
            log_detected_columns(client, result, columns)
        log_ingestion_source(client, result, sample_check)
        raise

    log_ingestion_result(client, result)
    log_detected_columns(client, result, columns)
    log_ingestion_source(client, result, sample_check)

    print(f"CSV importé avec succès : {row_count} lignes dans {database}.{table}")
    return asdict(result)


def detect_delimiter(path: Path) -> str:
    """
    Detect the delimiter used by a CSV file.

    The function first uses Python's CSV sniffer on a bounded file sample.
    If sniffer detection fails, it falls back to the most frequent supported
    delimiter among comma, semicolon, and tab.
    """
    sample = path.read_text(encoding="utf-8-sig", errors="ignore")[:8192]

    try:
        return csv.Sniffer().sniff(sample, delimiters=DELIMITERS).delimiter
    except csv.Error:
        return max(DELIMITERS, key=sample.count)


def read_csv_sample(path: Path, delimiter: str, sample_size: int) -> tuple[list[str], list[dict]]:
    """
    Read a bounded sample of rows from a CSV file.

    Column names are normalized into ClickHouse-safe identifiers and duplicate
    names are resolved deterministically. The sample is later used for type
    inference and pre-ingestion validation.
    """
    with path.open("r", encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file, delimiter=delimiter)

        original_headers = reader.fieldnames or []
        headers = dedupe_names([clean_identifier(name) for name in original_headers])

        rows = []
        for index, row in enumerate(reader):
            if index >= sample_size:
                break

            check_malformed_row(row, path, index + 2, delimiter)

            clean_row = {}
            for i, original_name in enumerate(original_headers):
                clean_row[headers[i]] = row.get(original_name)

            rows.append(clean_row)

    return headers, rows


def infer_column_types(headers: list[str], rows: list[dict]) -> list[DetectedColumn]:
    """
    Infer ClickHouse-compatible column types from sampled CSV rows.

    Missing values are ignored when selecting the base type, but they mark the
    resulting column as nullable. Supported inferred types are Int64, Float64,
    Date, DateTime, and String.
    """
    columns = []

    for header in headers:
        values = [clean_value(row.get(header)) for row in rows]
        present_values = [value for value in values if value is not None]

        nullable = len(present_values) < len(values)
        column_type = detect_type(present_values)

        if nullable:
            column_type = f"Nullable({column_type})"

        columns.append(
            DetectedColumn(
                name=header,
                detected_type=column_type,
                nullable=nullable,
            )
        )

    return columns


def detect_type(values: list[str]) -> str:
    """
    Select the narrowest supported ClickHouse type for observed values.

    The type order is intentionally conservative: integers, datetimes, dates,
    floats, then strings. Empty input defaults to String.
    """
    if not values:
        return "String"

    if all(is_int(value) for value in values):
        return "Int64"

    if all(is_datetime(value) for value in values):
        return "DateTime"

    if all(is_date(value) for value in values):
        return "Date"

    if all(is_float(value) for value in values):
        return "Float64"

    return "String"


def validate_first_rows_before_import(
    path: Path,
    delimiter: str,
    columns: list[DetectedColumn],
    row_limit: int = 5,
) -> dict:
    """
    Validate a small prefix of the CSV before full ingestion.

    This preflight check casts the first rows according to the inferred schema.
    If casting fails, or if rows contain more fields than the header, the source
    is marked as requiring human review instead of failing silently.
    """
    checked_rows = 0

    try:
        with path.open("r", encoding="utf-8-sig", newline="") as file:
            reader = csv.DictReader(file, delimiter=delimiter)
            original_headers = reader.fieldnames or []

            for line_number, row in enumerate(reader, start=2):
                if checked_rows >= row_limit:
                    break

                check_malformed_row(row, path, line_number, delimiter)

                for index, column in enumerate(columns):
                    value = row.get(original_headers[index])
                    cast_value(value, column, line_number)

                checked_rows += 1

        return {
            "sample_rows_checked": checked_rows,
            "needs_human_review": False,
            "review_reason": "",
        }

    except Exception as exc:
        return {
            "sample_rows_checked": checked_rows,
            "needs_human_review": True,
            "review_reason": str(exc),
        }


def create_database(client, database: str) -> None:
    client.command(f"CREATE DATABASE IF NOT EXISTS {q_ident(database)}")


def create_table(client, database: str, table: str, columns: list[DetectedColumn]) -> None:
    client.command(build_create_table_sql(database, table, columns))


def build_create_table_sql(database: str, table: str, columns: list[DetectedColumn]) -> str:
    """
    Render the ClickHouse CREATE TABLE statement for an inferred schema.

    The table uses MergeTree with ORDER BY tuple(), because no physical ordering
    key is assumed during raw ingestion.
    """
    column_lines = []

    for column in columns:
        column_lines.append(f"    {q_ident(column.name)} {column.detected_type}")

    columns_sql = ",\n".join(column_lines)

    return f"""
CREATE TABLE IF NOT EXISTS {q_ident(database)}.{q_ident(table)}
(
{columns_sql}
)
ENGINE = MergeTree
ORDER BY tuple()
"""


def insert_csv_rows(
    client,
    path: Path,
    database: str,
    table: str,
    columns: list[DetectedColumn],
    delimiter: str,
) -> int:
    """
    Insert all CSV rows into the target ClickHouse table.

    Each raw CSV value is cleaned and cast according to the inferred schema
    before insertion. Casting errors include the source line and column name.
    """
    column_names = [column.name for column in columns]
    data = []

    with path.open("r", encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file, delimiter=delimiter)
        original_headers = reader.fieldnames or []

        for line_number, row in enumerate(reader, start=2):
            check_malformed_row(row, path, line_number, delimiter)

            data.append([
                cast_value(row.get(original_headers[index]), columns[index], line_number)
                for index in range(len(columns))
            ])

    if data:
        client.insert(
            f"{database}.{table}",
            data,
            column_names=column_names,
        )

    return len(data)


def log_ingestion_result(client, result: IngestionResult) -> None:
    """
    Persist run-level ingestion metadata.

    The metadata records the source path, target table, detected delimiter,
    row count, column count, status, and error message. This supports
    reproducibility and auditing of ingestion runs.
    """
    ensure_meta_schema(client)

    client.insert(
        f"{META_DB}.ingestion_runs",
        [[
            result.source_path,
            result.target_database,
            result.target_table,
            result.detected_delimiter,
            result.row_count,
            result.column_count,
            result.status,
            result.error_message,
        ]],
        column_names=[
            "source_path",
            "target_database",
            "target_table",
            "detected_delimiter",
            "row_count",
            "column_count",
            "status",
            "error_message",
        ],
    )


def log_detected_columns(
    client,
    result: IngestionResult,
    columns: list[DetectedColumn],
) -> None:
    """
    Persist inferred column metadata.

    The stored schema is used by downstream profiling and validation steps.
    Each row records a detected column name, inferred type, and nullability.
    """
    ensure_meta_schema(client)

    rows = []
    for column in columns:
        rows.append([
            result.target_database,
            result.target_table,
            column.name,
            column.detected_type,
            column.nullable,
        ])

    client.insert(
        f"{META_DB}.detected_columns",
        rows,
        column_names=[
            "target_database",
            "target_table",
            "column_name",
            "detected_type",
            "nullable",
        ],
    )


def log_ingestion_source(client, result: IngestionResult, sample_check: dict) -> None:
    """
    Persist source-level diagnostics.

    This table records whether the source passed the pre-ingestion validation
    or requires human review, together with the review reason.
    """
    ensure_meta_schema(client)

    client.insert(
        f"{META_DB}.ingestion_sources",
        [[
            result.source_path,
            result.target_database,
            result.target_table,
            result.detected_delimiter,
            sample_check["sample_rows_checked"],
            sample_check["needs_human_review"],
            sample_check["review_reason"],
        ]],
        column_names=[
            "source_path",
            "target_database",
            "target_table",
            "detected_delimiter",
            "sample_rows_checked",
            "needs_human_review",
            "review_reason",
        ],
    )


def check_malformed_row(row: dict, path: Path, line_number: int, delimiter: str) -> None:
    if row.get(None):
        raise ValueError(
            f"CSV mal formé dans {path}, ligne {line_number}: colonnes en trop. "
            f"Si une décimale utilise '{delimiter}', mets la valeur entre guillemets "
            f"ou utilise un autre séparateur."
        )


def clean_identifier(value: str | None) -> str:
    text = (value or "").strip()
    cleaned = ""

    for char in text:
        if char.isalnum() or char == "_":
            cleaned += char
        else:
            cleaned += "_"

    cleaned = "_".join(part for part in cleaned.split("_") if part)

    if not cleaned:
        cleaned = "column"

    if cleaned[0].isdigit():
        cleaned = "col_" + cleaned

    return cleaned


def dedupe_names(names: list[str]) -> list[str]:
    seen = {}
    result = []

    for name in names:
        count = seen.get(name, 0)
        seen[name] = count + 1

        if count == 0:
            result.append(name)
        else:
            result.append(f"{name}_{count + 1}")

    return result


def clean_value(value: str | None):
    """
    Cast one CSV value according to an inferred ClickHouse column definition.

    Null values are accepted only for nullable columns. Conversion failures
    raise a contextual error containing the line number, column name, raw value,
    and expected type.
    """
    if value is None:
        return None

    value = value.strip()

    if value.lower() in NULL_TOKENS:
        return None

    return value


def cast_value(value: str | None, column: DetectedColumn, line_number: int):
    value = clean_value(value)

    if value is None:
        if not column.nullable:
            raise ValueError(
                f"Valeur NULL interdite ligne {line_number}, "
                f"colonne '{column.name}' de type {column.detected_type}"
            )
        return None

    base_type = column.detected_type.replace("Nullable(", "").replace(")", "")

    try:
        if base_type == "Int64":
            return int(value)

        if base_type == "Float64":
            return float(value.replace(",", "."))

        if base_type == "Date":
            return parse_date(value)

        if base_type == "DateTime":
            return parse_datetime(value)

        return value

    except ValueError as exc:
        raise ValueError(
            f"Cast impossible ligne {line_number}, colonne '{column.name}', "
            f"valeur '{value}' vers {base_type}"
        ) from exc


def is_int(value: str) -> bool:
    try:
        int(value)
        return "." not in value and "," not in value
    except ValueError:
        return False


def is_float(value: str) -> bool:
    try:
        float(value.replace(",", "."))
        return True
    except ValueError:
        return False


def is_date(value: str) -> bool:
    try:
        parse_date(value)
        return True
    except ValueError:
        return False


def is_datetime(value: str) -> bool:
    try:
        parse_datetime(value)
        return True
    except ValueError:
        return False


def parse_date(value: str) -> date:
    formats = ["%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y"]

    for fmt in formats:
        try:
            if fmt == "%Y-%m-%d":
                return date.fromisoformat(value)
            return datetime.strptime(value, fmt).date()
        except ValueError:
            pass

    raise ValueError(f"Invalid Date value: {value}")


def parse_datetime(value: str) -> datetime:
    formats = [
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%dT%H:%M:%S",
        "%d/%m/%Y %H:%M:%S",
    ]

    for fmt in formats:
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            pass

    raise ValueError(f"Invalid DateTime value: {value}")
