from core.clickhouse_manager import clickhouse_manager
from core.logger import get_logger
from stats.identifiability import *
from inference.primary_key import PrimaryKeyCandidate
from tqdm import tqdm


logger = get_logger(__name__)

def check_functional_dependency(database, table, col_A: str | list[str], col_B, limit_violations: int = 1) -> bool:
    '''
    Analyse if there is a dependency from column A to column B (A -> B)
    Column A can be a list of columns (composite key candidate)
    '''
    q_table = f"`{database}`.`{table}`"
    q_B = f"`{col_B}`"

    if isinstance(col_A, list):
        q_A_select = ", ".join(f"`{c}`" for c in col_A)
        q_A_group = ", ".join(f"`{c}`" for c in col_A)
    else:
        q_A_select = f"`{col_A}` AS valeur_A"
        q_A_group = "`valeur_A`"
    query_check = f"""
    SELECT 
        {q_A_select} AS valeur_A, 
        uniqExact({q_B}) AS nb_valeurs_B_differentes
    FROM {q_table}
    GROUP BY {q_A_group}
    HAVING nb_valeurs_B_differentes > 1
    ORDER BY nb_valeurs_B_differentes DESC
    LIMIT {limit_violations}
    """

    db_manager = clickhouse_manager()
    df_violations = db_manager.queryDf(query_check)
        
    if df_violations.empty:
        return True
    else:
        return False

def analyze_table_dependencies(database, table, col_name : str | list[str]) -> bool:
    '''
    Get a column name that is PK candidate and loop on check_functional_dependency
    to check if there is a dependency from this column to every other ones
    '''
    
    all_columns = get_columns_name(database, table)
    other_columns = [col for col in all_columns if col != col_name]
    

    for target_column in other_columns :
        if check_functional_dependency(database, table, col_name, target_column) :
            #print("OK")
            continue
        else :
            #print("NOT OK")
            return False

    return True

def validate_dependency(candidates_list: list[PrimaryKeyCandidate]) -> list[PrimaryKeyCandidate]:
    new_candidates = candidates_list.copy()
    logger.info(f"Validating functional dependencies for {len(candidates_list)} candidates...")

    for candidate in candidates_list:

        cols_to_test = candidate.column_name.split(", ") if isinstance(candidate.column_name, str) else candidate.column_name

        is_valid = analyze_table_dependencies(candidate.database_name, candidate.table_name, cols_to_test)

        if not is_valid:
            #logger.info(f"Candidate {candidate.column_name} in {candidate.table_name} is not a valid primary key : X")
            new_candidates.remove(candidate)
        else:
            #logger.info(f"Candidate {candidate.column_name} in {candidate.table_name} is a valid primary key : O")
            continue
    logger.info(f"Keys removed : {len(candidates_list) - len(new_candidates)}")
    return new_candidates