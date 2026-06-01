from __future__ import annotations

import csv
from dataclasses import asdict, dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any, Literal

from core.clickhouse_manager import CH_DB, META_DB, clickhouse_manager
from core.logger import get_logger
from core.meta import ensure_meta_schema
from core.schema import q_ident

logger = get_logger(__name__)

NULL_TOKENS = {"", "null", "none", "nan", "na", "n/a", "\\n", "\\N"}
DELIMITERS = [",", ";", "\t"]
BATCH_SIZE = 10_000


@dataclass
class DetectedColumn:
    """Column detected from a CSV file before it is created in ClickHouse."""

    name: str
    detected_type: str
    nullable: bool


@dataclass
class IngestionResult:
    """Summary of one CSV import attempt."""

    source_path: str
    target_database: str
    target_table: str
    detected_delimiter: str
    row_count: int
    column_count: int
    status: str
    error_message: str


@dataclass
class SampleCheck:
    """Small pre-import check used to detect obvious parsing or typing problems."""

    sample_rows_checked: int
    needs_human_review: bool
    review_reason: str


class CsvIngestionEngine:
    """
    Import CSV files into ClickHouse while keeping metadata about each import.
    """

    def __init__(self, db: clickhouse_manager):
        self.db = db

    def import_csv_to_clickhouse(
        self,
        csv_path: str | Path,
        table_name: str | None = None,
        database: str = CH_DB,
        sample_size: int | None = None,
        if_exists: Literal["replace", "append", "fail"] = "replace",
    ) -> dict:
        path = Path(csv_path)
        table = table_name or self.clean_identifier(path.stem)

        delimiter = ","
        columns: list[DetectedColumn] = []
        row_count = 0
        sample_check = SampleCheck(0, False, "")

        try:
            ensure_meta_schema(self.db)

            delimiter = self.detect_delimiter(path)
            headers, sample_rows = self.read_csv_sample(path, delimiter, sample_size)
            columns = self.infer_column_types(headers, sample_rows)
            sample_check = self.validate_first_rows_before_import(path, delimiter, columns)

            if sample_check.needs_human_review:
                result = IngestionResult(
                    source_path=str(path),
                    target_database=database,
                    target_table=table,
                    detected_delimiter=delimiter,
                    row_count=0,
                    column_count=len(columns),
                    status="needs_human_review",
                    error_message=sample_check.review_reason,
                )
                self.log_import_metadata(result, columns, sample_check)
                logger.warning("Import blocked for human review: %s", path)
                return asdict(result)

            self.create_database(database)
            self.prepare_table(database, table, columns, if_exists)

            row_count = self.insert_csv_rows(path, database, table, columns, delimiter)

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
            self.log_import_metadata(result, columns, sample_check)
            logger.error("CSV import failed for %s: %s", path, exc)
            raise

        self.log_import_metadata(result, columns, sample_check)
        logger.info("CSV imported: %s rows into %s.%s", row_count, database, table)
        return asdict(result)

    def import_csv_folder_to_clickhouse(
        self,
        folder_path: str | Path,
        database: str = CH_DB,
        sample_size: int | None = None,
        if_exists: Literal["replace", "append", "fail"] = "replace",
    ) -> list[dict]:
        folder = Path(folder_path)

        if not folder.exists():
            raise FileNotFoundError(f"Folder not found: {folder}")

        if not folder.is_dir():
            raise NotADirectoryError(f"Expected a folder, got: {folder}")

        results = []

        for csv_file in sorted(folder.glob("*.csv")):
            results.append(
                self.import_csv_to_clickhouse(
                    csv_path=csv_file,
                    table_name=None,
                    database=database,
                    sample_size=sample_size,
                    if_exists=if_exists,
                )
            )

        return results

    def detect_delimiter(self, path: Path) -> str:
        sample = path.read_text(encoding="utf-8-sig", errors="ignore")[:8192]

        try:
            return csv.Sniffer().sniff(sample, delimiters="".join(DELIMITERS)).delimiter
        except csv.Error:
            return max(DELIMITERS, key=sample.count)

    def read_csv_sample(
        self,
        path: Path,
        delimiter: str,
        sample_size: int | None,
    ) -> tuple[list[str], list[dict]]:
        with path.open("r", encoding="utf-8-sig", newline="") as file:
            reader = csv.DictReader(file, delimiter=delimiter)
            original_headers = reader.fieldnames or []

            if not original_headers:
                raise ValueError(f"CSV file has no header: {path}")

            headers = self.dedupe_names(
                [self.clean_identifier(name) for name in original_headers]
            )

            rows = []

            for index, row in enumerate(reader):
                if sample_size is not None and index >= sample_size:
                    break

                self.check_malformed_row(row, path, index + 2, delimiter)

                row_data = {
                    headers[i]: row.get(original_headers[i])
                    for i in range(len(original_headers))
                }

                if self.is_dirty_row(row_data):
                    continue

                rows.append(row_data)

        return headers, rows

    def infer_column_types(
        self,
        headers: list[str],
        rows: list[dict],
    ) -> list[DetectedColumn]:
        columns = []

        for header in headers:
            values = [self.clean_value(row.get(header)) for row in rows]
            present_values = [value for value in values if value is not None]

            nullable = len(present_values) < len(values)
            column_type = self.detect_type(present_values)

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

    def detect_type(self, values: list[str]) -> str:
        if not values:
            return "String"

        if all(self.is_int(value) for value in values):
            return "Int64"

        if all(self.is_datetime(value) for value in values):
            return "String"

        if all(self.is_date(value) for value in values):
            return "Date32"

        if all(self.is_float(value) for value in values):
            return "Float64"

        return "String"

    def validate_first_rows_before_import(
        self,
        path: Path,
        delimiter: str,
        columns: list[DetectedColumn],
        row_limit: int = 5,
    ) -> SampleCheck:
        checked_rows = 0

        try:
            with path.open("r", encoding="utf-8-sig", newline="") as file:
                reader = csv.DictReader(file, delimiter=delimiter)
                original_headers = reader.fieldnames or []

                for line_number, row in enumerate(reader, start=2):
                    if checked_rows >= row_limit:
                        break

                    self.check_malformed_row(row, path, line_number, delimiter)

                    row_data = {
                        columns[index].name: row.get(original_headers[index])
                        for index in range(len(columns))
                    }

                    if self.is_dirty_row(row_data):
                        continue

                    for column in columns:
                        self.cast_value(row_data[column.name], column, line_number)

                    checked_rows += 1

        except (ValueError, TypeError, KeyError, IndexError) as exc:
            return SampleCheck(
                sample_rows_checked=checked_rows,
                needs_human_review=True,
                review_reason=str(exc),
            )

        return SampleCheck(
            sample_rows_checked=checked_rows,
            needs_human_review=False,
            review_reason="",
        )

    def create_database(self, database: str) -> None:
        self.db.command(f"CREATE DATABASE IF NOT EXISTS {q_ident(database)}")

    def prepare_table(
        self,
        database: str,
        table: str,
        columns: list[DetectedColumn],
        if_exists: Literal["replace", "append", "fail"],
    ) -> None:
        if not columns:
            raise ValueError(f"Cannot create table '{table}': no columns were detected.")

        if if_exists not in {"replace", "append", "fail"}:
            raise ValueError("if_exists must be one of: replace, append, fail")

        exists = self.table_exists(database, table)

        if exists and if_exists == "fail":
            raise ValueError(
                f"Table {database}.{table} already exists. "
                "Use if_exists='replace' or if_exists='append'."
            )

        if exists and if_exists == "replace":
            self.db.command(f"DROP TABLE {q_ident(database)}.{q_ident(table)}")

        self.db.command(self.build_create_table_sql(database, table, columns))

    def table_exists(self, database: str, table: str) -> bool:
        sql = """
        SELECT count()
        FROM system.tables
        WHERE database = %(database)s
          AND name = %(table)s
        """

        row = self.db.query(
            sql,
            parameters={"database": database, "table": table},
        ).result_rows[0]

        return row[0] > 0

    def build_create_table_sql(
        self,
        database: str,
        table: str,
        columns: list[DetectedColumn],
    ) -> str:
        column_lines = [
            f"    {q_ident(column.name)} {column.detected_type}"
            for column in columns
        ]
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
        self,
        path: Path,
        database: str,
        table: str,
        columns: list[DetectedColumn],
        delimiter: str,
    ) -> int:
        column_names = [column.name for column in columns]
        total_rows = 0
        batch: list[list[Any]] = []

        with path.open("r", encoding="utf-8-sig", newline="") as file:
            reader = csv.DictReader(file, delimiter=delimiter)
            original_headers = reader.fieldnames or []

            for line_number, row in enumerate(reader, start=2):
                self.check_malformed_row(row, path, line_number, delimiter)

                row_data = {
                    column_names[index]: row.get(original_headers[index])
                    for index in range(len(columns))
                }

                if self.is_dirty_row(row_data):
                    continue

                batch.append(
                    [
                        self.cast_value(row_data[column.name], column, line_number)
                        for column in columns
                    ]
                )

                if len(batch) >= BATCH_SIZE:
                    self.db.insert(
                        f"{database}.{table}",
                        batch,
                        column_names=column_names,
                    )
                    total_rows += len(batch)
                    batch = []

        if batch:
            self.db.insert(
                f"{database}.{table}",
                batch,
                column_names=column_names,
            )
            total_rows += len(batch)

        return total_rows

    def log_import_metadata(
        self,
        result: IngestionResult,
        columns: list[DetectedColumn],
        sample_check: SampleCheck,
    ) -> None:
        self.log_ingestion_result(result)
        self.log_detected_columns(result, columns)
        self.log_ingestion_source(result, sample_check)

    def log_ingestion_result(self, result: IngestionResult) -> None:
        self.db.insert(
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
        self,
        result: IngestionResult,
        columns: list[DetectedColumn],
    ) -> None:
        if not columns:
            return

        rows = [
            [
                result.target_database,
                result.target_table,
                column.name,
                column.detected_type,
                column.nullable,
            ]
            for column in columns
        ]

        self.db.insert(
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

    def log_ingestion_source(
        self,
        result: IngestionResult,
        sample_check: SampleCheck,
    ) -> None:
        self.db.insert(
            f"{META_DB}.ingestion_sources",
            [[
                result.source_path,
                result.target_database,
                result.target_table,
                result.detected_delimiter,
                sample_check.sample_rows_checked,
                sample_check.needs_human_review,
                sample_check.review_reason,
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

    @staticmethod
    def check_malformed_row(
        row: dict,
        path: Path,
        line_number: int,
        delimiter: str,
    ) -> None:
        if row.get(None):
            raise ValueError(
                f"Malformed CSV row in {path}, line {line_number}: extra columns detected. "
                f"If decimal values use '{delimiter}', quote them or use another delimiter."
            )

    @staticmethod
    def is_dirty_row(row_dict: dict[str, str | None]) -> bool:
        if not row_dict:
            return True

        values = [
            value.strip()
            for value in row_dict.values()
            if value is not None and value.strip() != ""
        ]

        if not values:
            return True

        metadata_prefixes = (
            "export date",
            "exported",
            "source",
            "generated",
            "report",
        )

        for value in values:
            value_clean = value.lower()

            if value_clean.startswith(metadata_prefixes):
                return True

            if "---" in value_clean:
                return True

        return False

    @staticmethod
    def clean_identifier(value: str | None) -> str:
        text = (value or "").strip()
        cleaned = ""

        for char in text:
            cleaned += char if char.isalnum() or char == "_" else "_"

        cleaned = "_".join(part for part in cleaned.split("_") if part)

        if not cleaned:
            cleaned = "column"

        if cleaned[0].isdigit():
            cleaned = f"col_{cleaned}"

        return cleaned

    @staticmethod
    def dedupe_names(names: list[str]) -> list[str]:
        seen = {}
        result = []

        for name in names:
            count = seen.get(name, 0)
            seen[name] = count + 1
            result.append(name if count == 0 else f"{name}_{count + 1}")

        return result

    @staticmethod
    def clean_value(value: str | None) -> str | None:
        if value is None:
            return None

        value = value.strip()

        if value.lower() in NULL_TOKENS:
            return None

        return value

    def cast_value(
        self,
        value: str | None,
        column: DetectedColumn,
        line_number: int,
    ) -> Any:
        value = self.clean_value(value)

        if value is None:
            if not column.nullable:
                raise ValueError(
                    f"NULL value is not allowed at line {line_number}, "
                    f"column '{column.name}' with type {column.detected_type}"
                )
            return None

        base_type = self.base_type(column.detected_type)

        try:
            if base_type == "Int64":
                return int(value)

            if base_type == "Float64":
                return float(value.replace(",", "."))

            if base_type in ("Date", "Date32"):
                return self.parse_date(value)

            if base_type == "DateTime":
                return self.parse_datetime(value)

            return value

        except ValueError as exc:
            raise ValueError(
                f"Cannot cast line {line_number}, column '{column.name}', "
                f"value '{value}' to {base_type}"
            ) from exc

    @staticmethod
    def base_type(clickhouse_type: str) -> str:
        return clickhouse_type.removeprefix("Nullable(").removesuffix(")")

    @staticmethod
    def is_int(value: str) -> bool:
        try:
            int(value)
            return "." not in value and "," not in value
        except ValueError:
            return False

    @staticmethod
    def is_float(value: str) -> bool:
        try:
            float(value.replace(",", "."))
            return True
        except ValueError:
            return False

    def is_date(self, value: str) -> bool:
        try:
            self.parse_date(value)
            return True
        except ValueError:
            return False

    def is_datetime(self, value: str) -> bool:
        try:
            self.parse_datetime(value)
            return True
        except ValueError:
            return False

    @staticmethod
    def parse_date(value: str) -> date:
        for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y"):
            try:
                if fmt == "%Y-%m-%d":
                    return date.fromisoformat(value)

                return datetime.strptime(value, fmt).date()

            except ValueError:
                pass

        raise ValueError(f"Invalid Date value: {value}")

    @staticmethod
    def parse_datetime(value: str) -> datetime:
        for fmt in (
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%dT%H:%M:%S",
            "%d/%m/%Y %H:%M:%S",
        ):
            try:
                return datetime.strptime(value, fmt)
            except ValueError:
                pass

        raise ValueError(f"Invalid DateTime value: {value}")