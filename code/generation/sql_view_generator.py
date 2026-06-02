from __future__ import annotations

from dataclasses import dataclass

from core.clickhouse_manager import CH_DB, META_DB, clickhouse_manager
from core.logger import get_logger
from core.meta import load_confirmed_adjacency_edges, load_table_role_map
from core.naming import normalize_column_name as normalize_key_column_name
from core.schema import q_ident

logger = get_logger(__name__)


@dataclass
class SqlViewDefinition:
    fact_table: str
    view_name: str
    sql: str


class SQLViewGenerator:
    """
    Generate simple star-schema SQL views from detected FACT -> DIMENSION links.
    """

    def __init__(self, db: clickhouse_manager):
        self.db = db

    def generate_views(self) -> list[SqlViewDefinition]:
        roles = self.load_table_roles()
        edges = self.load_edges()

        fact_tables = {
            table_name
            for table_name, role in roles.items()
            if role == "FACT"
        }

        views = []

        for fact_table in sorted(fact_tables):
            fact_edges = self.select_star_edges(
                fact_table=fact_table,
                edges=edges,
                roles=roles,
            )

            if not fact_edges:
                continue

            sql = self.build_view_sql(fact_table, fact_edges)
            view_name = f"view_{fact_table.lower()}_star"

            views.append(
                SqlViewDefinition(
                    fact_table=fact_table,
                    view_name=view_name,
                    sql=sql,
                )
            )

        return views

    def load_table_roles(self) -> dict[str, str]:
        roles = load_table_role_map(self.db, CH_DB)

        if not roles:
            raise ValueError(
                "No table roles found. Run infer-table-roles before generate-sql-views."
            )

        return roles

    def load_edges(self) -> list[dict]:
        return [
            {
                "source_table": edge.source_table,
                "target_table": edge.target_table,
                "source_columns": edge.source_columns,
                "target_columns": edge.target_columns,
                "join_success_ratio": edge.join_success_ratio,
            }
            for edge in load_confirmed_adjacency_edges(self.db)
        ]

    def select_star_edges(
        self,
        fact_table: str,
        edges: list[dict],
        roles: dict[str, str],
    ) -> list[dict]:
        """
        Keep only the best FACT -> DIMENSION edge for each dimension table.

        The raw adjacency graph may contain several physical joins between the
        same fact and dimension. For a star view, one clean join per dimension
        is enough, so ties prefer column names that match exactly.
        """

        best_by_dimension: dict[str, dict] = {}

        for edge in edges:
            if edge["source_table"] != fact_table:
                continue

            if roles.get(edge["target_table"]) != "DIMENSION":
                continue

            target_table = edge["target_table"]
            current = best_by_dimension.get(target_table)

            if current is None or self.edge_rank(edge) > self.edge_rank(current):
                best_by_dimension[target_table] = edge

        return [
            best_by_dimension[target_table]
            for target_table in sorted(best_by_dimension)
        ]

    def build_view_sql(
        self,
        fact_table: str,
        edges: list[dict],
    ) -> str:
        fact_alias = "f"

        select_lines = [
            f"    {fact_alias}.*",
        ]

        join_lines = []

        for index, edge in enumerate(edges, start=1):
            dim_table = edge["target_table"]
            dim_alias = f"d{index}"

            select_lines.append(f"    {dim_alias}.*")

            source_columns = self.split_columns(edge["source_columns"])
            target_columns = self.split_columns(edge["target_columns"])

            join_conditions = [
                f"{fact_alias}.{q_ident(source_col)} = {dim_alias}.{q_ident(target_col)}"
                for source_col, target_col in zip(source_columns, target_columns, strict=False)
            ]

            join_lines.append(
                f"LEFT JOIN {q_ident(CH_DB)}.{q_ident(dim_table)} AS {dim_alias}\n"
                f"    ON {' AND '.join(join_conditions)}"
            )

        sql = (
            "SELECT\n"
            + ",\n".join(select_lines)
            + f"\nFROM {q_ident(CH_DB)}.{q_ident(fact_table)} AS {fact_alias}\n"
            + "\n".join(join_lines)
        )

        return sql

    def create_views(self) -> list[SqlViewDefinition]:
        views = self.generate_views()

        for view in views:
            full_view_name = f"{q_ident(CH_DB)}.{q_ident(view.view_name)}"

            self.db.command(f"DROP VIEW IF EXISTS {full_view_name}")

            self.db.command(
                f"""
                CREATE VIEW {full_view_name} AS
                {view.sql}
                """
            )

            logger.info(
                "SQL view created: %s for fact table %s",
                view.view_name,
                view.fact_table,
            )

        return views

    @staticmethod
    def split_columns(columns: str) -> list[str]:
        return [column.strip() for column in columns.split(",") if column.strip()]

    @classmethod
    def edge_rank(cls, edge: dict) -> tuple[float, int]:
        source_columns = cls.split_columns(edge["source_columns"])
        target_columns = cls.split_columns(edge["target_columns"])

        exact_matches = sum(
            1
            for source_col, target_col in zip(source_columns, target_columns, strict=False)
            if cls.normalize_column_name(source_col) == cls.normalize_column_name(target_col)
        )

        return (float(edge["join_success_ratio"]), exact_matches)

    @staticmethod
    def normalize_column_name(column: str) -> str:
        return normalize_key_column_name(column)

    @staticmethod
    def print_views(views: list[SqlViewDefinition]) -> None:
        if not views:
            logger.info("No SQL views generated.")
            return

        for view in views:
            logger.info("=== %s ===\n%s", view.view_name, view.sql)
