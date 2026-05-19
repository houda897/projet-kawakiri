from .clickhouse_manager import clickhouse_manager
import math
import os
from dotenv import load_dotenv


def get_table_stats(database, table):
    """
    Get lasts stats for a given table
    Return a dictionnary : { 'column': {'entropy': value, 'sparsity': value, 'var_coef': value, 'skewness': value} }
    """

    stats_table_name = f"stats_{database}_{table}"
    # print(stats_table_name)

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
        df = db_manager.queryDf(query)

        if df.empty:
            print(f"No data found for {database}.{table}")
            return {}

        stats_dict = df.set_index("column").to_dict(orient="index")

        return stats_dict

    except Exception as e:
        print(f"Error during stats recuperation for {table}: {e}")
        return {}


def calculate_identifiability(database, table):
    """
    Get untreated datas through get_table_stat and return
    the identifiability score
    """

    load_dotenv()

    # Terminal display (Modification in)
    display_result = os.getenv("Result", "False").lower() == "true"
    display_calculation = os.getenv("Calculation", "False").lower() == "true"

    stats = get_table_stats(database, table)

    if not stats:
        print(f"No data found for {database}.{table}")
        return

    # Ponderation (Weight modification in .env)
    W_UNIQUENESS = float(os.getenv("W_UNIQUENESS", 0.5))
    W_ENTROPY = float(os.getenv("W_ENTROPY", 0.3))
    W_COMPLETENESS = float(os.getenv("W_COMPLETENESS", 0.2))

    total_weight = W_UNIQUENESS + W_ENTROPY + W_COMPLETENESS
    if not (0.9999 <= total_weight <= 1.0001):
        print(f"Total weight : {round(total_weight,3)}, is not equal to 1")
        return

    results = {}

    if display_result:
        print(f"Table analysis for : {table}")
        print(f"{'COLUMN':<25} | {'SCORE':<10} | {'DIAGNOSTIC'}")
        print("-" * 60)

    for col_name, data in stats.items():
        entropy = data.get("entropy", 0)
        sparsity = data.get("sparsity", 0)
        distinct_est = data.get("distinct_est", 0)
        total_rows = data.get("rows", 1)

        uniqueness = distinct_est / total_rows if total_rows > 0 else 0
        completeness = 1 - sparsity

        score = (
            (W_UNIQUENESS * uniqueness) + (W_ENTROPY * entropy) + (W_COMPLETENESS * completeness)
        )
        score = round(score, 4)

        if display_calculation:
            print("entropy =", entropy)
            print("sparsity =", sparsity)
            print("distinct_est =", distinct_est)
            print("total_rows = ", total_rows)
            print("uniqueness =", uniqueness)
            print("completeness =", completeness)
            print("score =", score)
            print("score_final =", score)

        # Diagnosis (Threshold modification in .env)
        th_pk = float(os.getenv("TH_PK", 0.85))
        th_info = float(os.getenv("TH_info", 0.5))
        th_cat = float(os.getenv("TH_cat", 0.2))

        if score > th_pk:
            diag = "PK CANDIDATE"
        elif score > th_info:
            diag = "Useful info"
        elif score > th_cat:
            diag = "Category"
        else:
            diag = "Non usable data"

        results[col_name] = {
            "identifiability_score": score,
            "diagnostic": diag,
            # Uncomment if datas are needed later
            # "metrics": data
        }

        if display_result:
            print(f"{str(col_name)[:25]:<25} | {score:<10.4f} | {diag}")

    return results

def get_columns_name(database, table):
    """Get columns name for a given table
    Return a list of column name"""
    query = f"""
    SELECT name
    FROM system.columns
    WHERE database = '{database}' AND table = '{table}'
    """
    try:
        db_manager = clickhouse_manager()
        df = db_manager.queryDf(query)

        if df.empty:
            print(f"No columns found for {database}.{table}")
            return []

        columns = df['name'].tolist()
        return columns
    except Exception as e:
        print(f"Error during columns recuperation for {table}: {e}")
        return []
