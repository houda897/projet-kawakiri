from .clickhouse_manager import clickhouse_manager
import math

def get_table_stats(database, table):
    '''
    Get lasts stats for a given table
    Return a dictionnary : { 'column': {'entropy': value, 'sparsity': value, 'var_coef': value, 'skewness': value} }
    '''
    
    stats_table_name = f"stats_{database}_{table}"
    print(stats_table_name)
    
    query = f"""
    SELECT 
        column,
        rows,
        distinct_est,
        entropy, 
        sparsity, 
        var_coef, 
        skewness 
    FROM meta.`{stats_table_name}`
    WHERE run_ts in (
        SELECT max(run_ts) 
        FROM meta.`{stats_table_name}`
        )
    """

    # print(query)
    
    try:
        db_manager = clickhouse_manager()
        df = db_manager.client.query_df(query)
        
        if df.empty:
            print(f"No data found for {database}.{table}")
            return {}

        stats_dict = df.set_index('column').to_dict(orient='index')
        
        return stats_dict

    except Exception as e:
        print(f"Error during stats recuperation for {table}: {e}")
        return {}
    
def calculate_identifiability(database, table):
    '''
    Get untreated datas through get_table_stat and return 
    the identifiability score

    '''
    display_result      = False  # -- Turn True to display result in terminal
    display_calculation = False  # -- Turn True to display calculation in terminal

    stats = get_table_stats(database, table)

    if not stats:
        print(f"No data found for {database}.{table}")
        return
    
    # 2. Configuration des poids (Pondération)
    W_UNIQUENESS = 0.5
    W_ENTROPY = 0.3
    W_COMPLETENESS = 0.2
    
    results = {}

    if display_result :
        print(f"Table analysis for : {table}")
        print(f"{'COLUMN':<25} | {'SCORE':<10} | {'DIAGNOSTIC'}")
        print("-"*60)

    for col_name, data in stats.items():
        entropy = data.get('entropy', 0)
        sparsity = data.get('sparsity', 0)
        distinct_est = data.get('distinct_est', 0)
        total_rows = data.get('rows', 1)
        
        uniqueness = distinct_est / total_rows if total_rows > 0 else 0
        completeness = 1 - sparsity
        
        score = (W_UNIQUENESS * uniqueness) + (W_ENTROPY * entropy) + (W_COMPLETENESS * completeness)
        score = round(score, 4)
        
        if display_calculation :
            print("entropy =", entropy)
            print("sparsity =", sparsity)
            print("distinct_est =", distinct_est)
            print("total_rows = ", total_rows)
            print("uniqueness =", uniqueness)
            print("completeness =", completeness)
            print("score =", score)
            print("score_final =", score)
        
        
        # Diagnosis
        if score > 0.85:
            diag = "PK CANDIDATE"
        elif score > 0.5:
            diag = "Useful info"
        elif score > 0.2:
            diag = "Category"
        else:
            diag = "Non usable data"
            
        results[col_name] = {
            "identifiability_score": score,
            "diagnostic": diag,
            # Uncomment if datas are needed later
            #"metrics": data
        }
        
        if display_result :
            print(f"{col_name[:25]:<25} | {score:<10.4f} | {diag}")

    return results