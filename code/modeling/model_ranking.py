from core.clickhouse_manager import get_manager
from core .clickhouse_manager import META_DB
from core.schema import q_ident

from config.scoring import PARSIMONY_WEIGHTS


def get_tables_metrics(tables: list[str]) -> dict:
    '''
    Get for a group of tables :
    - The number of tables
    - The total number of attributes (columns)
    - The number of numeric attributes (Int, Float, Decimal...) 
    '''
    clickhouse = get_manager()

    tables_str = ", ".join([f"'{t}'" for t in tables])
    
    sql = f"""
    SELECT 
        count(DISTINCT table_name) as num_tables,
        count(column_name) as total_attributes,
        sum(case when 
            match(column_type, '(?i)Int|Float|Decimal|Decimal32|Decimal64|Decimal128') 
            then 1 else 0 end
        ) as numeric_attributes
    FROM {q_ident(META_DB)}.column_profiles
    WHERE table_name IN ({tables_str})
    """
    
    res = clickhouse.query(sql).result_rows[0]
    
    return {
        "num_tables": res[0],
        "total_attributes": res[1],
        "numeric_attributes": res[2]
    }

def rank_models_by_parsimony(candidates: list) -> list:
    '''Calculate the parsimony score for each candidate model and sort them from bet to worst'''

    for candidate in candidates: 

        is_galaxy = hasattr(candidate, 'fact_tables')
   
        if is_galaxy:
            fact_tables = candidate.fact_tables
            dim_tables = candidate.shared_dimension_tables
        else :
            fact_tables = [candidate.fact_table]
            dim_tables = candidate.dimension_tables

        all_model_tables = fact_tables + dim_tables
        metrics = get_tables_metrics(all_model_tables)

        score = (
            (metrics["num_tables"] * PARSIMONY_WEIGHTS["table_penalty"]) +
            (metrics["total_attributes"] * PARSIMONY_WEIGHTS["attribute_penalty"]) +
            (metrics["numeric_attributes"] * PARSIMONY_WEIGHTS["numeric_reward"]) +
            (len(all_model_tables) * PARSIMONY_WEIGHTS["dimension_reward"])
        )

        score += len(dim_tables) * PARSIMONY_WEIGHTS["dimension_reward"]

        if is_galaxy and len(fact_tables) > 1:
            num_facts = len(fact_tables)
            num_dims = len(dim_tables)

            score += (num_facts - 1) * PARSIMONY_WEIGHTS["fact_coverage_bonus"]

            score += num_dims * (num_facts - 1) + PARSIMONY_WEIGHTS["shared_dimension_bonus"]
        
        candidate.parsimony_score = round(score, 4)
        
    return sorted(candidates, key=lambda x: x.parsimony_score, reverse=True)