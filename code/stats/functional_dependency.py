import os
import pandas as pd
import itertools
from core.manager import ClickHouseManager
from core.schema import q_ident
from core.logger import get_logger


logger = get_logger(__name__)

def check_functional_dependency(database, table, col_A, col_B, limit_violations: int = 5) -> dict:
    """
    Analyse si l'attribut B dépend fonctionnellement de l'attribut A (A -> B).
    
    Méthode : Recherche de contre-exemples (GROUP BY A HAVING uniqExact(B) > 1).
    
    Retourne un dictionnaire avec :
    - 'is_valid': True si la dépendance est respectée, False sinon.
    - 'violations': Un DataFrame Pandas contenant les contre-exemples (si existants).
    - 'message': Un résumé textuel du diagnostic.
    """
    # Use proper quoting for identifiers
    q_table = f"{q_ident(database)}.{q_ident(table)}"
    q_A = q_ident(col_A)
    q_B = q_ident(col_B)
    
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
    
    try:
        # Récupération du manager existant (Singleton)
        db_manager = ClickHouseManager.get_instance()
        df_violations = db_manager.query_df(query)
        
        if df_violations.empty:
            return {
                "is_valid": True,
                "violations": pd.DataFrame(),
                "message": f"✅ Dépendance prouvée : {col_A} -> {col_B}. Chaque valeur de '{col_A}' détermine de manière unique la valeur de '{col_B}'."
            }
        else:
            return {
                "is_valid": False,
                "violations": df_violations,
                "message": f"❌ Dépendance violée : {col_A} -> {col_B}. Des valeurs de '{col_A}' sont associées à plusieurs valeurs de '{col_B}' distinctes."
            }
            
    except Exception as e:
        logger.error("Erreur lors de l'analyse de dépendance entre %s et %s: %s", col_A, col_B, e)
        return {
            "is_valid": False,
            "violations": pd.DataFrame(),
            "message": f"Erreur technique lors de l'exécution de la requête : {e}"
        }
    
def analyze_table_dependencies(database: str, table: str) -> dict:
    """
    Récupère toutes les colonnes d'une table, teste toutes les paires de dépendances 
    fonctionnelles possibles (A -> B) et retourne les résultats dans un dictionnaire.
    """
    db_manager = ClickHouseManager.get_instance()
    
    # 1. Requête pour récupérer proprement le nom de toutes les colonnes de la table
    columns_query = f"""
    SELECT name 
    FROM system.columns 
    WHERE database = '{database}' AND table = '{table}'
    """
    
    try:
        df_cols = db_manager.query_df(columns_query)
        if df_cols.empty:
            logger.info("Aucune colonne trouvée pour la table %s.%s", database, table)
            return {}

        columns = df_cols['name'].tolist()
        logger.info("Colonnes détectées (%s) : %s", len(columns), columns)

    except Exception as e:
        logger.error("Impossible de récupérer les colonnes de la table : %s", e)
        return {}

    # 2. Générer toutes les paires de colonnes ordonnées (Permutations de taille 2)
    # Si on a [col1, col2], itertools.permutations génère (col1, col2) ET (col2, col1)
    all_pairs = list(itertools.permutations(columns, 2))
    logger.info("Nombre total de dépendances à tester : %s", len(all_pairs))

    global_results = {}

    # 3. Boucler sur toutes les paires et stocker le résultat
    for col_A, col_B in all_pairs:
        pair_key = f"{col_A} -> {col_B}"
        
        # Exécution du test pour la paire actuelle
        result = check_functional_dependency(database, table, col_A, col_B)
        
        global_results[pair_key] = result

    return global_results