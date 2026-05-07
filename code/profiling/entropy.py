from core.client import CH_DB
from core.schema import Col, q_ident


def compute_entropy_for_column(client, table: str, col: Col) -> dict:
    table_ref = f"{q_ident(CH_DB)}.{q_ident(table)}"
    col_ref = q_ident(col.name)

    sql = f"""
    WITH
      base AS (
        SELECT
          count() AS rows,
          countIf({col_ref} IS NOT NULL) AS non_null_rows,
          uniqExact({col_ref}) AS distinct_count
        FROM {table_ref}
      ),
      freqs AS (
        SELECT
          toString({col_ref}) AS v,
          count() AS c
        FROM {table_ref}
        WHERE {col_ref} IS NOT NULL
        GROUP BY v
      ),
      entropy_calc AS (
        SELECT
          if(
            (SELECT non_null_rows FROM base) = 0,
            0.0,
            sum(
              -1.0
              * (c / toFloat64((SELECT non_null_rows FROM base)))
              * log2(c / toFloat64((SELECT non_null_rows FROM base)))
            )
          ) AS entropy
        FROM freqs
      )
    SELECT
      base.rows,
      base.non_null_rows,
      base.distinct_count,
      entropy_calc.entropy
    FROM base
    CROSS JOIN entropy_calc
    """

    row = client.query(sql).result_rows[0]

    return {
        "db": CH_DB,
        "table": table,
        "column": col.name,
        "ch_type": col.ch_type,
        "rows": row[0],
        "non_null_rows": row[1],
        "distinct_count": row[2],
        "entropy": row[3] or 0.0,
    }
#modifications apportée
#table qualifiée avec CH_DB.table
#une ligne retournée même si la colonne est vide ou full NULL
#distinct_count calculé proprement avec uniqExact
#division forcée en Float64
#entropy sécurisé avec row[3] or 0.0
# from core.client import CH_DB
# from core.schema import Col, q_ident
#
# def compute_entropy_for_column(client, table: str, col: Col) -> dict:
#     sql = f"""
#     WITH
#       base AS (
#         SELECT
#           count() AS rows,
#           countIf({q_ident(col.name)} IS NOT NULL) AS non_null_rows
#         FROM {q_ident(table)}
#       ),
#       freqs AS (
#         SELECT
#           toString({q_ident(col.name)}) AS v,
#           count() AS c
#         FROM {q_ident(table)}
#         WHERE {q_ident(col.name)} IS NOT NULL
#         GROUP BY v
#       ),
#       tot AS (
#         SELECT sum(c) AS n FROM freqs
#       ),
#       probs AS (
#         SELECT
#           c,
#           (c / n) AS p,
#           n
#         FROM freqs
#         CROSS JOIN tot
#       )
#     SELECT
#       (SELECT rows FROM base) AS rows,
#       (SELECT non_null_rows FROM base) AS non_null_rows,
#       toUInt64(count()) AS distinct_count,
#       if(max(n)=0, 0.0, -sum(p * log2(p))) AS entropy
#     FROM probs
#     """
#     row = client.query(sql).result_rows[0]
#
#     return {
#         "db": CH_DB,
#         "table": table,
#         "column": col.name,
#         "ch_type": col.ch_type,
#         "rows": row[0],
#         "non_null_rows": row[1],
#         "distinct_count": row[2],
#         "entropy": row[3],
#     }
#     