from __future__ import annotations

import datetime
from dataclasses import dataclass

from core.clickhouse_manager import CH_DB, META_DB
from core.logger import get_logger
from core.meta import clear_computed_metadata, ensure_meta_schema
from core.schema import Col, list_columns, list_tables, q_ident
from stats.stats_computing import compute_column_stats

logger = get_logger(__name__)


@dataclass
class ColumnProfile:
    """
    Statistical profile of a ClickHouse column.

    Stores completeness, cardinality, uniqueness, and boundary metrics used
    by downstream inference steps (key detection, fact/dimension separation).
    """

    database_name: str
    table_name: str
    column_name: str
    column_type: str
    rows: int
    non_null_rows: int
    null_rows: int
    null_ratio: float
    distinct_count: int
    uniqueness_ratio: float
    min_value: str
    max_value: str


class ProfileEngine:
    """
    Compute and store basic column profiles for all tables in the configured database.

    A profile captures completeness, cardinality, uniqueness, and value range for
    each column. These metrics feed the identifiability scoring and primary-key
    inference steps.
    """

    def __init__(self, db):
        self.db = db

    def compute_basic_profile_for_column(self, table: str, col: Col) -> ColumnProfile:
        """
        Run a single SQL query to collect row counts, null counts, distinct counts,
        and boundary values for one column.

        All ratios are rounded to 6 decimal places before being returned.
        """
        table_ref = f"{q_ident(CH_DB)}.{q_ident(table)}"
        col_ref = q_ident(col.name)

        sql = f"""
        SELECT
          count() AS rows,
          countIf({col_ref} IS NOT NULL) AS non_null_rows,
          countIf({col_ref} IS NULL) AS null_rows,
          if(rows = 0, 0.0, null_rows / toFloat64(rows)) AS null_ratio,
          uniqExact({col_ref}) AS distinct_count,
          if(non_null_rows = 0, 0.0, distinct_count / toFloat64(non_null_rows)) AS uniqueness_ratio,
          if(non_null_rows = 0, '', toString(min({col_ref}))) AS min_value,
          if(non_null_rows = 0, '', toString(max({col_ref}))) AS max_value
        FROM {table_ref}
        """

        row = self.db.query(sql).result_rows[0]

        return ColumnProfile(
            database_name=CH_DB,
            table_name=table,
            column_name=col.name,
            column_type=col.ch_type,
            rows=row[0],
            non_null_rows=row[1],
            null_rows=row[2],
            null_ratio=round(row[3], 6),
            distinct_count=row[4],
            uniqueness_ratio=round(row[5], 6),
            min_value=row[6],
            max_value=row[7],
        )

    def insert_column_profiles(self, profiles: list[ColumnProfile]) -> None:
        """
        Persist a batch of column profiles into the metadata table.

        Does nothing if the list is empty, so callers do not need to guard
        against empty batches.
        """
        if not profiles:
            return

        rows = [
            [
                profile.database_name,
                profile.table_name,
                profile.column_name,
                profile.column_type,
                profile.rows,
                profile.non_null_rows,
                profile.null_rows,
                profile.null_ratio,
                profile.distinct_count,
                profile.uniqueness_ratio,
                profile.min_value,
                profile.max_value,
            ]
            for profile in profiles
        ]

        self.db.insert(
            f"{META_DB}.column_profiles",
            rows,
            column_names=[
                "database_name",
                "table_name",
                "column_name",
                "column_type",
                "rows",
                "non_null_rows",
                "null_rows",
                "null_ratio",
                "distinct_count",
                "uniqueness_ratio",
                "min_value",
                "max_value",
            ],
        )

    def profile_database(self) -> list[ColumnProfile]:
        """
        Profile all regular columns in the configured ClickHouse database.
        """

        ensure_meta_schema(self.db)
        clear_computed_metadata(self.db)

        profiles = []
        run_ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        for table in list_tables(self.db):
            for col in list_columns(self.db, table):
                if col.name.startswith("__"):
                    continue

                profiles.append(self.compute_basic_profile_for_column(table, col))

                try:
                    compute_column_stats(
                        db=self.db,
                        run_ts=run_ts,
                        database=CH_DB,
                        table=table,
                        col=col,
                    )
                except Exception as exc:
                    logger.warning(
                        "Failed to compute advanced stats for %s.%s: %s",
                        table,
                        col.name,
                        exc,
                    )

        self.insert_column_profiles(profiles)
        return profiles

