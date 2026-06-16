from __future__ import annotations

from dataclasses import dataclass

from core.clickhouse_manager import CH_DB, META_DB, ClickHouseManager
from core.logger import get_logger
from core.naming import normalize_column_name
from core.schema import q_ident

logger = get_logger(__name__)


@dataclass
class SqlViewDefinition:
    fact_table: str
    view_name: str
    sql: str


@dataclass(frozen=True)
class CertifiedModel:
    model_id: str
    model_type: str
    status: str
    fact_tables: tuple[str, ...]


class SQLViewGenerator:
    """
    Generate SQL views from the best certified decision model.
    """

    def __init__(self, db: ClickHouseManager):
        self.db = db

    def generate_views(self) -> list[SqlViewDefinition]:
        model = self.load_best_certified_model()
        edges = self.load_model_edges(model.model_id)

        views = []

        for fact_table in model.fact_tables:
            fact_edges = self.select_edges_for_view(model, fact_table, edges)

            if not fact_edges:
                continue

            sql = self.build_view_sql(fact_table, fact_edges)
            view_name = f"view_{fact_table.lower()}_{model.model_type.lower()}"

            views.append(
                SqlViewDefinition(
                    fact_table=fact_table,
                    view_name=view_name,
                    sql=sql,
                )
            )

        return views

    def load_best_certified_model(self) -> CertifiedModel:
        """
        Load the best certified model.

        VALID models are preferred. WARNING models are accepted as a fallback
        because some optional validators can still be missing during research.
        """

        sql = f"""
        SELECT
            c.model_id,
            c.status,
            m.model_type,
            m.fact_tables
        FROM {q_ident(META_DB)}.model_certifications AS c
        INNER JOIN {q_ident(META_DB)}.decision_model_candidates AS m
            ON c.database_name = m.database_name
           AND c.model_id = m.model_id
        WHERE c.database_name = %(database)s
          AND c.status IN ('VALID', 'WARNING')
        ORDER BY
            if(c.status = 'VALID', 0, 1),
            c.certification_score DESC,
            c.parsimony_score DESC,
            c.created_at DESC
        LIMIT 1
        """

        rows = self.db.query(sql, parameters={"database": CH_DB}).result_rows

        if not rows:
            raise ValueError(
                "No certified model found. Run certify-models before generate-sql-views."
            )

        row = rows[0]
        return CertifiedModel(
            model_id=row[0],
            status=row[1],
            model_type=row[2],
            fact_tables=tuple(self.split_columns(row[3])),
        )

    def load_model_edges(self, model_id: str) -> list[dict]:
        sql = f"""
        SELECT
            source_table,
            target_table,
            source_columns,
            target_columns,
            join_success_ratio,
            depth
        FROM {q_ident(META_DB)}.decision_model_edges
        WHERE database_name = %(database)s
          AND model_id = %(model_id)s
        ORDER BY depth, source_table, target_table
        """

        rows = self.db.query(
            sql,
            parameters={"database": CH_DB, "model_id": model_id},
        ).result_rows

        return [
            {
                "source_table": row[0],
                "target_table": row[1],
                "source_columns": row[2],
                "target_columns": row[3],
                "join_success_ratio": row[4],
                "depth": row[5],
            }
            for row in rows
        ]

    def select_edges_for_view(
        self,
        model: CertifiedModel,
        fact_table: str,
        edges: list[dict],
    ) -> list[dict]:
        if model.model_type == "SNOWFLAKE":
            return self.select_reachable_edges(fact_table, self.deduplicate_edges(edges))

        return self.deduplicate_edges(
            [
                edge
                for edge in edges
                if edge["source_table"] == fact_table and edge["depth"] == 1
            ]
        )

    def deduplicate_edges(self, edges: list[dict]) -> list[dict]:
        best_by_link: dict[tuple[str, str], dict] = {}

        for edge in edges:
            link = (edge["source_table"], edge["target_table"])
            current = best_by_link.get(link)

            if current is None or self.edge_rank(edge) > self.edge_rank(current):
                best_by_link[link] = edge

        return sorted(
            best_by_link.values(),
            key=lambda edge: (edge["depth"], edge["source_table"], edge["target_table"]),
        )

    @staticmethod
    def select_reachable_edges(fact_table: str, edges: list[dict]) -> list[dict]:
        reachable_tables = {fact_table}
        selected_edges = []

        for edge in sorted(edges, key=lambda item: item["depth"]):
            if edge["source_table"] not in reachable_tables:
                continue

            selected_edges.append(edge)
            reachable_tables.add(edge["target_table"])

        return selected_edges

    def build_view_sql(
        self,
        fact_table: str,
        edges: list[dict],
    ) -> str:
        table_aliases = {fact_table: "f"}

        select_lines = self.build_select_lines(
            table_name=fact_table,
            table_alias="f",
            column_alias_prefix="fact",
        )

        join_lines = []

        for edge in edges:
            source_table = edge["source_table"]
            dim_table = edge["target_table"]
            source_alias = table_aliases[source_table]
            dim_alias = table_aliases.get(dim_table)

            if dim_alias is not None:
                continue

            dim_alias = f"d{len(table_aliases)}"
            table_aliases[dim_table] = dim_alias
            select_lines.extend(
                self.build_select_lines(
                    table_name=dim_table,
                    table_alias=dim_alias,
                    column_alias_prefix=dim_table.lower(),
                )
            )

            source_columns = self.split_columns(edge["source_columns"])
            target_columns = self.split_columns(edge["target_columns"])

            join_conditions = [
                f"{source_alias}.{q_ident(source_col)} = {dim_alias}.{q_ident(target_col)}"
                for source_col, target_col in zip(source_columns, target_columns, strict=False)
            ]

            join_lines.append(
                f"LEFT JOIN {q_ident(CH_DB)}.{q_ident(dim_table)} AS {dim_alias}\n"
                f"    ON {' AND '.join(join_conditions)}"
            )

        sql = (
            "SELECT\n"
            + ",\n".join(select_lines)
            + f"\nFROM {q_ident(CH_DB)}.{q_ident(fact_table)} AS f\n"
            + "\n".join(join_lines)
        )

        return sql

    def build_select_lines(
        self,
        table_name: str,
        table_alias: str,
        column_alias_prefix: str,
    ) -> list[str]:
        columns = self.load_table_columns(table_name)

        if not columns:
            raise ValueError(
                f"No column profile found for table {table_name}. Run profile-basic before generate-sql-views."
            )

        return [
            f"    {table_alias}.{q_ident(column)} AS {q_ident(f'{column_alias_prefix}_{column}')}"
            for column in columns
        ]

    def load_table_columns(self, table_name: str) -> list[str]:
        sql = f"""
        SELECT column_name
        FROM {q_ident(META_DB)}.column_profiles
        WHERE database_name = %(database)s
          AND table_name = %(table)s
          AND NOT startsWith(column_name, '__')
        ORDER BY column_name
        """

        rows = self.db.query(
            sql,
            parameters={"database": CH_DB, "table": table_name},
        ).result_rows

        return [row[0] for row in rows]

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
            if normalize_column_name(source_col) == normalize_column_name(target_col)
        )

        return (float(edge["join_success_ratio"]), exact_matches)

    @staticmethod
    def print_views(views: list[SqlViewDefinition]) -> None:
        if not views:
            logger.info("No SQL views generated.")
            return

        for view in views:
            logger.info("=== %s ===\n%s", view.view_name, view.sql)
