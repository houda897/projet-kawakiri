from __future__ import annotations

from dataclasses import dataclass

from clickhouse_connect.driver import Client

from core.client import CH_DB, META_DB
from core.schema import q_ident
from inference.primary_key import PrimaryKeyCandidate


@dataclass
class JoinPrimaryKeyCandidate:
    """
    Empirical relationship between a source column and a primary-key candidate.

    The success ratio measures the fraction of non-null source rows whose value
    is present in the target key domain.
    """

    source_table: str
    source_column: str
    target_table: str
    target_column: str
    source_non_null_rows: int
    matched_rows: int
    join_success_ratio: float


@dataclass
class SourceColumn:
    """
    Profiled column that can be evaluated as a possible foreign key.
    """

    table_name: str
    column_name: str
    column_type: str


class JoinEngine:
    """
    Evaluate physical joins between profiled columns and primary-key candidates.

    The engine does not infer primary keys itself. It receives key candidates
    from the primary-key inference step and measures empirical value coverage.
    """

    def __init__(self, client: Client):
        self.client = client

    def evaluate_join_to_primary_key(
        self,
        source_table: str,
        source_column: str,
        primary_key: PrimaryKeyCandidate,
    ) -> JoinPrimaryKeyCandidate:
        """
        Measure whether a source column is covered by a primary-key candidate.
        """

        source_ref = f"{q_ident(CH_DB)}.{q_ident(source_table)}"
        target_ref = f"{q_ident(CH_DB)}.{q_ident(primary_key.table_name)}"
        source_col = q_ident(source_column)
        target_col = q_ident(primary_key.column_name)

        sql = f"""
        WITH
            source_values AS (
                SELECT {source_col} AS value
                FROM {source_ref}
                WHERE {source_col} IS NOT NULL
            ),
            target_values AS (
                SELECT DISTINCT {target_col} AS value
                FROM {target_ref}
                WHERE {target_col} IS NOT NULL
            )
        SELECT
            count() AS source_non_null_rows,
            countIf(t.value IS NOT NULL) AS matched_rows,
            if(
                source_non_null_rows = 0,
                0.0,
                matched_rows / toFloat64(source_non_null_rows)
            ) AS join_success_ratio
        FROM source_values AS s
        LEFT JOIN target_values AS t
            ON s.value = t.value
        """

        row = self.client.query(sql).result_rows[0]

        return JoinPrimaryKeyCandidate(
            source_table=source_table,
            source_column=source_column,
            target_table=primary_key.table_name,
            target_column=primary_key.column_name,
            source_non_null_rows=row[0],
            matched_rows=row[1],
            join_success_ratio=round(row[2], 6),
        )

    def evaluate_join_by_target(
        self,
        source_table: str,
        source_column: str,
        target_table: str,
        target_column: str,
        primary_keys: list[PrimaryKeyCandidate],
    ) -> JoinPrimaryKeyCandidate:
        """
        Resolve a named target key and evaluate source-column coverage.
        """

        primary_key = self.find_primary_key(
            primary_keys=primary_keys,
            target_table=target_table,
            target_column=target_column,
        )

        return self.evaluate_join_to_primary_key(
            source_table=source_table,
            source_column=source_column,
            primary_key=primary_key,
        )

    def find_primary_key(
        self,
        primary_keys: list[PrimaryKeyCandidate],
        target_table: str,
        target_column: str,
    ) -> PrimaryKeyCandidate:
        """
        Find a primary-key candidate by table and column name.
        """

        for primary_key in primary_keys:
            if primary_key.table_name == target_table and primary_key.column_name == target_column:
                return primary_key

        raise ValueError(
            f"No primary-key candidate found for {target_table}.{target_column}. "
            "Run profiling and primary-key inference first."
        )

    def load_source_columns(self) -> list[SourceColumn]:
        """
        Load profiled columns that can provide evidence for a relationship.
        """

        sql = f"""
        SELECT
            table_name,
            column_name,
            column_type
        FROM {q_ident(META_DB)}.column_profiles
        WHERE null_ratio < 1
          AND NOT startsWith(column_name, '__')
        ORDER BY table_name, column_name
        """

        rows = self.client.query(sql).result_rows

        return [
            SourceColumn(
                table_name=row[0],
                column_name=row[1],
                column_type=row[2],
            )
            for row in rows
        ]

    def evaluate_candidates(
        self,
        primary_keys: list[PrimaryKeyCandidate],
        min_success_ratio: float = 0.95,
    ) -> list[JoinPrimaryKeyCandidate]:
        """
        Evaluate all type-compatible source columns against primary-key candidates.
        """

        source_columns = self.load_source_columns()
        candidates = []

        for source in source_columns:
            for primary_key in primary_keys:
                if self.should_skip_pair(source, primary_key):
                    continue

                result = self.evaluate_join_to_primary_key(
                    source_table=source.table_name,
                    source_column=source.column_name,
                    primary_key=primary_key,
                )

                if result.join_success_ratio >= min_success_ratio:
                    candidates.append(result)

        return candidates

    @staticmethod
    def should_skip_pair(
        source: SourceColumn,
        primary_key: PrimaryKeyCandidate,
    ) -> bool:
        """
        Exclude pairs that cannot represent a foreign-key to primary-key relation.
        """

        same_table = source.table_name == primary_key.table_name
        incompatible_type = source.column_type != primary_key.column_type

        return same_table or incompatible_type

    @staticmethod
    def print_result(result: JoinPrimaryKeyCandidate) -> None:
        """
        Print one join evaluation result.
        """

        print(
            f"{result.source_table}.{result.source_column} -> "
            f"{result.target_table}.{result.target_column}"
        )
        print(f"Source non-null rows : {result.source_non_null_rows}")
        print(f"Matched rows         : {result.matched_rows}")
        print(f"Join success ratio   : {result.join_success_ratio}")

    @staticmethod
    def print_candidates(candidates: list[JoinPrimaryKeyCandidate]) -> None:
        """
        Print inferred join candidates.
        """

        if not candidates:
            print("No join candidates found.")
            return

        for candidate in candidates:
            print(
                f"{candidate.source_table}.{candidate.source_column} -> "
                f"{candidate.target_table}.{candidate.target_column} | "
                f"ratio={candidate.join_success_ratio}"
            )
