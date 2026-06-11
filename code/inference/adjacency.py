from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from core.clickhouse_manager import META_DB, ClickHouseManager
from core.logger import get_logger
from core.meta import clear_metadata_table

from inference.join_candidate import JoinPrimaryKeyCandidate

logger = get_logger(__name__)


class SemanticEdgeEnricher(Protocol):
    def enrich_edges_with_semantics(
        self,
        edges: list[AdjacencyEdge],
    ) -> list[AdjacencyEdge]: ...


@dataclass
class AdjacencyEdge:
    """
    Directed relationship between two tables.

    The edge points from the source table carrying the referencing column to the
    target table carrying the candidate key.
    """

    source_table: str
    target_table: str
    source_columns: tuple[str, ...]
    target_columns: tuple[str, ...]
    join_success_ratio: float
    hybrid_score: float | None
    evidence: str


class AdjacencyMatrixEngine:
    """
    Build a table-level adjacency matrix from physical join evidence.
    """

    def __init__(self, db: ClickHouseManager, semantic_engine: SemanticEdgeEnricher):
        self.db = db
        self.semantic_engine = semantic_engine

    def build_edges_from_join_candidates(
        self,
        join_candidates: list[JoinPrimaryKeyCandidate],
    ) -> list[AdjacencyEdge]:
        """
        Convert column-level join candidates into table-level directed edges.
        """

        edges = []

        for candidate in join_candidates:
            edges.append(
                AdjacencyEdge(
                    source_table=candidate.source_table,
                    target_table=candidate.target_table,
                    source_columns=self.split_columns(candidate.source_column),
                    target_columns=self.split_columns(candidate.target_column),
                    join_success_ratio=candidate.join_success_ratio,
                    hybrid_score=None,
                    evidence="physical_join_coverage",
                )
            )

        return self.semantic_engine.enrich_edges_with_semantics(edges)

    @staticmethod
    def split_columns(columns: str) -> tuple[str, ...]:
        return tuple(column.strip() for column in columns.split(",") if column.strip())

    def build_matrix(
        self,
        edges: list[AdjacencyEdge],
    ) -> dict[str, dict[str, float]]:
        """
        Build a sparse adjacency matrix indexed by source and target table.

        When several edges exist between the same pair of tables, the strongest
        join coverage is kept.
        """

        matrix: dict[str, dict[str, float]] = {}
        confirmed_edges = [edge for edge in edges if edge.evidence == "CONFIRMED"]

        for edge in confirmed_edges:
            matrix.setdefault(edge.source_table, {})

            current_score = matrix[edge.source_table].get(edge.target_table, 0.0)
            matrix[edge.source_table][edge.target_table] = max(
                current_score,
                edge.hybrid_score or edge.join_success_ratio,
            )

        return matrix

    def store_edges(self, edges: list[AdjacencyEdge]) -> None:
        """
        Store adjacency edges in the metadata database.
        """

        clear_metadata_table(self.db, "adjacency_edges")

        if not edges:
            return

        rows = [
            [
                edge.source_table,
                edge.target_table,
                ",".join(edge.source_columns),
                ",".join(edge.target_columns),
                edge.join_success_ratio,
                edge.evidence,
            ]
            for edge in edges
        ]

        self.db.insert(
            f"{META_DB}.adjacency_edges",
            rows,
            column_names=[
                "source_table",
                "target_table",
                "source_columns",
                "target_columns",
                "join_success_ratio",
                "evidence",
            ],
        )

    @staticmethod
    def print_matrix(matrix: dict[str, dict[str, float]]) -> None:
        """
        Print the adjacency matrix as readable table-to-table links.
        """

        if not matrix:
            logger.info("No adjacency edges found.")
            return

        for source_table, targets in matrix.items():
            for target_table, score in targets.items():
                logger.info("%s -> %s | score=%s", source_table, target_table, score)

    @staticmethod
    def print_binary_matrix(matrix: dict[str, dict[str, float]]) -> None:
        """
        Print the adjacency matrix as a compact binary table.

        Long table names are replaced by aliases to keep the output readable.
        """

        if not matrix:
            logger.info("No adjacency edges found.")
            return

        tables = sorted(
            set(matrix.keys())
            | {target_table for targets in matrix.values() for target_table in targets.keys()}
        )

        aliases = {table: f"T{index + 1}" for index, table in enumerate(tables)}

        alias_width = max(5, max(len(alias) for alias in aliases.values()) + 2)

        lines = []
        lines.append("Adjacency binary matrix")
        lines.append("")

        header = "".ljust(alias_width)
        for table in tables:
            header += aliases[table].center(alias_width)

        lines.append(header)

        for source_table in tables:
            row = aliases[source_table].ljust(alias_width)

            for target_table in tables:
                if source_table == target_table:
                    value = "0"
                else:
                    value = "1" if matrix.get(source_table, {}).get(target_table, 0.0) > 0 else "0"

                row += value.center(alias_width)

            lines.append(row)

        lines.append("")
        lines.append("Legend:")

        for table in tables:
            lines.append(f"{aliases[table]} = {table}")

        logger.info("\n%s", "\n".join(lines))

    @staticmethod
    def print_edges(edges: list[AdjacencyEdge]) -> None:
        """Print the edges with their evidence label"""

        for edge in edges:
            src = f"{edge.source_table}.{edge.source_columns[0]}"
            tgt = f"{edge.target_table}.{edge.target_columns[0]}"

            logger.info(
                f"{src:<25} -> {tgt:<25} | ratio : {edge.join_success_ratio:<10} | hybrid score: {edge.hybrid_score:<10} | {edge.evidence}"
            )
