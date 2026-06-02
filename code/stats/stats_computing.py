from __future__ import annotations

from core.clickhouse_manager import META_DB, clickhouse_manager
from core.schema import Col, is_numeric_type, q_ident


def compute_column_stats(
    db: clickhouse_manager,
    run_ts: str,
    database: str,
    table: str,
    col: Col,
) -> None:
    """
    Compute advanced metrics for one column and store them in metadata.

    Entropy estimates information spread, sparsity measures missingness, and
    the numerical indicators describe dispersion and asymmetry when applicable.
    """

    is_numeric = is_numeric_type(col.ch_type)
    col_ref = q_ident(col.name)
    table_ref = f"{q_ident(database)}.{q_ident(table)}"

    if is_numeric:
        numeric_metrics = f"""
            avg({col_ref}) AS avg_value,
            stddevPop({col_ref}) AS std_value,
            skewPop({col_ref}) AS skew_value
        """
        variation_expr = """
            if(
                avg_value != 0,
                abs(std_value / avg_value) / (1 + abs(std_value / avg_value)),
                0.0
            )
        """
        skewness_expr = "abs(skew_value) / (1 + abs(skew_value))"
    else:
        numeric_metrics = """
            0.0 AS avg_value,
            0.0 AS std_value,
            0.0 AS skew_value
        """
        variation_expr = "0.0"
        skewness_expr = "0.0"

    sql = f"""
    INSERT INTO {q_ident(META_DB)}.column_stats
    (
        run_ts,
        database_name,
        table_name,
        column_name,
        column_type,
        rows,
        non_null_rows,
        distinct_count,
        entropy_ratio,
        sparsity,
        variation_coefficient,
        skewness_score
    )
    WITH
        base AS (
            SELECT
                count() AS total_rows,
                countIf({col_ref} IS NOT NULL) AS non_null_rows,
                {numeric_metrics}
            FROM {table_ref}
        ),
        freqs AS (
            SELECT
                toString({col_ref}) AS value,
                count() AS frequency
            FROM {table_ref}
            WHERE {col_ref} IS NOT NULL
            GROUP BY value
        ),
        probs AS (
            SELECT
                frequency,
                frequency / toFloat64((SELECT non_null_rows FROM base)) AS probability
            FROM freqs
        )
    SELECT
        toDateTime(%(run_ts)s) AS run_ts,
        %(database)s AS database_name,
        %(table)s AS table_name,
        %(column)s AS column_name,
        %(column_type)s AS column_type,
        (SELECT total_rows FROM base) AS rows,
        (SELECT non_null_rows FROM base) AS non_null_rows,
        toUInt64(count()) AS distinct_count,
        if(
            (SELECT non_null_rows FROM base) > 1,
            -sum(probability * log2(probability)) / log2((SELECT non_null_rows FROM base)),
            0.0
        ) AS entropy_ratio,
        (SELECT if(total_rows > 0, 1 - (non_null_rows / total_rows), 0.0) FROM base) AS sparsity,
        (SELECT {variation_expr} FROM base) AS variation_coefficient,
        (SELECT {skewness_expr} FROM base) AS skewness_score
    FROM probs
    """

    db.command(
        sql,
        parameters={
            "run_ts": run_ts,
            "database": database,
            "table": table,
            "column": col.name,
            "column_type": col.ch_type,
        },
    )
