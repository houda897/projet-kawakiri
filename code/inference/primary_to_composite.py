from inference.primary_key import PrimaryKeyCandidate
from core.clickhouse_manager import META_DB
from stats.functional_dependency import validate_dependency
from core.logger import get_logger

logger = get_logger(__name__)

def process_composite_candidates(db, pk_engine, composite_engine):
    all_candidates = fetch_identifiability_scores(db)

    simple_candidates = pk_engine.infer_candidates()
    logger.info(f"Simple candidates inferred: {len(simple_candidates)}")

    if simple_candidates:
        final_candidates = validate_dependency(simple_candidates)
    else:
        final_candidates = []

    table_with_simple_pk = set(c.table_name for c in final_candidates)
    for t in table_with_simple_pk:
        logger.info(f"Table with simple PK: {t}")

    all_tables = set(c.table_name for c in all_candidates)
    tables_without_pk = list(all_tables - table_with_simple_pk)
    for t in tables_without_pk:
        logger.info(f"Table without simple PK: {t}")

    logger.info(f"Generating composite candidates for {len(tables_without_pk)} tables without simple PK...")
    composite_candidates = []
    if tables_without_pk:
        composite_candidates = composite_engine.generate_composite_candidates(
            all_columns=all_candidates,
            tables_without_pk=tables_without_pk
        )
    
    final_candidates += composite_candidates

    return final_candidates


def fetch_identifiability_scores(db) -> list[PrimaryKeyCandidate]:
    """
    Récupère directement les colonnes depuis identifiability_scores.
    Requête simple et rapide sans jointure.
    """
    sql = f"""
    SELECT
        database_name,
        table_name,
        column_name,
        uniqueness_ratio,
        entropy_ratio,
        identifiability_score,
        -- On recalcule la confidence à la volée
        round((0.7 * uniqueness_ratio) + (0.3 * identifiability_score), 6) AS confidence
    FROM {META_DB}.identifiability_scores
    """
    
    rows = db.query(sql).result_rows
    
    all_candidates = []
    for row in rows:
        all_candidates.append(
            PrimaryKeyCandidate(
                database_name=row[0],
                table_name=row[1],
                column_name=row[2],
                column_type="Unknown", 
                rows=0,                
                null_ratio=0.0,        
                uniqueness_ratio=row[3],
                identifiability_score=row[5],
                confidence=row[6],
                reason="Fetched directly from identifiability_scores"
            )
        )
        
    return all_candidates