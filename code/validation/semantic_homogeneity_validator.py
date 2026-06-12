import math

from config.scoring import SEMANTIC_HOMOGENEITY_WEIGHTS
from core.clickhouse_manager import CH_DB, META_DB, ClickHouseManager
from core.logger import get_logger
from core.meta import clear_metadata_table
from core.naming import is_key_like_column as is_key_like_column_name
from core.schema import q_ident
from inference.table_role import TableRoleCandidate

logger = get_logger(__name__)

MEASURE_KEYWORDS = {
    "amount",
    "price",
    "cost",
    "quantity",
    "qty",
    "total",
    "margin",
    "discount",
    "tax",
    "revenue",
    "sales",
    "profit",
    "rate",
    "score",
}

DESCRIPTIVE_KEYWORDS = {
    "name",
    "label",
    "description",
    "category",
    "type",
    "status",
    "city",
    "country",
    "region",
}


class SemanticHomogeneityValidator:
    def __init__(self, db: ClickHouseManager):
        self.db = db
        self.database_name = CH_DB
        self.threshold = SEMANTIC_HOMOGENEITY_WEIGHTS["threshold"]
        self.w_entropy = SEMANTIC_HOMOGENEITY_WEIGHTS["entropy_weight"]
        self.w_cv = SEMANTIC_HOMOGENEITY_WEIGHTS["variation_coef_weight"]
        self.w_skew = SEMANTIC_HOMOGENEITY_WEIGHTS["skewness_weight"]

    def is_key_like_column(self, column_name: str) -> bool:
        """Detects key/identifier type technical columns to exclude from analyses"""
        return is_key_like_column_name(column_name)

    def check_dimension_homogeneity(self, table_name: str) -> dict:
        """Proves that a dimension table doesn't contain fact measures"""

        sql = f"""
        SELECT
            cs.column_name, cp.column_type, cs.entropy_ratio, cs.variation_coefficient, cs.skewness_score
        FROM {q_ident(META_DB)}.column_stats cs
        JOIN {q_ident(META_DB)}.column_profiles cp
            ON cs.database_name = cp.database_name
            AND cs.table_name = cp.table_name
            AND cs.column_name = cp.column_name
        WHERE cs.database_name = %(db)s AND cs.table_name = %(table)s
        AND cs.run_ts = (
            SELECT max(run_ts)
            FROM {q_ident(META_DB)}.column_stats
            WHERE database_name = %(db)s
        )
        AND (
            positionCaseInsensitive(cp.column_type, 'Int') > 0
            OR positionCaseInsensitive(cp.column_type, 'Float') > 0
            OR positionCaseInsensitive(cp.column_type, 'Decimal') > 0
        )
        """

        rows = self.db.query(
            sql, parameters={"db": self.database_name, "table": table_name}
        ).result_rows
        violations = []

        for row in rows:
            col_name, col_type, entropy, cv, skew = row

            if self.is_key_like_column(col_name):
                continue

            cv_bounded = min(abs(cv or 0.0) / 2.0, 1.0)
            skew_bounded = math.tanh(abs(skew or 0.0))

            fact_score = (
                self.w_entropy * (entropy or 0.0)
                + self.w_cv * cv_bounded
                + self.w_skew * skew_bounded
            )

            if fact_score > self.threshold:
                violations.append(
                    {
                        "column": col_name,
                        "score": round(fact_score, 3),
                        "reason": f"Suspicious continuous distribution for a dimension (Variable coef = {cv}, Skewness = {skew})",
                    }
                )

        issue_count = len(violations)
        is_valid = issue_count == 0

        score = max(0.0, 1.0 - (issue_count * 0.2))

        measure_like = ", ".join([v["column"] for v in violations])
        reason_str = (
            "; ".join([v["reason"] for v in violations])
            if not is_valid
            else "Pure and homogeneous dimension table"
        )

        return {
            "table_name": table_name,
            "role": "DIMENSION",
            "is_valid": is_valid,
            "homogeneity_score": round(score, 2),
            "measure_like_columns": measure_like,
            "descriptive_like_columns": "",
            "issue_count": issue_count,
            "reason": reason_str,
        }

    def check_fact_homogeneity(self, table_name: str) -> dict:
        """Prove that a fact table doesn't contain dimension attributes"""

        sql = f"""
        SELECT
            cs.column_name,
            cp.column_type,
            cs.entropy_ratio,
            cs.variation_coefficient,
            cp.null_ratio,
            cp.uniqueness_ratio
        FROM {q_ident(META_DB)}.column_stats cs
        JOIN {q_ident(META_DB)}.column_profiles cp
            ON cs.database_name = cp.database_name
            AND cs.table_name = cp.table_name
            AND cs.column_name = cp.column_name
        WHERE cs.database_name = %(db)s AND cs.table_name = %(table)s
        AND cs.run_ts = (
            SELECT max(run_ts)
            FROM {q_ident(META_DB)}.column_stats
            WHERE database_name = %(db)s
        )
        """
        rows = self.db.query(
            sql, parameters={"db": self.database_name, "table": table_name}
        ).result_rows
        violations = []

        for row in rows:
            col_name, col_type, entropy, cv, null_ratio, uniqueness_ratio = row
            col_lower = col_name.lower()

            if self.is_key_like_column(col_name):
                continue

            if "Date" in col_type or "date" in col_lower:
                continue

            if any(kw in col_lower for kw in MEASURE_KEYWORDS):
                continue

            if "String" in col_type:
                if any(kw in col_lower for kw in DESCRIPTIVE_KEYWORDS):
                    violations.append(
                        {
                            "column": col_name,
                            "score": 1.0,
                            "reason": f"String column with descriptive keyword in a fact table ('{col_name}')",
                        }
                    )
                continue

            entropy_val = entropy or 0.0
            cv_val = cv or 0.0
            cv_bounded = min(abs(cv_val) / 2.0, 1.0)
            fact_weights = self.w_entropy + self.w_cv

            dim_score = (
                (self.w_entropy * (1.0 - entropy_val))
                + (self.w_cv * math.exp(-cv_bounded))
            ) / fact_weights

            if dim_score > self.threshold:
                violations.append(
                    {
                        "column": col_name,
                        "score": round(dim_score, 3),
                        "reason": (
                            f"Distribution too discrete for a fact "
                            f"(Entropy = {round(entropy_val, 2)}, Variable coef = {round(cv_val, 2)}, "
                            f"Uniqueness = {round(uniqueness_ratio or 0.0, 2)})"
                        ),
                    }
                )

        issue_count = len(violations)
        is_valid = issue_count == 0

        score = max(0.0, 1.0 - (issue_count * 0.2))

        desc_like = ", ".join([v["column"] for v in violations])
        reason_str = (
            "; ".join([v["reason"] for v in violations])
            if not is_valid
            else "Pure and homogeneous fact table"
        )

        return {
            "table_name": table_name,
            "role": "FACT",
            "is_valid": is_valid,
            "homogeneity_score": round(score, 2),
            "measure_like_columns": "",
            "descriptive_like_columns": desc_like,
            "issue_count": issue_count,
            "reason": reason_str,
        }

    def check_homogeneity(self, raw_roles: list[TableRoleCandidate]) -> list:
        reports = []
        for role in raw_roles:
            if role.role == "DIMENSION":
                reports.append(self.check_dimension_homogeneity(role.table_name))
            elif role.role == "FACT":
                reports.append(self.check_fact_homogeneity(role.table_name))
            else:
                logger.warning("Error in table role: %s", role.role)
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
            f"{q_ident(META_DB)}.semantic_homogeneity",
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
            else:
                problematic_columns = report["descriptive_like_columns"]
            if report["is_valid"]:
                truth = "True"
            else:
                truth = "False"

            logger.info(
                "Table name: %-30s | role: %-10s | is valid: %-5s | "
                "homogeneity score: %-4s | problematic columns=%-30s | reason=%s",
                report["table_name"],
                report["role"],
                truth,
                report["homogeneity_score"],
                problematic_columns,
                report["reason"],
            )
