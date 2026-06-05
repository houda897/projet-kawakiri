# modeling/semantic_homogeneity.py
import math
from core.clickhouse_manager import clickhouse_manager, META_DB
from core.meta import clear_metadata_table
from core.logger import get_logger
from core.schema import q_ident
from config.scoring import SEMANTIC_HOMOGENEITY_WEIGHTS
from core.clickhouse_manager import CH_DB, META_DB
from inference.table_role import TableRoleCandidate

logger = get_logger(__name__)

class SemanticHomogeneityEngine:
    def __init__(self, db: clickhouse_manager):
        self.db = db
        self.database_name = clickhouse_manager.get_CH_DB(self.db)
        self.threshold = SEMANTIC_HOMOGENEITY_WEIGHTS["threshold"]
        self.w_entropy = SEMANTIC_HOMOGENEITY_WEIGHTS["entropy_weight"]
        self.w_cv = SEMANTIC_HOMOGENEITY_WEIGHTS["variation_coef_weight"]
        self.w_skew = SEMANTIC_HOMOGENEITY_WEIGHTS["skewness_weight"]

    def check_dimension_homogeneity(self, table_name: str) -> dict:
        '''Proves that a dimension table doesn't contain fact measures'''

        sql = f"""
        SELECT 
            column_name, column_type, entropy_ratio, variation_coefficient, skewness_score
        FROM {q_ident(META_DB)}.column_stats
        WHERE database_name = %(db)s AND table_name = %(table)s
        AND column_type IN ('Int32', 'Int64', 'Float32', 'Float64', 'UInt32', 'UInt64')
        AND NOT startsWith(column_name, 'id_') AND NOT endsWith(column_name, '_id')
        """

        rows = self.db.query(sql, parameters={"db": CH_DB, "table": table_name}).result_rows
        violations = []

        for row in rows:
            col_name, col_type, entropy, cv, skew = row
            
            cv_bounded = min(abs(cv or 0.0) / 2.0, 1.0)
            skew_bounded = math.tanh(abs(skew or 0.0))
            
            fact_score = (self.w_entropy * (entropy or 0.0) + 
                          self.w_cv * cv_bounded + 
                          self.w_skew * skew_bounded)
            
            if fact_score > self.threshold:
                violations.append({
                    "column": col_name,
                    "score": round(fact_score, 3),
                    "reason": f"Suspicious continuous distribution for a dimension (Variable coef = {cv}, Skewness = {skew})"
                })
        
        issue_count = len(violations)
        is_valid = issue_count == 0
        
        score = max(0.0, 1.0 - (issue_count * 0.2))
        
        measure_like = ", ".join([v["column"] for v in violations])
        reason_str = "; ".join([v["reason"] for v in violations]) if not is_valid else "Pure and homogeneous dimension table"

        return {
            "table_name": table_name,
            "role": "DIMENSION",
            "is_valid": is_valid,
            "homogeneity_score": round(score, 2),
            "measure_like_columns": measure_like,
            "descriptive_like_columns": "",
            "issue_count": issue_count,
            "reason": reason_str
        }
    
    def check_fact_homogeneity(self, table_name: str) -> dict:
        '''Prove that a fact table doesn't contain dimension attributes'''

        sql = f"""
        SELECT 
            column_name, column_type, entropy_ratio, variation_coefficient
        FROM {q_ident(META_DB)}.column_stats
        WHERE database_name = %(db)s AND table_name = %(table)s
        """
        rows = self.db.query(sql, parameters={"db": CH_DB, "table": table_name}).result_rows
        violations = []
        
        measure_keywords = ['qty', 'quantity', 'amount', 'price', 'cost', 'tax', 'freight', 'discount', 'total', 'margin']

        for row in rows:
            col_name, col_type, entropy, cv = row
            col_lower = col_name.lower()
            
            if col_lower.endswith('id') or col_lower.startswith('id_') or col_lower.endswith('key'):
                continue

            if 'Date' in col_type or 'date' in col_lower:
                continue

            if any(kw in col_lower for kw in measure_keywords):
                continue
                
            if 'String' in col_type:
                continue

            entropy_val = entropy or 0.0
            cv_val = cv or 0.0
            
            dim_score = (0.7 * (1.0 - entropy_val)) + (0.3 * math.exp(-cv_val))
            
            if dim_score > self.threshold:
                violations.append({
                    "column": col_name,
                    "score": round(dim_score, 3),
                    "reason": f"Distribution too discreet for a fact (Entropy = {round(entropy_val, 2)}, Variable coef = {round(cv_val, 2)})"
                })
        
        issue_count = len(violations)
        is_valid = issue_count == 0
        
        score = max(0.0, 1.0 - (issue_count * 0.2))
        
        desc_like = ", ".join([v["column"] for v in violations])
        reason_str = "; ".join([v["reason"] for v in violations]) if not is_valid else "Pure and homogeneous fact table"

        return {
            "table_name": table_name,
            "role": "FACT",
            "is_valid": is_valid,
            "homogeneity_score": round(score, 2),
            "measure_like_columns": "",
            "descriptive_like_columns": desc_like,
            "issue_count": issue_count,
            "reason": reason_str
        }
    
    def check_homogeneity(self, raw_roles: list[TableRoleCandidate]) -> list:
        reports = []
        for role in raw_roles:
            if role.role == "DIMENSION":
                reports.append(self.check_dimension_homogeneity(role.table_name))
            elif role.role == "FACT":
                reports.append(self.check_fact_homogeneity(role.table_name))
            else:
                logger.warning(f'Error in table role : {role.role}')
        return reports           
    
    def store_homogeneity(self, reports: list[dict]) -> None:
        """
        Store semantic homogeneity validation results so downstream steps can consume stable metadata.
        """
        clear_metadata_table(self.db, "semantic_homogeneity")

        if not reports:
            return

        rows = [
            [
                CH_DB,
                report["table_name"],
                report["role"],
                report["is_valid"],
                report["homogeneity_score"],
                report["measure_like_columns"],
                report["descriptive_like_columns"],
                report["issue_count"],
                report["reason"],
            ]
            for report in reports
        ]

        self.db.insert(
            f"{META_DB}.semantic_homogeneity",
            rows,
            column_names=[
                "database_name",
                "table_name",
                "role",
                "is_valid",
                "homogeneity_score",
                "measure_like_columns",
                "descriptive_like_columns",
                "issue_count",
                "reason",
            ],
        )

    def print_homogeneity(self, reports) -> None:
        for report in reports:
            if report["role"] == "DIMENSION":
                problematic_columns = report["measure_like_columns"]
            else : 
                problematic_columns = report["descriptive_like_columns"]
            if report["is_valid"] :
                truth = 'True'
            else :
                truth = 'False'

            logger.info(f'Table name : {report["table_name"]:<30} | role : {report["role"]:<10} | is valid : {truth:<5} | homogeneity score : {report["homogeneity_score"]:<4} | problematic columns = {problematic_columns:<30} | reason = {report["reason"]}')