from __future__ import annotations

import csv
from dataclasses import asdict, dataclass
from datetime import date, datetime
from pathlib import Path

from clickhouse_connect.driver import Client
from core.client import CH_DB, META_DB
from core.logger import get_logger
from core.meta import ensure_meta_schema
from core.schema import q_ident

logger = get_logger(__name__)

NULL_TOKENS = {"", "null", "none", "nan", "na", "n/a"}
DELIMITERS = [",", ";", "\t"]
BATCH_SIZE = 10_000


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


def detect_delimiter(path: Path) -> str:
    sample = path.read_text(encoding="utf-8-sig", errors="ignore")[:8192]
    try:
        return csv.Sniffer().sniff(sample, delimiters="".join(DELIMITERS)).delimiter
    except csv.Error:
        return max(DELIMITERS, key=sample.count)


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
    if value is None:
        return None

    value = value.strip()

    if value.lower() in NULL_TOKENS:
        return None

    return value


def _parse_date(value: str) -> date:
    formats = ["%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y"]

    for fmt in formats:
        try:
            if fmt == "%Y-%m-%d":
                return date.fromisoformat(value)
            return datetime.strptime(value, fmt).date()
        except ValueError:
            pass

    raise ValueError(f"Invalid Date value: {value}")


def _parse_datetime(value: str) -> datetime:
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
        _parse_date(value)
        return True
    except ValueError:
        return False


def is_datetime(value: str) -> bool:
    try:
        _parse_datetime(value)
        return True
    except ValueError:
        return False


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
            return _parse_date(value)

        if base_type == "DateTime":
            return _parse_datetime(value)

        return value

    except ValueError as exc:
        raise ValueError(
            f"Cast impossible ligne {line_number}, colonne '{column.name}', "
            f"valeur '{value}' vers {base_type}"
        ) from exc


def infer_column_types(headers: list[str], rows: list[dict]) -> list[DetectedColumn]:
    columns = []

    for header in headers:
        values = [clean_value(row.get(header)) for row in rows]
        present_values = [value for value in values if value is not None]

        nullable = len(present_values) < len(values)
        column_type = _detect_type(present_values)

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


def _detect_type(values: list[str]) -> str:
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

    except (ValueError, TypeError, KeyError) as exc:
        return {
            "sample_rows_checked": checked_rows,
            "needs_human_review": True,
            "review_reason": str(exc),
        }


def build_create_table_sql(database: str, table: str, columns: list[DetectedColumn]) -> str:
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


class CsvIngestionEngine:
    def __init__(self, client: Client):
        self.client = client

    def import_csv_to_clickhouse(
        self,
        csv_path: str | Path,
        table_name: str | None = None,
        database: str = CH_DB,
        sample_size: int = 5000,
    ) -> dict:
        path = Path(csv_path)
        table = table_name or self._clean_identifier(path.stem)

        delimiter = ","
        columns: list[DetectedColumn] = []
        row_count = 0
        sample_check = {
            "sample_rows_checked": 0,
            "needs_human_review": False,
            "review_reason": "",
        }

        try:
            ensure_meta_schema(self.client)

            delimiter = self._detect_delimiter(path)
            headers, sample_rows = self._read_csv_sample(path, delimiter, sample_size)
            columns = self._infer_column_types(headers, sample_rows)

            sample_check = self._validate_first_rows_before_import(path, delimiter, columns)

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

                self._log_ingestion_result(result)
                self._log_detected_columns(result, columns)
                self._log_ingestion_source(result, sample_check)

                logger.warning(f"Import bloqué : intervention humaine requise pour {path}")
                logger.warning(sample_check["review_reason"])
                return asdict(result)

            self._create_database(database)
            self._create_table(database, table, columns)

            row_count = self._insert_csv_rows(path, database, table, columns, delimiter)

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

            self._log_ingestion_result(result)
            if columns:
                self._log_detected_columns(result, columns)
            self._log_ingestion_source(result, sample_check)
            logger.error(f"Erreur lors de l'import de {path}: {exc}", exc_info=True)
            raise

        self._log_ingestion_result(result)
        self._log_detected_columns(result, columns)
        self._log_ingestion_source(result, sample_check)

        logger.info(f"CSV importé avec succès : {row_count} lignes dans {database}.{table}")
        return asdict(result)

    def import_csv_folder_to_clickhouse(
        self,
        folder_path: str | Path,
        database: str = CH_DB,
        sample_size: int = 5000,
    ) -> list[dict]:
        folder = Path(folder_path)

        if not folder.exists():
            raise FileNotFoundError(f"Folder not found: {folder}")

        if not folder.is_dir():
            raise NotADirectoryError(f"Expected a folder, got: {folder}")

        results = []

        for csv_file in sorted(folder.glob("*.csv")):
            result = self.import_csv_to_clickhouse(
                csv_path=csv_file,
                table_name=None,
                database=database,
                sample_size=sample_size,
            )
            results.append(result)

        return results

    def _detect_delimiter(self, path: Path) -> str:
        sample = path.read_text(encoding="utf-8-sig", errors="ignore")[:8192]
        try:
            return csv.Sniffer().sniff(sample, delimiters="".join(DELIMITERS)).delimiter
        except csv.Error:
            return max(DELIMITERS, key=sample.count)

    def _read_csv_sample(
        self, path: Path, delimiter: str, sample_size: int
    ) -> tuple[list[str], list[dict]]:
        with path.open("r", encoding="utf-8-sig", newline="") as file:
            reader = csv.DictReader(file, delimiter=delimiter)

            original_headers = reader.fieldnames or []
            headers = self._dedupe_names(
                [self._clean_identifier(name) for name in original_headers]
            )

            rows = []
            for index, row in enumerate(reader):
                if index >= sample_size:
                    break

                self._check_malformed_row(row, path, index + 2, delimiter)

                clean_row = {}
                for i, original_name in enumerate(original_headers):
                    clean_row[headers[i]] = row.get(original_name)

                rows.append(clean_row)

        return headers, rows

    def _infer_column_types(self, headers: list[str], rows: list[dict]) -> list[DetectedColumn]:
        columns = []

        for header in headers:
            values = [self._clean_value(row.get(header)) for row in rows]
            present_values = [value for value in values if value is not None]

            nullable = len(present_values) < len(values)
            column_type = self._detect_type(present_values)

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

    def _detect_type(self, values: list[str]) -> str:
        if not values:
            return "String"

        if all(self._is_int(value) for value in values):
            return "Int64"

        if all(self._is_datetime(value) for value in values):
            return "DateTime"

        if all(self._is_date(value) for value in values):
            return "Date"

        if all(self._is_float(value) for value in values):
            return "Float64"

        return "String"

    def _validate_first_rows_before_import(
        self,
        path: Path,
        delimiter: str,
        columns: list[DetectedColumn],
        row_limit: int = 5,
    ) -> dict:
        checked_rows = 0

        try:
            with path.open("r", encoding="utf-8-sig", newline="") as file:
                reader = csv.DictReader(file, delimiter=delimiter)
                original_headers = reader.fieldnames or []

                for line_number, row in enumerate(reader, start=2):
                    if checked_rows >= row_limit:
                        break

                    self._check_malformed_row(row, path, line_number, delimiter)

                    for index, column in enumerate(columns):
                        value = row.get(original_headers[index])
                        self._cast_value(value, column, line_number)

                    checked_rows += 1

            return {
                "sample_rows_checked": checked_rows,
                "needs_human_review": False,
                "review_reason": "",
            }

        except (ValueError, TypeError, KeyError) as exc:
            return {
                "sample_rows_checked": checked_rows,
                "needs_human_review": True,
                "review_reason": str(exc),
            }

    def _create_database(self, database: str) -> None:
        self.client.command(f"CREATE DATABASE IF NOT EXISTS {q_ident(database)}")

    def _create_table(self, database: str, table: str, columns: list[DetectedColumn]) -> None:
        if not columns:
            raise ValueError(f"Impossible de créer la table '{table}' : aucune colonne détectée.")
        self.client.command(self._build_create_table_sql(database, table, columns))

    def _build_create_table_sql(
        self, database: str, table: str, columns: list[DetectedColumn]
    ) -> str:
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

    def _insert_csv_rows(
        self,
        path: Path,
        database: str,
        table: str,
        columns: list[DetectedColumn],
        delimiter: str,
    ) -> int:
        column_names = [column.name for column in columns]
        total_rows = 0
        batch: list[list] = []

        with path.open("r", encoding="utf-8-sig", newline="") as file:
            reader = csv.DictReader(file, delimiter=delimiter)
            original_headers = reader.fieldnames or []

            for line_number, row in enumerate(reader, start=2):
                self._check_malformed_row(row, path, line_number, delimiter)

                batch.append(
                    [
                        self._cast_value(
                            row.get(original_headers[index]), columns[index], line_number
                        )
                        for index in range(len(columns))
                    ]
                )

                if len(batch) >= BATCH_SIZE:
                    self.client.insert(f"{database}.{table}", batch, column_names=column_names)
                    total_rows += len(batch)
                    batch = []

        if batch:
            self.client.insert(f"{database}.{table}", batch, column_names=column_names)
            total_rows += len(batch)

        return total_rows

    def _log_ingestion_result(self, result: IngestionResult) -> None:
        self.client.insert(
            f"{META_DB}.ingestion_runs",
            [
                [
                    result.source_path,
                    result.target_database,
                    result.target_table,
                    result.detected_delimiter,
                    result.row_count,
                    result.column_count,
                    result.status,
                    result.error_message,
                ]
            ],
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

    def _log_detected_columns(
        self,
        result: IngestionResult,
        columns: list[DetectedColumn],
    ) -> None:
        rows = []
        for column in columns:
            rows.append(
                [
                    result.target_database,
                    result.target_table,
                    column.name,
                    column.detected_type,
                    column.nullable,
                ]
            )

        self.client.insert(
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

    def _log_ingestion_source(self, result: IngestionResult, sample_check: dict) -> None:
        self.client.insert(
            f"{META_DB}.ingestion_sources",
            [
                [
                    result.source_path,
                    result.target_database,
                    result.target_table,
                    result.detected_delimiter,
                    sample_check["sample_rows_checked"],
                    sample_check["needs_human_review"],
                    sample_check["review_reason"],
                ]
            ],
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

    def _check_malformed_row(self, row: dict, path: Path, line_number: int, delimiter: str) -> None:
        if row.get(None):
            raise ValueError(
                f"CSV mal formé dans {path}, ligne {line_number}: colonnes en trop. "
                f"Si une décimale utilise '{delimiter}', mets la valeur entre guillemets "
                f"ou utilise un autre séparateur."
            )

    def _clean_identifier(self, value: str | None) -> str:
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

    def _dedupe_names(self, names: list[str]) -> list[str]:
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

    def _clean_value(self, value: str | None):
        if value is None:
            return None

        value = value.strip()

        if value.lower() in NULL_TOKENS:
            return None

        return value

    def _cast_value(self, value: str | None, column: DetectedColumn, line_number: int):
        value = self._clean_value(value)

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
                return self._parse_date(value)

            if base_type == "DateTime":
                return self._parse_datetime(value)

            return value

        except ValueError as exc:
            raise ValueError(
                f"Cast impossible ligne {line_number}, colonne '{column.name}', "
                f"valeur '{value}' vers {base_type}"
            ) from exc

    def _is_int(self, value: str) -> bool:
        try:
            int(value)
            return "." not in value and "," not in value
        except ValueError:
            return False

    def _is_float(self, value: str) -> bool:
        try:
            float(value.replace(",", "."))
            return True
        except ValueError:
            return False

    def _is_date(self, value: str) -> bool:
        try:
            self._parse_date(value)
            return True
        except ValueError:
            return False

    def _is_datetime(self, value: str) -> bool:
        try:
            self._parse_datetime(value)
            return True
        except ValueError:
            return False

    def _parse_date(self, value: str) -> date:
        formats = ["%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y"]

        for fmt in formats:
            try:
                if fmt == "%Y-%m-%d":
                    return date.fromisoformat(value)
                return datetime.strptime(value, fmt).date()
            except ValueError:
                pass

        raise ValueError(f"Invalid Date value: {value}")

    def _parse_datetime(self, value: str) -> datetime:
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
