from __future__ import annotations

from dataclasses import asdict, dataclass

from core.client import CH_DB, META_DB
from core.meta import ensure_meta_schema
from core.schema import Col, list_columns, list_tables, q_ident


@dataclass
class ColumnProfile:
    """
    Profil statistique d'une colonne ClickHouse.

    Stocke les métriques de complétude, cardinalité, unicité et valeurs
    limites utilisées par les étapes d'inférence aval (détection de clés,
    séparation faits/dimensions).
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
    def __init__(self, client):
        self.client = client

    def compute_basic_profile_for_column(self, table: str, col: Col) -> ColumnProfile:
        """
        Compute the core profiling metrics for one ClickHouse column.
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
        row = self.client.query(sql).result_rows[0]

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
        Persist computed column profiles in the metadata database.
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

        self.client.insert(
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
        ensure_meta_schema(self.client)

        profiles = []

        for table in list_tables(self.client):
            for col in list_columns(self.client, table):
                if col.name.startswith("__"):
                    continue

                profiles.append(self.compute_basic_profile_for_column(table, col))

        self.insert_column_profiles(profiles)
        return profiles


def profiles_to_dicts(profiles: list[ColumnProfile]) -> list[dict]:
    """
    Convert profile objects to dictionaries for tests or serialization.
    """
    return [asdict(profile) for profile in profiles]
