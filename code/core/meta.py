from dataclasses import dataclass

from core.clickhouse_manager import CH_DB, META_DB
from core.schema import q_ident


@dataclass(frozen=True)
class StoredAdjacencyEdge:
    source_table: str
    target_table: str
    source_columns: str
    target_columns: str
    join_success_ratio: float


@dataclass(frozen=True)
class MetadataTable:
    name: str
    create_sql: str
    computed: bool
    migrations: tuple[str, ...] = ()


AGGREGATION_STABILITY_COLUMNS = (
    ("group_column", "String"),
    ("fine_sum", "Float64"),
    ("agg_sum", "Float64"),
    ("delta_sum", "Float64"),
    ("fine_count", "UInt64"),
    ("agg_count", "UInt64"),
    ("delta_count", "UInt64"),
    ("fine_avg", "Float64"),
    ("agg_avg", "Float64"),
    ("delta_avg", "Float64"),
    ("fine_min", "Float64"),
    ("agg_min", "Float64"),
    ("delta_min", "Float64"),
    ("fine_max", "Float64"),
    ("agg_max", "Float64"),
    ("delta_max", "Float64"),
)


def add_column_sql(table_name: str, column_name: str, column_type: str) -> str:
    return f"""
    ALTER TABLE {q_ident(META_DB)}.{q_ident(table_name)}
    ADD COLUMN IF NOT EXISTS {q_ident(column_name)} {column_type}
    """


METADATA_TABLES = (
    MetadataTable(
        name="ingestion_runs",
        computed=False,
        create_sql=f"""
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
        """,
    ),
    MetadataTable(
        name="ingestion_sources",
        computed=False,
        create_sql=f"""
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
        """,
    ),
    MetadataTable(
        name="detected_columns",
        computed=False,
        create_sql=f"""
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
        """,
    ),
    MetadataTable(
        name="column_profiles",
        computed=True,
        create_sql=f"""
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
        """,
    ),
    MetadataTable(
        name="primary_key_candidates",
        computed=True,
        create_sql=f"""
        CREATE TABLE IF NOT EXISTS {q_ident(META_DB)}.primary_key_candidates
        (
            database_name String,
            table_name String,
            column_name String,
            column_type String,
            rows UInt64,
            null_ratio Float64,
            uniqueness_ratio Float64,
            identifiability_score Float64,
            confidence Float64,
            reason String,
            created_at DateTime DEFAULT now()
        )
        ENGINE = MergeTree
        ORDER BY (database_name, table_name, confidence, column_name)
        """,
    ),
    MetadataTable(
        name="identifiability_scores",
        computed=True,
        create_sql=f"""
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
        """,
    ),
    MetadataTable(
        name="column_stats",
        computed=True,
        create_sql=f"""
        CREATE TABLE IF NOT EXISTS {q_ident(META_DB)}.column_stats
        (
            run_ts DateTime,
            database_name String,
            table_name String,
            column_name String,
            column_type String,
            rows UInt64,
            non_null_rows UInt64,
            distinct_count UInt64,
            entropy_ratio Float64,
            sparsity Float64,
            variation_coefficient Float64,
            skewness_score Float64
        )
        ENGINE = MergeTree
        ORDER BY (database_name, table_name, column_name, run_ts)
        """,
    ),
    MetadataTable(
        name="adjacency_edges",
        computed=True,
        create_sql=f"""
    CREATE TABLE IF NOT EXISTS {q_ident(META_DB)}.adjacency_edges
    (
        database_name String,
        source_table String,
        target_table String,
        source_columns String,
        target_columns String,
        join_success_ratio Float64,
        evidence String,
        created_at DateTime DEFAULT now()
    )
    ENGINE = MergeTree
    ORDER BY (database_name, source_table, target_table, created_at)
    """,
        migrations=(add_column_sql("adjacency_edges", "database_name", "String"),),
    ),
    MetadataTable(
        name="join_candidates",
        computed=True,
        create_sql=f"""
    CREATE TABLE IF NOT EXISTS {q_ident(META_DB)}.join_candidates
    (
        source_table String,
        source_column String,
        target_table String,
        target_column String,
        source_non_null_rows UInt64,
        matched_rows UInt64,
        join_success_ratio Float64,
        created_at DateTime DEFAULT now()
    )
    ENGINE = MergeTree
    ORDER BY (source_table, target_table, source_column, target_column, created_at)
    """,
    ),
    MetadataTable(
        name="table_roles",
        computed=True,
        create_sql=f"""
    CREATE TABLE IF NOT EXISTS {q_ident(META_DB)}.table_roles
    (
        database_name String,
        table_name String,
        row_count UInt64,
        outgoing_edges UInt64,
        incoming_edges UInt64,
        numeric_columns UInt64,
        text_columns UInt64,
        date_columns UInt64,
        has_primary_key Bool,
        role String,
        confidence Float64,
        reason String,
        created_at DateTime DEFAULT now()
    )
    ENGINE = MergeTree
    ORDER BY (database_name, table_name, created_at)
    """,
    ),
    MetadataTable(
        name="decision_model_candidates",
        computed=True,
        create_sql=f"""
    CREATE TABLE IF NOT EXISTS {q_ident(META_DB)}.decision_model_candidates
    (
        database_name String,
        model_id String,
        model_type String,
        fact_tables String,
        dimension_tables String,
        table_count UInt64,
        join_count UInt64,
        attribute_count UInt64,
        numeric_attribute_count UInt64,
        created_at DateTime DEFAULT now()
    )
    ENGINE = MergeTree
    ORDER BY (database_name, model_type, model_id, created_at)
    """,
    ),
    MetadataTable(
        name="decision_model_edges",
        computed=True,
        create_sql=f"""
    CREATE TABLE IF NOT EXISTS {q_ident(META_DB)}.decision_model_edges
    (
        database_name String,
        model_id String,
        source_table String,
        target_table String,
        source_columns String,
        target_columns String,
        join_success_ratio Float64,
        depth UInt64,
        created_at DateTime DEFAULT now()
    )
    ENGINE = MergeTree
    ORDER BY (database_name, model_id, source_table, target_table, created_at)
    """,
    ),
    MetadataTable(
        name="decision_model_scores",
        computed=True,
        create_sql=f"""
    CREATE TABLE IF NOT EXISTS {q_ident(META_DB)}.decision_model_scores
    (
        database_name String,
        model_id String,
        parsimony_score Float64,
        created_at DateTime DEFAULT now()
    )
    ENGINE = MergeTree
    ORDER BY (database_name, model_id)
    """,
    ),
    MetadataTable(
        name="decision_model_validations",
        computed=True,
        create_sql=f"""
    CREATE TABLE IF NOT EXISTS {q_ident(META_DB)}.decision_model_validations
    (
        database_name String,
        model_id String,
        is_valid Bool,
        issue_count UInt64,
        orphan_count UInt64,
        created_at DateTime DEFAULT now()
    )
    ENGINE = MergeTree
    ORDER BY (database_name, model_id, created_at)
    """,
    ),
    MetadataTable(
        name="decision_model_validation_issues",
        computed=True,
        create_sql=f"""
    CREATE TABLE IF NOT EXISTS {q_ident(META_DB)}.decision_model_validation_issues
    (
        database_name String,
        model_id String,
        rule_name String,
        severity String,
        message String,
        source_table String,
        target_table String,
        orphan_count UInt64,
        created_at DateTime DEFAULT now()
    )
    ENGINE = MergeTree
    ORDER BY (database_name, model_id, rule_name, created_at)
    """,
    ),
    MetadataTable(
        name="semantic_homogeneity",
        computed=True,
        create_sql=f"""
    CREATE TABLE IF NOT EXISTS {q_ident(META_DB)}.semantic_homogeneity
    (
        database_name String,
        table_name String,
        role String,
        is_valid Bool,
        homogeneity_score Float64,
        measure_like_columns String,
        descriptive_like_columns String,
        issue_count UInt64,
        reason String,
        created_at DateTime DEFAULT now()
    )
    ENGINE = MergeTree
    ORDER BY (database_name, table_name)
    """,
    ),
    MetadataTable(
        name="aggregation_stability",
        computed=True,
        create_sql=f"""
    CREATE TABLE IF NOT EXISTS {q_ident(META_DB)}.aggregation_stability
    (
        database_name String,
        model_id String,
        fact_table String,
        dimension_table String,
        measure_column String,
        group_column String,

        fine_sum Float64,
        agg_sum Float64,
        delta_sum Float64,

        fine_count UInt64,
        agg_count UInt64,
        delta_count UInt64,

        fine_avg Float64,
        agg_avg Float64,
        delta_avg Float64,

        fine_min Float64,
        agg_min Float64,
        delta_min Float64,

        fine_max Float64,
        agg_max Float64,
        delta_max Float64,

        is_stable Bool,
        reason String,
        created_at DateTime DEFAULT now()
    )
    ENGINE = MergeTree
    ORDER BY (database_name, model_id, fact_table, dimension_table)
    """,
        migrations=tuple(
            add_column_sql("aggregation_stability", column_name, column_type)
            for column_name, column_type in AGGREGATION_STABILITY_COLUMNS
        ),
    ),
    MetadataTable(
        name="granularity_validations",
        computed=True,
        create_sql=f"""
    CREATE TABLE IF NOT EXISTS {q_ident(META_DB)}.granularity_validations
    (
        database_name String,
        model_id String,
        fact_table String,
        grain_columns String,
        duplicate_count UInt64,
        is_valid Bool,
        reason String,
        created_at DateTime DEFAULT now()
    )
    ENGINE = MergeTree
    ORDER BY (database_name, model_id, fact_table, created_at)
    """,
    ),
    MetadataTable(
        name="model_certifications",
        computed=True,
        create_sql=f"""
    CREATE TABLE IF NOT EXISTS {q_ident(META_DB)}.model_certifications
    (
        database_name String,
        model_id String,
        status String,
        is_certified Bool,
        certification_score Float64,
        parsimony_score Float64,
        issue_count UInt64,
        created_at DateTime DEFAULT now()
    )
    ENGINE = MergeTree
    ORDER BY (database_name, model_id, created_at)
    """,
    ),
    MetadataTable(
        name="model_certification_issues",
        computed=True,
        create_sql=f"""
    CREATE TABLE IF NOT EXISTS {q_ident(META_DB)}.model_certification_issues
    (
        database_name String,
        model_id String,
        rule_name String,
        severity String,
        message String,
        table_name String,
        created_at DateTime DEFAULT now()
    )
    ENGINE = MergeTree
    ORDER BY (database_name, model_id, rule_name, created_at)
    """,
    ),
)


COMPUTED_METADATA_TABLES = tuple(table.name for table in METADATA_TABLES if table.computed)


def ensure_meta_schema(client) -> None:
    """
    Create the metadata schema used by Kawakiri.
    """

    client.command(f"CREATE DATABASE IF NOT EXISTS {q_ident(META_DB)}")

    for table in METADATA_TABLES:
        client.command(table.create_sql)

        for migration_sql in table.migrations:
            client.command(migration_sql)


def clear_computed_metadata(db) -> None:
    """
    Clear metadata tables that are recomputed by the analysis pipeline.

    Import history is preserved so source traceability remains available.
    """

    for table in COMPUTED_METADATA_TABLES:
        db.command(f"TRUNCATE TABLE IF EXISTS {q_ident(META_DB)}.{q_ident(table)}")


def clear_metadata_table(db, table_name: str) -> None:
    """
    Clear one metadata table that is recomputed by a pipeline step.
    """

    db.command(f"TRUNCATE TABLE IF EXISTS {q_ident(META_DB)}.{q_ident(table_name)}")


def load_table_role_map(db, database: str) -> dict[str, str]:
    """
    Load stored table roles as a table_name -> role mapping.
    """

    sql = f"""
    SELECT
        table_name,
        role
    FROM {q_ident(META_DB)}.table_roles
    WHERE database_name = %(database)s
    ORDER BY table_name
    """

    rows = db.query(sql, parameters={"database": database}).result_rows
    return {row[0]: row[1] for row in rows}


def load_confirmed_adjacency_edges(
    db,
    database: str = CH_DB,
) -> list[StoredAdjacencyEdge]:
    """
    Load confirmed adjacency edges from metadata.
    """

    sql = f"""
    SELECT
        source_table,
        target_table,
        source_columns,
        target_columns,
        join_success_ratio
    FROM {q_ident(META_DB)}.adjacency_edges
    WHERE database_name = %(database)s
      AND evidence = 'CONFIRMED'
    """

    rows = db.query(sql, parameters={"database": database}).result_rows

    return [
        StoredAdjacencyEdge(
            source_table=row[0],
            target_table=row[1],
            source_columns=row[2],
            target_columns=row[3],
            join_success_ratio=row[4],
        )
        for row in rows
    ]
