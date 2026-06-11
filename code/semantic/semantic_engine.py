from config.scoring import SEMANTIC_THRESHOLDS, SEMANTIC_WEIGHTS
from core.logger import get_logger
from core.naming import normalize_column_name as normalize_key_column_name
from inference.adjacency import AdjacencyEdge
from rapidfuzz import fuzz

logger = get_logger(__name__)


class SemanticEngine:
    """Semantic engine that computes a similarity (with Levenshtein distance) score between column names to enrich join candidates"""

    def normalize_column_name(self, column_name: str) -> str:
        """Normalise the column name by removing prefix/suffix patterns, underscores, hyphens and converting to lowercase"""
        return normalize_key_column_name(column_name)

    def compute_similarity(self, col1: str, col2: str) -> float:
        """Calculate a similarity score between two column names using Levenshtein distance"""
        norm1 = self.normalize_column_name(col1)
        norm2 = self.normalize_column_name(col2)

        if not norm1 or not norm2:
            return 1.0 if norm1 == norm2 else 0.0

        if "date" in norm1 and "date" in norm2:
            return 1.0

        score = fuzz.ratio(norm1, norm2) / 100.0

        return round(score, 4)

    def enrich_edges_with_semantics(self, edges: list[AdjacencyEdge]) -> list[AdjacencyEdge]:
        """
        Enrich the join candidates (edges) by recalculating an hybrid score that combine the original join success ratio with a semantic similarity score
        and add a evidence label based on the new hybrid score
        """

        enriched_edges = []

        for edge in edges:
            column_pairs = list(zip(edge.source_columns, edge.target_columns, strict=False))

            if column_pairs:
                similarities = [
                    self.compute_similarity(src_col, tgt_col) for src_col, tgt_col in column_pairs
                ]
                semantic_score = sum(similarities) / len(similarities)
            else:
                semantic_score = 0.0

            hybrid_score = round(
                (SEMANTIC_WEIGHTS["join_success_ratio"] * edge.join_success_ratio)
                + (SEMANTIC_WEIGHTS["semantic_similarity"] * semantic_score),
                6,
            )
            if hybrid_score >= SEMANTIC_THRESHOLDS["confirmed"]:
                evidence_label = "CONFIRMED"
            elif hybrid_score <= SEMANTIC_THRESHOLDS["coincidence"]:
                evidence_label = "WEAK"
            else:
                evidence_label = "COINCIDENCE"

            enriched_edges.append(
                AdjacencyEdge(
                    source_table=edge.source_table,
                    target_table=edge.target_table,
                    source_columns=edge.source_columns,
                    target_columns=edge.target_columns,
                    join_success_ratio=edge.join_success_ratio,
                    hybrid_score=hybrid_score,
                    evidence=evidence_label,
                )
            )

        return enriched_edges
