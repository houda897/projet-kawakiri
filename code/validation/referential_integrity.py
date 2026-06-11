from __future__ import annotations

from core.clickhouse_manager import CH_DB, clickhouse_manager
from core.schema import q_ident
from modeling.decision_model import DecisionModelCandidate, DecisionModelEdge

from validation.structural_report import StructuralValidationIssue


class ReferentialIntegrityValidator:
    """
    Check that every source key value exists in its target table.
    """

    def __init__(self, db: clickhouse_manager, database: str = CH_DB):
        self.db = db
        self.database = database

    def validate(self, candidate: DecisionModelCandidate) -> list[StructuralValidationIssue]:
        issues = []

        for edge in candidate.edges:
            orphan_count = self.count_orphans(edge)

            if orphan_count > 0:
                issues.append(
                    StructuralValidationIssue(
                        model_id=candidate.model_id,
                        rule_name="REFERENTIAL_INTEGRITY",
                        severity="ERROR",
                        message=(
                            f"{orphan_count} value(s) from {edge.source_table} "
                            f"do not exist in {edge.target_table}."
                        ),
                        source_table=edge.source_table,
                        target_table=edge.target_table,
                        orphan_count=orphan_count,
                    )
                )

        return issues

    def count_orphans(self, edge: DecisionModelEdge) -> int:
        sql = self.build_orphan_count_sql(edge)
        row = self.db.query(sql).result_rows[0]
        return int(row[0])

    def build_orphan_count_sql(self, edge: DecisionModelEdge) -> str:
        if len(edge.source_columns) != len(edge.target_columns):
            raise ValueError(
                f"Edge {edge.source_table}->{edge.target_table} has incompatible column counts."
            )

        source_select = ", ".join(
            f"{q_ident(column)} AS c{index}" for index, column in enumerate(edge.source_columns)
        )
        target_select = ", ".join(
            f"{q_ident(column)} AS c{index}" for index, column in enumerate(edge.target_columns)
        )
        source_not_null = " AND ".join(
            f"{q_ident(column)} IS NOT NULL" for column in edge.source_columns
        )
        join_conditions = " AND ".join(
            f"s.c{index} = t.c{index}" for index in range(len(edge.source_columns))
        )
        target_missing = " AND ".join(
            f"t.c{index} IS NULL" for index in range(len(edge.target_columns))
        )

        return f"""
        WITH
            source_values AS (
                SELECT DISTINCT {source_select}
                FROM {q_ident(self.database)}.{q_ident(edge.source_table)}
                WHERE {source_not_null}
            ),
            target_values AS (
                SELECT DISTINCT {target_select}
                FROM {q_ident(self.database)}.{q_ident(edge.target_table)}
            )
        SELECT count()
        FROM source_values AS s
        LEFT JOIN target_values AS t
            ON {join_conditions}
        WHERE {target_missing}
        """
