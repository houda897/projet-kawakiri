import math
from collections import Counter
from clickhouse_manager import clickhouse_manager

def get_db(client, database) :
    '''Extracts the column from a database'''

    query = f"""
    SELECT *
    FROM merge('{database}', '^.*$')
    """

    try:
        df = client.query_df(query)
        
        if df.empty:
            print(f"No table found in {database}.")
            return {}

        data_dict = df.to_dict(orient='list')
        return data_dict

    except Exception as e:
        print(f"Error in the extraction : {e}")
        return {}
    

def calculate_shannon_entropy(data_column):
    '''Calcultates the Shannon entropy of a column'''

    data = [v for v in data_column if v is not None]
    if not data:
        return 0.0

    counts = Counter(data_column)
    total_elements = len(data_column)
    
    entropy = 0
    for count in counts.values():
        p_i = count / total_elements
        entropy -= p_i * math.log2(p_i)
        
    return entropy

def process_database_entropy(data_dict):
    '''Take the dictionnary of data and iterate each column
    in the calulate_shannon_entropy function'''
    results = {}
    
    print(f"\n{'Colonne':<15} | {'Entropie (bits)':<15}")
    print("-" * 35)
    
    for col_name, values in data_dict.items():
        score = calculate_shannon_entropy(values)
        
        results[col_name] = round(score, 4)
        
        # Display the result
        print(f"{col_name:<15} | {results[col_name]:<15}")
        
    return results



def shannon_entropy_pipeline():
    client = clickhouse_manager()
    data_dict = get_db(client, client.get_CH_DB())
    process_database_entropy(data_dict)

