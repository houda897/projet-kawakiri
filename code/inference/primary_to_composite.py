from __future__ import annotations

from core.clickhouse_manager import META_DB, clickhouse_manager
from core.logger import get_logger
from core.schema import q_ident
from config.scoring import PK_WEIGHTS
from inference.key_ranking import RankedKeyCandidate

logger = get_logger(__name__)


def process_composite_candidates(
    db: clickhouse_manager,
    simple_candidates: list[RankedKeyCandidate],
    composite_engine,
    low_cardinality_columns: set[tuple[str, str]],
) -> list[RankedKeyCandidate]:
    """
    Add composite-key candidates only for tables without a simple primary key.
    """

    all_columns = fetch_candidate_columns(db)

    tables_with_simple_pk = {
        candidate.table_name
        for candidate in simple_candidates
    }

    all_tables = {
        candidate.table_name
        for candidate in all_columns
    }

    tables_without_pk = sorted(all_tables - tables_with_simple_pk)

    logger.info("Simple primary-key candidates: %s", len(simple_candidates))
    logger.info("Tables without simple primary key: %s", tables_without_pk)

    if not tables_without_pk:
        return simple_candidates

    composite_candidates = composite_engine.generate_composite_candidates(
        all_columns=all_columns,
        tables_without_pk=tables_without_pk,
        low_cardinality_columns=low_cardinality_columns,
    )

    return simple_candidates + composite_candidates


def fetch_candidate_columns(db: clickhouse_manager):
    """
    Load column evidence used by the composite-key search.
    """

    from inference.primary_key import PrimaryKeyCandidate

    sql = f"""
    SELECT
        p.database_name,
        p.table_name,
        p.column_name,
        p.column_type,
        p.rows,
        p.null_ratio,
        p.uniqueness_ratio,
        coalesce(i.identifiability_score, 0.0) AS identifiability_score
    FROM {q_ident(META_DB)}.column_profiles AS p
    LEFT JOIN {q_ident(META_DB)}.identifiability_scores AS i
        ON p.database_name = i.database_name
       AND p.table_name = i.table_name
       AND p.column_name = i.column_name
    WHERE p.null_ratio <= 0.000001
      AND NOT startsWith(p.column_name, '__')
    ORDER BY p.table_name, p.column_name
    """

    rows = db.query(sql).result_rows
    candidates = []

    for row in rows:
        confidence = round(
            PK_WEIGHTS["uniqueness"] * row[6]
            + PK_WEIGHTS["identifiability"] * row[7],
            6,
        )

        candidates.append(
            PrimaryKeyCandidate(
                database_name=row[0],
                table_name=row[1],
                column_name=row[2],
                column_type=row[3],
                rows=row[4],
                null_ratio=row[5],
                uniqueness_ratio=row[6],
                identifiability_score=row[7],
                confidence=confidence,
                reason="column_evidence_for_composite_key_search",
            )
        )

    return candidates
