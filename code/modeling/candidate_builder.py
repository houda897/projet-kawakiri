from __future__ import annotations

from collections import defaultdict

from core.clickhouse_manager import CH_DB, META_DB, clickhouse_manager
from core.logger import get_logger
from core.meta import load_confirmed_adjacency_edges, load_table_role_map
from core.schema import q_ident
from modeling.decision_model import (
    DecisionModelCandidate,
    DecisionModelEdge,
    DecisionModelType,
)

logger = get_logger(__name__)


class DecisionModelCandidateBuilder:
    """
    Build plausible decision-model candidates from detected roles and confirmed edges.
    """

    def __init__(self, db: clickhouse_manager):
        self.db = db

    def build_candidates(self) -> list[DecisionModelCandidate]:
        roles = self.load_table_roles()
        edges = self.load_confirmed_edges()
        column_counts = self.load_column_counts()

        candidates = []
        candidates.extend(self.build_star_candidates(roles, edges, column_counts))
        candidates.extend(self.build_snowflake_candidates(roles, edges, column_counts))
        candidates.extend(self.build_constellation_candidates(roles, edges, column_counts))

        return candidates

    def load_table_roles(self) -> dict[str, str]:
        roles = load_table_role_map(self.db, CH_DB)

        if not roles:
            raise ValueError(
                "No table roles found. Run infer-table-roles before build-model-candidates."
            )

        return roles

    def load_confirmed_edges(self) -> list[DecisionModelEdge]:
        return [
            DecisionModelEdge(
                source_table=edge.source_table,
                target_table=edge.target_table,
                source_columns=self.split_columns(edge.source_columns),
                target_columns=self.split_columns(edge.target_columns),
                join_success_ratio=edge.join_success_ratio,
                depth=1,
            )
            for edge in load_confirmed_adjacency_edges(self.db)
        ]

    def load_column_counts(self) -> dict[str, dict[str, int]]:
        sql = f"""
        SELECT
            table_name,
            count() AS attribute_count,
            countIf(
                positionCaseInsensitive(column_type, 'Int') > 0
                OR positionCaseInsensitive(column_type, 'UInt') > 0
                OR positionCaseInsensitive(column_type, 'Float') > 0
                OR positionCaseInsensitive(column_type, 'Decimal') > 0
            ) AS numeric_attribute_count
        FROM {q_ident(META_DB)}.column_profiles
        WHERE database_name = %(database)s
          AND NOT startsWith(column_name, '__')
        GROUP BY table_name
        """

        rows = self.db.query(sql, parameters={"database": CH_DB}).result_rows

        return {
            row[0]: {
                "attribute_count": row[1],
                "numeric_attribute_count": row[2],
            }
            for row in rows
        }

    def build_star_candidates(
        self,
        roles: dict[str, str],
        edges: list[DecisionModelEdge],
        column_counts: dict[str, dict[str, int]],
    ) -> list[DecisionModelCandidate]:
        candidates = []

        for fact_table in self.fact_tables(roles):
            fact_edges = [
                edge
                for edge in edges
                if edge.source_table == fact_table
                and roles.get(edge.target_table) == "DIMENSION"
            ]

            if not fact_edges:
                continue

            dimension_tables = sorted({edge.target_table for edge in fact_edges})

            candidates.append(
                self.to_candidate(
                    model_type=DecisionModelType.STAR,
                    fact_tables=(fact_table,),
                    dimension_tables=tuple(dimension_tables),
                    edges=tuple(fact_edges),
                    column_counts=column_counts,
                )
            )

        return candidates

    def build_snowflake_candidates(
        self,
        roles: dict[str, str],
        edges: list[DecisionModelEdge],
        column_counts: dict[str, dict[str, int]],
    ) -> list[DecisionModelCandidate]:
        candidates = []

        for fact_table in self.fact_tables(roles):
            direct_edges = [
                edge
                for edge in edges
                if edge.source_table == fact_table
                and roles.get(edge.target_table) == "DIMENSION"
            ]

            if not direct_edges:
                continue

            direct_dimensions = {edge.target_table for edge in direct_edges}

            snowflake_edges = list(direct_edges)

            for dimension_table in direct_dimensions:
                for edge in edges:
                    if (
                        edge.source_table == dimension_table
                        and roles.get(edge.target_table) == "DIMENSION"
                    ):
                        snowflake_edges.append(
                            DecisionModelEdge(
                                source_table=edge.source_table,
                                target_table=edge.target_table,
                                source_columns=edge.source_columns,
                                target_columns=edge.target_columns,
                                join_success_ratio=edge.join_success_ratio,
                                depth=2,
                            )
                        )

            all_dimensions = sorted({edge.target_table for edge in snowflake_edges})

            if len(all_dimensions) <= len(direct_dimensions):
                continue

            candidates.append(
                self.to_candidate(
                    model_type=DecisionModelType.SNOWFLAKE,
                    fact_tables=(fact_table,),
                    dimension_tables=tuple(all_dimensions),
                    edges=tuple(snowflake_edges),
                    column_counts=column_counts,
                )
            )

        return candidates

    def build_constellation_candidates(
        self,
        roles: dict[str, str],
        edges: list[DecisionModelEdge],
        column_counts: dict[str, dict[str, int]],
    ) -> list[DecisionModelCandidate]:
        facts_by_dimension: dict[str, set[str]] = defaultdict(set)

        for edge in edges:
            if roles.get(edge.source_table) == "FACT" and roles.get(edge.target_table) == "DIMENSION":
                facts_by_dimension[edge.target_table].add(edge.source_table)

        shared_dimensions = {
            dimension
            for dimension, facts in facts_by_dimension.items()
            if len(facts) >= 2
        }

        if not shared_dimensions:
            return []

        fact_tables = sorted(
            {
                fact
                for dimension in shared_dimensions
                for fact in facts_by_dimension[dimension]
            }
        )

        constellation_edges = [
            edge
            for edge in edges
            if edge.source_table in fact_tables
            and roles.get(edge.target_table) == "DIMENSION"
        ]

        dimension_tables = sorted(
            {edge.target_table for edge in constellation_edges}
        )

        return [
            self.to_candidate(
                model_type=DecisionModelType.CONSTELLATION,
                fact_tables=tuple(fact_tables),
                dimension_tables=tuple(dimension_tables),
                edges=tuple(constellation_edges),
                column_counts=column_counts,
            )
        ]

    def to_candidate(
        self,
        model_type: DecisionModelType,
        fact_tables: tuple[str, ...],
        dimension_tables: tuple[str, ...],
        edges: tuple[DecisionModelEdge, ...],
        column_counts: dict[str, dict[str, int]],
    ) -> DecisionModelCandidate:
        tables = set(fact_tables) | set(dimension_tables)

        attribute_count = sum(
            column_counts.get(table, {}).get("attribute_count", 0)
            for table in tables
        )

        numeric_attribute_count = sum(
            column_counts.get(table, {}).get("numeric_attribute_count", 0)
            for table in tables
        )

        return DecisionModelCandidate(
            model_type=model_type,
            fact_tables=fact_tables,
            dimension_tables=dimension_tables,
            edges=edges,
            table_count=len(tables),
            join_count=len(edges),
            attribute_count=attribute_count,
            numeric_attribute_count=numeric_attribute_count,
        )

    @staticmethod
    def fact_tables(roles: dict[str, str]) -> list[str]:
        return sorted(
            table_name
            for table_name, role in roles.items()
            if role == "FACT"
        )

    @staticmethod
    def split_columns(columns: str) -> tuple[str, ...]:
        return tuple(
            column.strip()
            for column in columns.split(",")
            if column.strip()
        )

    @staticmethod
    def print_candidates(candidates: list[DecisionModelCandidate]) -> None:
        if not candidates:
            logger.info("No decision model candidates found.")
            return

        for candidate in candidates:
            logger.info(
                "%s | id=%s | facts=%s | dimensions=%s | tables=%s | joins=%s | attributes=%s | numeric_attributes=%s",
                candidate.model_type.value,
                candidate.model_id,
                ", ".join(candidate.fact_tables),
                ", ".join(candidate.dimension_tables),
                candidate.table_count,
                candidate.join_count,
                candidate.attribute_count,
                candidate.numeric_attribute_count,
            )
