import os
import pandas as pd
from core.clickhouse_manager import clickhouse_manager
from core.logger import get_logger
from stats.identifiability import *


logger = get_logger(__name__)

def check_functional_dependency(database, table, col_A, col_B, limit_violations: int = 2):
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