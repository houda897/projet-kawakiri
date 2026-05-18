from core.client import CH_DB, META_DB
from core.meta import ensure_meta_schema
from core.schema import Col, list_columns, list_tables, q_ident


# Calcule les statistiques de base d'une colonne ClickHouse.
def compute_basic_profile_for_column(client, table: str, col: Col) -> dict:
    """
    Compute the core profiling metrics for one ClickHouse column.

    The profile captures row counts, null density, cardinality, uniqueness, and
    boundary values. These metrics provide the statistical foundation used by
    later inference steps, such as candidate key detection and fact/dimension
    separation.
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
    row = client.query(sql).result_rows[0]

    return {
        "database_name": CH_DB,
        "table_name": table,
        "column_name": col.name,
        "column_type": col.ch_type,
        "rows": row[0],
        "non_null_rows": row[1],
        "null_rows": row[2],
        "null_ratio": round(row[3], 6),
        "distinct_count": row[4],
        "uniqueness_ratio": round(row[5], 6),
        "min_value": row[6],
        "max_value": row[7],
    }


# Insère les profils de colonnes dans lab_meta.column_profiles.
def insert_column_profiles(client, profiles: list[dict]) -> None:
    """
    Persist computed column profiles in the metadata database.

    Storing these metrics makes profiling results reusable by downstream stages
    and supports reproducibility across independent runs of the inference
    pipeline.
    """
    if not profiles:
        return

    rows = [
        [
            profile["database_name"],
            profile["table_name"],
            profile["column_name"],
            profile["column_type"],
            profile["rows"],
            profile["non_null_rows"],
            profile["null_rows"],
            profile["null_ratio"],
            profile["distinct_count"],
            profile["uniqueness_ratio"],
            profile["min_value"],
            profile["max_value"],
        ]
        for profile in profiles
    ]

    client.insert(
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

                                                                                                           
# Parcourt toutes les tables et colonnes de la base puis stocke leurs profils.
def profile_database(client) -> list[dict]:
    """
    Profile all regular columns in the configured ClickHouse database.

    The function iterates over available tables and columns, skips technical
    columns, computes basic profiles, and stores the resulting metrics in the
    metadata schema for later model inference.
    """
    ensure_meta_schema(client)

    profiles = []

    for table in list_tables(client):
        for col in list_columns(client, table):
            if col.name.startswith("__"):
                continue

            profiles.append(compute_basic_profile_for_column(client, table, col))

    insert_column_profiles(client, profiles)
    return profiles
