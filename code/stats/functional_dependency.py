from __future__ import annotations

from typing import TYPE_CHECKING

from core.clickhouse_manager import clickhouse_manager
from core.logger import get_logger

if TYPE_CHECKING:
    from inference.primary_key import PrimaryKeyCandidate

logger = get_logger(__name__)

def check_functional_dependency(database: str, table: str, pk_candidate: str | list[str], db_manager: clickhouse_manager) -> bool:
    '''
    Check if the given candidate (single column or composite) satisfies the functional dependency by ensuring no duplicates exist.
    '''
    q_table = f"`{database}`.`{table}`"

    if isinstance(pk_candidate, list):
        q_cols = ", ".join("`"+col+"`" for col in pk_candidate)
    else:
        q_cols = f"`{pk_candidate}`"

    query_check = f"""
    WITH key_research AS (
        SELECT cityHash64({q_cols}) AS col_hash
        FROM {q_table}
    )
    SELECT count(1), col_hash
    FROM key_research
    GROUP BY col_hash
    HAVING count(1) > 1
    """

    result = db_manager.query(query_check)

    return len(result.result_rows) == 0

def validate_dependency(candidates_list: list[PrimaryKeyCandidate]) -> list[PrimaryKeyCandidate]:
    new_candidates = candidates_list.copy()
    logger.info(f"Validating functional dependencies for {len(candidates_list)} candidates...")
    db_manager = clickhouse_manager()

    for candidate in candidates_list:

        is_valid = check_functional_dependency(candidate.database_name, candidate.table_name, candidate.column_name, db_manager)

        if not is_valid:
            #logger.info(f"Candidate {candidate.column_name} in {candidate.table_name} is not a valid primary key : X")
            new_candidates.remove(candidate)
        else:
            #logger.info(f"Candidate {candidate.column_name} in {candidate.table_name} is a valid primary key : O")
            continue
    logger.info(f"Keys removed : {len(candidates_list) - len(new_candidates)}")
    return new_candidates
