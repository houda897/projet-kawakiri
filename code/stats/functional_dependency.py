import os
import pandas as pd
import itertools
from .clickhouse_manager import clickhouse_manager

def check_functional_dependency(database, table, col_A, col_B, limit_violations: int = 5) -> dict:
    """
    Analyse si l'attribut B dépend fonctionnellement de l'attribut A (A -> B).
    
    Méthode : Recherche de contre-exemples (GROUP BY A HAVING uniqExact(B) > 1).
    
    Retourne un dictionnaire avec :
    - 'is_valid': True si la dépendance est respectée, False sinon.
    - 'violations': Un DataFrame Pandas contenant les contre-exemples (si existants).
    - 'message': Un résumé textuel du diagnostic.
    """
    # Protection des noms de tables et colonnes pour éviter les injections/erreurs de syntaxe
    q_table = f"`{database}`.`{table}`"
    q_A = f"`{col_A}`"
    q_B = f"`{col_B}`"
    
    query = f"""
    SELECT 
        {q_A} AS valeur_A, 
        uniqExact({q_B}) AS nb_valeurs_B_differentes,
        groupArray(distinct {q_B}) AS exemples_B
    FROM {q_table}
    GROUP BY valeur_A
    HAVING nb_valeurs_B_differentes > 1
    ORDER BY nb_valeurs_B_differentes DESC
    LIMIT {limit_violations}
    """
    
    try:
        # Récupération du manager existant (Singleton)
        db_manager = clickhouse_manager()
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
        print(f"Erreur lors de l'analyse de dépendance entre {col_A} et {col_B}: {e}")
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
    db_manager = clickhouse_manager()
    
    # 1. Requête pour récupérer proprement le nom de toutes les colonnes de la table
    columns_query = f"""
    SELECT name 
    FROM system.columns 
    WHERE database = '{database}' AND table = '{table}'
    """
    
    try:
        df_cols = db_manager.query_df(columns_query)
        if df_cols.empty:
            print(f"⚠️ Aucune colonne trouvée pour la table {database}.{table}")
            return {}
            
        columns = df_cols['name'].tolist()
        print(f"🔍 Colonnes détectées ({len(columns)}) : {columns}")
        
    except Exception as e:
        print(f"❌ Impossible de récupérer les colonnes de la table : {e}")
        return {}

    # 2. Générer toutes les paires de colonnes ordonnées (Permutations de taille 2)
    # Si on a [col1, col2], itertools.permutations génère (col1, col2) ET (col2, col1)
    all_pairs = list(itertools.permutations(columns, 2))
    print(f"📊 Nombre total de dépendances à tester : {len(all_pairs)}")

    global_results = {}

    # 3. Boucler sur toutes les paires et stocker le résultat
    for col_A, col_B in all_pairs:
        pair_key = f"{col_A} -> {col_B}"
        
        # Exécution du test pour la paire actuelle
        result = check_functional_dependency(database, table, col_A, col_B)
        
        global_results[pair_key] = result

    return global_results