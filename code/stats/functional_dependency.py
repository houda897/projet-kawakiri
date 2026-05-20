from core.clickhouse_manager import clickhouse_manager
from core.logger import get_logger
from stats.identifiability import *
from inference.primary_key import PrimaryKeyCandidate
from tqdm import tqdm


logger = get_logger(__name__)

def check_functional_dependency(database, table, col_A, col_B, limit_violations: int = 1):
    '''Analyse if there is a dependency from column A to column B (A -> B)'''
    q_table = f"`{database}`.`{table}`"
    q_A = f"`{col_A}`"
    q_B = f"`{col_B}`"
    
    query_check = f"""
    SELECT 
        {q_A} AS valeur_A, 
        uniqExact({q_B}) AS nb_valeurs_B_differentes
    FROM {q_table}
    GROUP BY valeur_A
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

def analyze_table_dependencies(database, table, col_name) :
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
        is_valid = analyze_table_dependencies(candidate.database_name, candidate.table_name, candidate.column_name)
        if not is_valid:
            #logger.info(f"Candidate {candidate.column_name} in {candidate.table_name} is not a valid primary key.")
            new_candidates.remove(candidate)
        else:
            #logger.info(f"Candidate {candidate.column_name} in {candidate.table_name} is a valid primary key.")
            continue
    logger.info(f"Keys removed : {len(candidates_list) - len(new_candidates)}")
    return new_candidates