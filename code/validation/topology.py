from __future__ import annotations

from collections import defaultdict

from modeling.decision_model import DecisionModelCandidate, DecisionModelType
from validation.structural_report import StructuralValidationIssue


class TopologyValidator:
    """
    Validate the graph shape of an inferred decision model.
    """

    def validate(self, candidate: DecisionModelCandidate) -> list[StructuralValidationIssue]:
        issues = []
        issues.extend(self.find_self_loops(candidate))
        issues.extend(self.find_fact_to_fact_edges(candidate))
        issues.extend(self.find_invalid_star_edges(candidate))
        issues.extend(self.find_cycles(candidate))
        return issues

    def find_self_loops(
        self,
        candidate: DecisionModelCandidate,
    ) -> list[StructuralValidationIssue]:
        return [
            StructuralValidationIssue(
                model_id=candidate.model_id,
                rule_name="NO_SELF_LOOP",
                severity="ERROR",
                message=f"Table {edge.source_table} links to itself.",
                source_table=edge.source_table,
                target_table=edge.target_table,
            )
            for edge in candidate.edges
            if edge.source_table == edge.target_table
        ]

    def find_fact_to_fact_edges(
        self,
        candidate: DecisionModelCandidate,
    ) -> list[StructuralValidationIssue]:
        fact_tables = set(candidate.fact_tables)

        return [
            StructuralValidationIssue(
                model_id=candidate.model_id,
                rule_name="NO_FACT_TO_FACT_EDGE",
                severity="ERROR",
                message=f"Fact table {edge.source_table} links to fact table {edge.target_table}.",
                source_table=edge.source_table,
                target_table=edge.target_table,
            )
            for edge in candidate.edges
            if edge.source_table in fact_tables
            and edge.target_table in fact_tables
            and edge.source_table != edge.target_table
        ]

    def find_invalid_star_edges(
        self,
        candidate: DecisionModelCandidate,
    ) -> list[StructuralValidationIssue]:
        if candidate.model_type != DecisionModelType.STAR:
            return []

        fact_tables = set(candidate.fact_tables)
        dimension_tables = set(candidate.dimension_tables)
        issues = []

        for edge in candidate.edges:
            if (
                edge.source_table not in fact_tables
                or edge.target_table not in dimension_tables
                or edge.depth != 1
            ):
                issues.append(
                    StructuralValidationIssue(
                        model_id=candidate.model_id,
                        rule_name="STAR_DIRECT_TO_DIMENSION",
                        severity="ERROR",
                        message="A star model must only contain direct fact-to-dimension edges.",
                        source_table=edge.source_table,
                        target_table=edge.target_table,
                    )
                )

        return issues

    def find_cycles(
        self,
        candidate: DecisionModelCandidate,
    ) -> list[StructuralValidationIssue]:
        graph: dict[str, list[str]] = defaultdict(list)

        for edge in candidate.edges:
            graph[edge.source_table].append(edge.target_table)

        cycles = self.detect_cycles(graph)

        return [
            StructuralValidationIssue(
                model_id=candidate.model_id,
                rule_name="NO_CYCLE",
                severity="ERROR",
                message=f"Cycle detected: {' -> '.join(cycle)}.",
            )
            for cycle in cycles
        ]

    @staticmethod
    def detect_cycles(graph: dict[str, list[str]]) -> list[tuple[str, ...]]:
        cycles: set[tuple[str, ...]] = set()
        visiting: set[str] = set()
        visited: set[str] = set()
        path: list[str] = []

        def visit(node: str) -> None:
            if node in visiting:
                cycle_start = path.index(node)
                cycle = path[cycle_start:] + [node]
                cycles.add(tuple(cycle))
                return

            if node in visited:
                return

            visiting.add(node)
            path.append(node)

            for next_node in graph.get(node, []):
                visit(next_node)

            path.pop()
            visiting.remove(node)
            visited.add(node)

        for node in graph:
            visit(node)

        return sorted(cycles)
