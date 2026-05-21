import itertools
from core.logger import get_logger
from inference.primary_key import PrimaryKeyCandidate
from core.clickhouse_manager import clickhouse_manager
from collections import defaultdict
from stats.functional_dependency import check_functional_dependency

logger = get_logger(__name__)

class CompositeKeyEngine:
    def __init__(self, db: clickhouse_manager):
        self.db = db

    def _is_numeric(self, ch_type: str) -> bool:
        """Check if a ClickHouse type is numeric."""
        t = ch_type.lower()
        return "int" in t or "float" in t or "decimal" in t
    
    def generate_composite_candidates(self, all_columns: list[PrimaryKeyCandidate], tables_without_pk: list[str]) -> list[PrimaryKeyCandidate]:
        '''
        Generates composite key candidates using a greedy iterative approach.
        For each table without a simple PK, it starts with the column with the highest confidence score and iteratively adds columns based on their confidence and uniqueness ratios.
        '''
        
        valid_composite_candidates = []

        columns_by_table = defaultdict(list)
        for c in all_columns:
            columns_by_table[c.table_name].append(c)

        for table in tables_without_pk:
            table_cols = columns_by_table.get(table, [])
            
            if len(table_cols) < 2:
                continue

            table_cols.sort(key=lambda c: (c.confidence, c.uniqueness_ratio), reverse=True)
            
            database_name = table_cols[0].database_name

            current_combo = [table_cols[0], table_cols[1]]
            
            for size in range(2, len(table_cols) + 1):
                
                if size > 2:
                    current_combo.append(table_cols[size - 1])
                
                combo_names = [c.column_name for c in current_combo]
                logger.info(f"Testing combo for {table} (Size {size}): {combo_names}")
                
                is_valid = check_functional_dependency(database_name, table, combo_names, self.db)
                
                if is_valid:
                    logger.info(f"Composite key found {table} : {combo_names}")
                    
                    valid_composite_candidates.append(PrimaryKeyCandidate(
                        database_name=database_name,
                        table_name=table,
                        column_name=", ".join(combo_names), 
                        column_type="Composite",
                        rows=current_combo[0].rows,
                        null_ratio=0.0,
                        uniqueness_ratio=1.0, 
                        identifiability_score=sum(c.identifiability_score for c in current_combo) / len(current_combo),
                        confidence=sum(c.confidence for c in current_combo) / len(current_combo),
                        reason=f"Composite PK (Size {len(combo_names)}) validated by DF"
                    ))
                    
                    break 
                    
        return valid_composite_candidates
    
    