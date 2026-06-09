from core.clickhouse_manager import CH_DB, META_DB, clickhouse_manager
from core.schema import q_ident
from core.logger import get_logger
from modeling.decision_model import DecisionModelCandidate
from core.meta import clear_metadata_table

logger = get_logger(__name__)

class AggregationStabilityEngine:
    def __init__(self, db: clickhouse_manager):
        self.db = db
        self.epsilon = 0.001 

    def check_stability(self, candidate: DecisionModelCandidate) -> list[dict]:
        '''Verifies that aggregating a measure via the model's dimensions does not cause any data loss or duplication'''

        reports = []

        for edge in candidate.edges:
            if edge.source_table not in candidate.fact_tables or edge.target_table not in candidate.dimension_tables:
                continue

            fact_table = edge.source_table
            dim_table = edge.target_table
            fk_cols = edge.source_columns
            pk_cols = edge.target_columns

            if not fk_cols or not pk_cols:
                continue

            measure_col = self._get_best_measure(fact_table)
            if not measure_col:
                logger.debug(f"Aucune mesure numérique trouvée dans {fact_table} pour le test de stabilité.")
                continue

            fk_col = fk_cols[0]
            pk_col = pk_cols[0]

            sql_fine = f"""
            SELECT COALESCE(toFloat64(SUM({measure_col})), 0.0) 
            FROM {q_ident(CH_DB)}.{q_ident(fact_table)}
            """
            
            sql_agg = f"""
            SELECT COALESCE(toFloat64(SUM(agg_measure)), 0.0)
            FROM (
                SELECT SUM(F.{measure_col}) as agg_measure
                FROM {q_ident(CH_DB)}.{q_ident(fact_table)} F
                LEFT JOIN {q_ident(CH_DB)}.{q_ident(dim_table)} D
                ON F.{fk_col} = D.{pk_col}
                GROUP BY D.{pk_col}
            )
            """

            fine_val = self.db.query(sql_fine).result_rows[0][0]
            agg_val = self.db.query(sql_agg).result_rows[0][0]
            
            delta = abs(fine_val - agg_val)
            is_stable = delta <= self.epsilon

            if is_stable:
                reason = "Stable"
            elif agg_val < fine_val:
                reason = "Data loss during aggregation"
            else:
                reason = "Data duplication during aggregation"

            reports.append({
                "model_id": candidate.model_id,
                "fact_table": fact_table,
                "dimension_table": dim_table,
                "measure_column": measure_col,
                "fine_grain_sum": fine_val,
                "aggregated_sum": agg_val,
                "delta": round(delta, 4),
                "is_stable": is_stable,
                "reason": reason
            })
            
        return reports

    def _get_best_measure(self, table_name: str):
        '''Find the best numeric column to use as test mesure (excluing PK)'''
        
        sql = f"""
        SELECT column_name 
        FROM {q_ident(META_DB)}.column_stats
        WHERE database_name = %(db)s AND table_name = %(table)s
        AND column_type IN ('Int32', 'Int64', 'Float32', 'Float64', 'UInt32', 'UInt64')
        AND NOT endsWith(lower(column_name), 'id')
        AND NOT startsWith(lower(column_name), 'id_')
        AND NOT endsWith(lower(column_name), 'key')
        ORDER BY variation_coefficient DESC 
        LIMIT 1
        """
        rows = self.db.query(sql, parameters={"db": CH_DB, "table": table_name}).result_rows
                
        return rows[0][0] if rows else None
    
    def store_stability(self, reports: list[dict]) -> None:
        '''Store the stability stats in the clickhouse'''
        clear_metadata_table(self.db, "aggregation_stability")

        if not reports:
            return

        rows = [
            [
                CH_DB,
                r["model_id"],
                r["fact_table"],
                r["dimension_table"],
                r["measure_column"],
                r["fine_grain_sum"],
                r["aggregated_sum"],
                r["delta"],
                r["is_stable"],
                r["reason"],
            ]
            for r in reports
        ]

        self.db.insert(
            f"{META_DB}.aggregation_stability",
            rows,
            column_names=[
                "database_name",
                "model_id",
                "fact_table",
                "dimension_table",
                "measure_column",
                "fine_grain_sum",
                "aggregated_sum",
                "delta",
                "is_stable",
                "reason",
            ],
        )

    def print_stability(self, reports : list[dict]) -> None :
        logger.info("=== Stability agregation test ===")
        for report in reports:
            if report["is_stable"]:
                logger.info(f'OK    | Fact table : {report["fact_table"]:<40} -> Dim table : {report["dimension_table"]:<40} | Delta : 0')
            else:
                logger.info(f'ERROR | Fact table : {report["fact_table"]:<40} -> Dim table : {report["dimension_table"]:<40} | {report["reason"]} (Fin: {report["fine_grain_sum"]} vs Agg: {report["aggregated_sum"]})')