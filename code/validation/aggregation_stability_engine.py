from core.clickhouse_manager import CH_DB, META_DB, ClickHouseManager
from core.logger import get_logger
from core.meta import clear_metadata_table
from core.schema import q_ident
from modeling.decision_model import DecisionModelCandidate

logger = get_logger(__name__)


class AggregationStabilityValidator:
    """
    Validates the structural integrity of decision models (Star/Snowflake schemas) 
    by ensuring that joining a fact table to a dimension table does not alter 
    the underlying data metrics (no fan-out/duplication, no data loss).
    """

    def __init__(self, db: ClickHouseManager):
        self.db = db
        self.epsilon = 0.001

    def check_stability(self, candidate: DecisionModelCandidate) -> list[dict]:
        """
        Main orchestrator. Iterates through all valid fact-to-dimension relationships 
        in a model candidate, dynamically selects test columns, and runs the stability checks.
        """
        reports = []

        for edge in candidate.edges:
            if (
                edge.source_table not in candidate.fact_tables
                or edge.target_table not in candidate.dimension_tables
            ):
                continue

            fact_table = edge.source_table
            dimension_table = edge.target_table

            if (
                not edge.source_columns
                or not edge.target_columns
                or len(edge.source_columns) != len(edge.target_columns)
            ):
                logger.warning(
                    "Invalid join columns between %s and %s",
                    fact_table,
                    dimension_table,
                )
                continue

            measure_column = self._get_best_measure(fact_table)
            if not measure_column:
                logger.warning("No measure found for fact table %s", fact_table)
                continue

            group_column = self._get_best_dimension_grouping(dimension_table)
            if not group_column:
                logger.warning(
                    "No aggregation level found for dimension table %s",
                    dimension_table,
                )
                continue

            report = self._check_edge_stability(
                candidate=candidate,
                fact_table=fact_table,
                dimension_table=dimension_table,
                source_columns=edge.source_columns,
                target_columns=edge.target_columns,
                measure_column=measure_column,
                group_column=group_column,
            )
            reports.append(report)

        return reports

    def _check_edge_stability(
        self,
        candidate: DecisionModelCandidate,
        fact_table: str,
        dimension_table: str,
        source_columns: tuple[str, ...],
        target_columns: tuple[str, ...],
        measure_column: str,
        group_column: str,
    ) -> dict:
        """
        Executes two SQL queries: one on the raw fact table (fine grain) and one 
        aggregated through a JOIN (roll-up). Returns the raw metrics for comparison.
        """
        join_conditions = [
            f"F.{q_ident(source_col)} = D.{q_ident(target_col)}"
            for source_col, target_col in zip(source_columns, target_columns, strict=True)
        ]
        on_clause = " AND ".join(join_conditions)

        sql_fine = f"""
        SELECT
            COALESCE(toFloat64(SUM({q_ident(measure_column)})), 0.0),
            toUInt64(COUNT({q_ident(measure_column)})),
            COALESCE(toFloat64(AVG({q_ident(measure_column)})), 0.0),
            COALESCE(toFloat64(MIN({q_ident(measure_column)})), 0.0),
            COALESCE(toFloat64(MAX({q_ident(measure_column)})), 0.0)
        FROM {q_ident(CH_DB)}.{q_ident(fact_table)}
        """

        sql_agg = f"""
        SELECT
            COALESCE(toFloat64(SUM(group_sum)), 0.0),
            toUInt64(SUM(group_count)),
            COALESCE(toFloat64(SUM(group_sum) / NULLIF(SUM(group_count), 0)), 0.0),
            COALESCE(toFloat64(MIN(group_min)), 0.0),
            COALESCE(toFloat64(MAX(group_max)), 0.0)
        FROM (
            SELECT
                D.{q_ident(group_column)} AS group_value,
                SUM(F.{q_ident(measure_column)}) AS group_sum,
                COUNT(F.{q_ident(measure_column)}) AS group_count,
                MIN(F.{q_ident(measure_column)}) AS group_min,
                MAX(F.{q_ident(measure_column)}) AS group_max
            FROM {q_ident(CH_DB)}.{q_ident(fact_table)} AS F
            LEFT JOIN {q_ident(CH_DB)}.{q_ident(dimension_table)} AS D
                ON {on_clause}
            GROUP BY group_value
        )
        """

        fine_sum, fine_count, fine_avg, fine_min, fine_max = (
            self.db.query(sql_fine).result_rows[0]
        )
        agg_sum, agg_count, agg_avg, agg_min, agg_max = (
            self.db.query(sql_agg).result_rows[0]
        )

        return self._build_report(
            candidate=candidate,
            fact_table=fact_table,
            dimension_table=dimension_table,
            measure_column=measure_column,
            group_column=group_column,
            fine_sum=fine_sum,
            agg_sum=agg_sum,
            fine_count=fine_count,
            agg_count=agg_count,
            fine_avg=fine_avg,
            agg_avg=agg_avg,
            fine_min=fine_min,
            agg_min=agg_min,
            fine_max=fine_max,
            agg_max=agg_max,
        )

    def _build_report(
        self,
        candidate: DecisionModelCandidate,
        fact_table: str,
        dimension_table: str,
        measure_column: str,
        group_column: str,
        fine_sum: float,
        agg_sum: float,
        fine_count: int,
        agg_count: int,
        fine_avg: float,
        agg_avg: float,
        fine_min: float,
        agg_min: float,
        fine_max: float,
        agg_max: float,
    ) -> dict:
        """
        Calculates the deltas between fine and aggregated metrics.
        Determines the stability status and generates error messages if thresholds are exceeded.
        """
        delta_sum = abs(fine_sum - agg_sum)
        delta_count = abs(fine_count - agg_count)
        delta_avg = abs(fine_avg - agg_avg)
        delta_min = abs(fine_min - agg_min)
        delta_max = abs(fine_max - agg_max)

        failed_rules = []

        if delta_sum > self.epsilon:
            failed_rules.append("SUM instability")
        if delta_count != 0:
            failed_rules.append("COUNT instability")
        if delta_avg > self.epsilon:
            failed_rules.append("AVG instability")
        if delta_min > self.epsilon:
            failed_rules.append("MIN instability")
        if delta_max > self.epsilon:
            failed_rules.append("MAX instability")

        is_stable = not failed_rules

        return {
            "model_id": candidate.model_id,
            "fact_table": fact_table,
            "dimension_table": dimension_table,
            "measure_column": measure_column,
            "group_column": group_column,
            "fine_sum": fine_sum,
            "agg_sum": agg_sum,
            "delta_sum": round(delta_sum, 4),
            "fine_count": fine_count,
            "agg_count": agg_count,
            "delta_count": delta_count,
            "fine_avg": round(fine_avg, 4),
            "agg_avg": round(agg_avg, 4),
            "delta_avg": round(delta_avg, 4),
            "fine_min": round(fine_min, 4),
            "agg_min": round(agg_min, 4),
            "delta_min": round(delta_min, 4),
            "fine_max": round(fine_max, 4),
            "agg_max": round(agg_max, 4),
            "delta_max": round(delta_max, 4),
            "is_stable": is_stable,
            "reason": (
                f"Stable after aggregation by {group_column}"
                if is_stable
                else ", ".join(failed_rules)
            ),
        }

    def _get_best_measure(self, table_name: str) -> str | None:
        """
        Finds the most suitable numerical column in a fact table to be used as a measure.
        Prefers columns with high variation coefficients (e.g., amounts, quantities) 
        and explicitly ignores primary/foreign keys.
        """
        sql = f"""
        SELECT column_name
        FROM {q_ident(META_DB)}.column_stats
        WHERE database_name = %(database)s
          AND table_name = %(table)s
          AND (
              positionCaseInsensitive(column_type, 'Int') > 0
              OR positionCaseInsensitive(column_type, 'Float') > 0
              OR positionCaseInsensitive(column_type, 'Decimal') > 0
          )
          AND run_ts = (
              SELECT max(run_ts)
              FROM {q_ident(META_DB)}.column_stats
              WHERE database_name = %(database)s
                AND table_name = %(table)s
          )
        ORDER BY variation_coefficient DESC
        """

        rows = self.db.query(
            sql,
            parameters={"database": CH_DB, "table": table_name},
        ).result_rows

        for row in rows:
            column_name = row[0]
            if not self._is_key_like_column(column_name):
                return column_name

        return None

    def _get_best_dimension_grouping(self, table_name: str) -> str | None:
        """
        Finds the ideal descriptive attribute in a dimension to group data by.
        It avoids unique IDs and continuous measures, favoring categorical strings 
        or dates with low entropy (e.g., Status, Month, Category).
        """
        sql = f"""
        SELECT
            s.column_name,
            s.column_type
        FROM {q_ident(META_DB)}.column_stats AS s
        INNER JOIN {q_ident(META_DB)}.column_profiles AS p
            ON s.database_name = p.database_name
           AND s.table_name = p.table_name
           AND s.column_name = p.column_name
        WHERE s.database_name = %(database)s
          AND s.table_name = %(table)s
          AND s.run_ts = (
              SELECT max(run_ts)
              FROM {q_ident(META_DB)}.column_stats
              WHERE database_name = %(database)s
                AND table_name = %(table)s
          )
          AND p.uniqueness_ratio < 0.95
        ORDER BY
            if(
                positionCaseInsensitive(s.column_type, 'String') > 0
                OR positionCaseInsensitive(s.column_type, 'Date') > 0
                OR positionCaseInsensitive(s.column_type, 'LowCardinality') > 0,
                0,
                1
            ),
            s.entropy_ratio ASC
        """

        rows = self.db.query(
            sql,
            parameters={"database": CH_DB, "table": table_name},
        ).result_rows

        for row in rows:
            column_name = row[0]
            column_type = row[1]

            if self._is_key_like_column(column_name):
                continue

            if self._is_measure_like_type(column_type):
                continue

            return column_name

        return None

    def store_stability(self, reports: list[dict]) -> None:
        """
        Persists the validation logs and metric deltas into the metadata database.
        """
        clear_metadata_table(self.db, "aggregation_stability")

        if not reports:
            return

        rows = [
            [
                CH_DB,
                report["model_id"],
                report["fact_table"],
                report["dimension_table"],
                report["measure_column"],
                report["group_column"],
                report["fine_sum"],
                report["agg_sum"],
                report["delta_sum"],
                report["fine_count"],
                report["agg_count"],
                report["delta_count"],
                report["fine_avg"],
                report["agg_avg"],
                report["delta_avg"],
                report["fine_min"],
                report["agg_min"],
                report["delta_min"],
                report["fine_max"],
                report["agg_max"],
                report["delta_max"],
                report["is_stable"],
                report["reason"],
            ]
            for report in reports
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
                "group_column",
                "fine_sum",
                "agg_sum",
                "delta_sum",
                "fine_count",
                "agg_count",
                "delta_count",
                "fine_avg",
                "agg_avg",
                "delta_avg",
                "fine_min",
                "agg_min",
                "delta_min",
                "fine_max",
                "agg_max",
                "delta_max",
                "is_stable",
                "reason",
            ],
        )

    def print_stability(self, reports: list[dict]) -> None:
        """
        Outputs a summary of the stability tests to the application logger.
        """
        logger.info("=== Aggregation stability test ===")

        if not reports:
            logger.info("No aggregation stability result found.")
            return

        for report in reports:
            if report["is_stable"]:
                logger.info(
                    "VALID | model=%s | fact=%s | dimension=%s | group=%s | measure=%s",
                    report["model_id"],
                    report["fact_table"],
                    report["dimension_table"],
                    report["group_column"],
                    report["measure_column"],
                )
            else:
                logger.warning(
                    "INVALID | model=%s | fact=%s | dimension=%s | group=%s | measure=%s | %s",
                    report["model_id"],
                    report["fact_table"],
                    report["dimension_table"],
                    report["group_column"],
                    report["measure_column"],
                    report["reason"],
                )

    @staticmethod
    def _is_key_like_column(column_name: str) -> bool:
        """
        Helper method to detect technical keys/IDs based on naming conventions.
        """
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

    @staticmethod
    def _is_measure_like_type(column_type: str) -> bool:
        """
        Helper method to determine if a ClickHouse type represents continuous data (Floats/Decimals).
        """
        normalized_type = column_type.lower()
        return "float" in normalized_type or "decimal" in normalized_type