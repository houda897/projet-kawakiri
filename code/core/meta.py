from core.manager import META_DB
from core.schema import q_ident


def ensure_meta_schema(client) -> None:
    """
    Create the metadata schema used by Kawakiri.

    This function initializes the metadata database and the tables required to
    trace CSV ingestion, store source-level diagnostics, preserve inferred
    column schemas, and persist column profiling results. These tables make the
    ingestion and profiling pipeline reproducible and auditable across runs.
    """

    client.command(f"CREATE DATABASE IF NOT EXISTS {q_ident(META_DB)}")

    # Store one row per ingestion attempt, including status and error message.
    client.command(f"""
        CREATE TABLE IF NOT EXISTS {q_ident(META_DB)}.ingestion_runs
        (
            source_path String,
            target_database String,
            target_table String,
            detected_delimiter String,
            row_count UInt64,
            column_count UInt64,
            status LowCardinality(String),
            error_message String,
            created_at DateTime DEFAULT now()
        )
        ENGINE = MergeTree
        ORDER BY (created_at, target_database, target_table)
        """)

    # Store source-level diagnostics and whether human review is required.
    client.command(f"""
        CREATE TABLE IF NOT EXISTS {q_ident(META_DB)}.ingestion_sources
        (
            run_id String,
            source_path String,
            target_database String,
            target_table String,
            detected_delimiter String,
            sample_rows_checked UInt64,
            needs_human_review Bool,
            review_reason String,
            created_at DateTime DEFAULT now()
        )
        ENGINE = MergeTree
        ORDER BY (created_at, target_database, target_table)
        """)

    # Store inferred column metadata.
    client.command(f"""
        CREATE TABLE IF NOT EXISTS {q_ident(META_DB)}.detected_columns
        (
            run_id String,
            target_database String,
            target_table String,
            column_name String,
            detected_type String,
            nullable Bool,
            created_at DateTime DEFAULT now()
        )
        ENGINE = MergeTree
        ORDER BY (run_id, target_database, target_table, column_name)
        """)

    # Store column profiling results for each column.
    client.command(f"""
        CREATE TABLE IF NOT EXISTS {q_ident(META_DB)}.column_profiles
        (
            database_name String,
            table_name String,
            column_name String,
            column_type String,
            rows UInt64,
            non_null_rows UInt64,
            null_rows UInt64,
            null_ratio Float64,
            distinct_count UInt64,
            uniqueness_ratio Float64,
            min_value String,
            max_value String,
            profiled_at DateTime DEFAULT now()
        )
        ENGINE = MergeTree
        ORDER BY (database_name, table_name, column_name, profiled_at)
        """)
    # Store mathematically inferred simple primary-key candidates.
    client.command(f"""
        CREATE TABLE IF NOT EXISTS {q_ident(META_DB)}.primary_key_candidates
        (
            database_name String,
            table_name String,
            column_name String,
            column_type String,
            rows UInt64,
            null_ratio Float64,
            uniqueness_ratio Float64,
            confidence Float64,
            reason String,
            created_at DateTime DEFAULT now()
        )
        ENGINE = MergeTree
        ORDER BY (database_name, table_name, confidence, column_name)
        """)
    client.command(
        f"""
        CREATE TABLE IF NOT EXISTS {q_ident(META_DB)}.identifiability_scores
        (
            database_name String,
            table_name String,
            column_name String,
            uniqueness_ratio Float64,
            entropy_ratio Float64,
            completeness Float64,
            identifiability_score Float64,
            diagnostic String,
            created_at DateTime DEFAULT now()
        )
        ENGINE = MergeTree
        ORDER BY (database_name, table_name, column_name, created_at)
        """
    )


