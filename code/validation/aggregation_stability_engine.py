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

    def _is_key_like_column(self, column_name: str) -> bool:
        """Detects if a column has a typical key or identifier name"""
        name = column_name.lower()
        return (
            name.endswith("id")
            or name.endswith("_id")
            or name.endswith("key")
            or name.endswith("_key")
            or name.endswith("no")
            or name.endswith("_no")
            or "code" in name
        )

    def check_stability(self, candidate: DecisionModelCandidate) -> list[dict]:
        """
        Verifies that the join with the model dimensions does not cause data loss or duplication (fan-out) on SUM, COUNT, and AVG. 
        Natively handles composite primary keys
        """
        reports = []

        for edge in candidate.edges:
            if edge.source_table not in candidate.fact_tables or edge.target_table not in candidate.dimension_tables:
                continue

            fact_table = edge.source_table
            dim_table = edge.target_table

            if not edge.source_columns or not edge.target_columns or len(edge.source_columns) != len(edge.target_columns):
                logger.warning(f"Liaison composite asymétrique ou vide détectée entre {fact_table} et {dim_table}")
                continue

            measure_col = self._get_best_measure(fact_table)
            if not measure_col:
                logger.warning(f"Aucune mesure de test exploitable trouvée pour la table de faits {fact_table}")
                continue

            join_conditions = [
                f"F.{q_ident(f_col)} = D.{q_ident(d_col)}"
                for f_col, d_col in zip(edge.source_columns, edge.target_columns)
            ]
            on_clause = " AND ".join(join_conditions)

            sql_fine = f"""
            SELECT 
                COALESCE(toFloat64(SUM({q_ident(measure_col)})), 0.0),
                toInt64(COUNT({q_ident(measure_col)})),
                COALESCE(toFloat64(AVG({q_ident(measure_col)})), 0.0)
            FROM {q_ident(CH_DB)}.{q_ident(fact_table)}
            """
            
            sql_agg = f"""
            SELECT 
                COALESCE(toFloat64(SUM(F.{q_ident(measure_col)})), 0.0),
                toInt64(COUNT(F.{q_ident(measure_col)})),
                COALESCE(toFloat64(AVG(F.{q_ident(measure_col)})), 0.0)
            FROM {q_ident(CH_DB)}.{q_ident(fact_table)} F
            LEFT JOIN {q_ident(CH_DB)}.{q_ident(dim_table)} D ON {on_clause}
            """

            fine_row = self.db.query(sql_fine).result_rows[0]
            agg_row = self.db.query(sql_agg).result_rows[0]

            fine_sum, fine_count, fine_avg = fine_row[0], fine_row[1], fine_row[2]
            agg_sum, agg_count, agg_avg = agg_row[0], agg_row[1], agg_row[2]

            delta_sum = abs(fine_sum - agg_sum)
            delta_count = abs(fine_count - agg_count)
            delta_avg = abs(fine_avg - agg_avg)

            is_stable_sum = delta_sum <= self.epsilon
            is_stable_count = delta_count == 0
            is_stable_avg = delta_avg <= self.epsilon

            is_stable = is_stable_sum and is_stable_count and is_stable_avg

            reasons = []
            if not is_stable_sum: reasons.append("SUM instability")
            if not is_stable_count: reasons.append("COUNT instability")
            if not is_stable_avg: reasons.append("AVERAGE instability")
            reason_str = ", ".join(reasons) if not is_stable else "Stable"

            reports.append({
                "model_id": candidate.model_id,
                "fact_table": fact_table,
                "dimension_table": dim_table,
                "measure_column": measure_col,
                "fine_sum": fine_sum,
                "agg_sum": agg_sum,
                "delta_sum": round(delta_sum, 4),
                "fine_count": fine_count,
                "agg_count": agg_count,
                "delta_count": delta_count,
                "fine_avg": round(fine_avg, 4),
                "agg_avg": round(agg_avg, 4),
                "delta_avg": round(delta_avg, 4),
                "is_stable": is_stable,
                "reason": reason_str
            })
            
        return reports

    def _get_best_measure(self, table_name: str):
        """
        Find the best numeric column to use as a test measure
        Filter by run_ts and use broad ClickHouse type detection
        """
        sql = f"""
        SELECT column_name 
        FROM {q_ident(META_DB)}.column_stats
        WHERE database_name = %(db)s 
          AND table_name = %(table)s
          AND (
              positionCaseInsensitive(column_type, 'Int') > 0
              OR positionCaseInsensitive(column_type, 'Float') > 0
              OR positionCaseInsensitive(column_type, 'Decimal') > 0
          )
          AND run_ts = (SELECT max(run_ts) FROM {q_ident(META_DB)}.column_stats WHERE database_name = %(db)s)
        ORDER BY variation_coefficient DESC
        """
        rows = self.db.query(sql, parameters={"db": CH_DB, "table": table_name}).result_rows
                
        for row in rows:
            col_name = row[0]
            if not self._is_key_like_column(col_name):
                return col_name
                
        return None
    
    def store_stability(self, reports: list[dict]) -> None:
        """The logs and metric calculations of the stability tests persist"""
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
                r["fine_sum"],
                r["agg_sum"],
                r["delta_sum"],
                r["fine_count"],
                r["agg_count"],
                r["delta_count"],
                r["fine_avg"],
                r["agg_avg"],
                r["delta_avg"],
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
                "fine_sum",
                "agg_sum",
                "delta_sum",
                "fine_count",
                "agg_count",
                "delta_count",
                "fine_avg",
                "agg_avg",
                "delta_avg",
                "is_stable",
                "reason",
            ],
        )

    def print_stability(self, reports : list[dict]) -> None :
        """Displays condensed logs of stability results"""
        logger.info("=== Stability aggregation test ===")
        for report in reports:
            if report["is_stable"]:
                logger.info(f'OK    | Fact table : {report["fact_table"]:<40} -> Dim table : {report["dimension_table"]:<40} | Delta : 0')
            else:
                logger.info(
                    f'ERROR | Fact table : {report["fact_table"]:<40} -> Dim table : {report["dimension_table"]:<40} | '
                    f'{report["reason"]} (Fin: {report["fine_sum"]} vs Agg: {report["agg_sum"]})'
                )