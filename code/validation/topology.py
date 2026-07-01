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
        visited: set[str] = set()

        for start_node in graph:
            if start_node in visited:
                continue

            stack = [(start_node, iter(graph.get(start_node, [])))]
            path = [start_node]
            visiting = {start_node}

            while stack:
                current_node, children = stack[-1]

                try:
                    next_node = next(children)
                except StopIteration:
                    stack.pop()
                    path.pop()
                    visiting.remove(current_node)
                    visited.add(current_node)
                    continue

                if next_node in visiting:
                    cycle_start = path.index(next_node)
                    cycle = path[cycle_start:] + [next_node]
                    cycles.add(tuple(cycle))
                    continue

                if next_node in visited:
                    continue

                visiting.add(next_node)
                path.append(next_node)
                stack.append((next_node, iter(graph.get(next_node, []))))

        return sorted(cycles)
