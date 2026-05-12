from clickhouse_manager import clickhouse_manager

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