from __future__ import annotations

from dataclasses import dataclass

from core.naming import is_key_like_column
from inference.join_candidate import JoinEngine, JoinPrimaryKeyCandidate
from inference.primary_key import PrimaryKeyCandidate, PrimaryKeyEngine


@dataclass(frozen=True)
class SourceTableStructure:
    """Relational evidence observed before logical-table reconstruction."""

    table_name: str
    entity_key: PrimaryKeyCandidate | None
    incoming_relationships: tuple[JoinPrimaryKeyCandidate, ...]
    outgoing_relationships: tuple[JoinPrimaryKeyCandidate, ...]

    @property
    def incoming_count(self) -> int:
        return len({edge.source_table for edge in self.incoming_relationships})

    @property
    def outgoing_count(self) -> int:
        return len({edge.target_table for edge in self.outgoing_relationships})

    @property
    def is_normalized_entity_source(self) -> bool:
        return self.entity_key is not None and self.incoming_count > 0


class SourceStructureAnalyzer:
    """Choose entity keys and orient source relationships from shared evidence."""

    def __init__(self, db):
        self.db = db

    def load_structures(self) -> dict[str, SourceTableStructure]:
        keys = PrimaryKeyEngine(self.db).load_candidates(
            analysis_scope="SOURCE",
            official_only=False,
        )
        joins = JoinEngine(self.db).load_candidates(analysis_scope="SOURCE")
        return self.build_structures(keys, joins)

    @classmethod
    def build_structures(
        cls,
        keys: list[PrimaryKeyCandidate],
        joins: list[JoinPrimaryKeyCandidate],
    ) -> dict[str, SourceTableStructure]:
        entity_keys = cls.select_entity_keys(keys, joins)
        selected_relationships = cls.select_relationships(joins, entity_keys)
        table_names = (
            {key.table_name for key in keys}
            | {edge.source_table for edge in selected_relationships}
            | {edge.target_table for edge in selected_relationships}
        )

        return {
            table_name: SourceTableStructure(
                table_name=table_name,
                entity_key=entity_keys.get(table_name),
                incoming_relationships=tuple(
                    edge for edge in selected_relationships if edge.target_table == table_name
                ),
                outgoing_relationships=tuple(
                    edge for edge in selected_relationships if edge.source_table == table_name
                ),
            )
            for table_name in sorted(table_names)
        }

    @classmethod
    def select_entity_keys(
        cls,
        keys: list[PrimaryKeyCandidate],
        joins: list[JoinPrimaryKeyCandidate],
    ) -> dict[str, PrimaryKeyCandidate]:
        keys_by_table: dict[str, list[PrimaryKeyCandidate]] = {}
        for key in keys:
            if key.null_ratio > 0.000001 or key.uniqueness_ratio < 0.999999999:
                continue
            keys_by_table.setdefault(key.table_name, []).append(key)

        selected = {}
        for table_name, candidates in keys_by_table.items():
            selected[table_name] = max(
                candidates,
                key=lambda candidate: cls.entity_key_score(candidate, joins),
            )
        return selected

    @staticmethod
    def entity_key_score(
        candidate: PrimaryKeyCandidate,
        joins: list[JoinPrimaryKeyCandidate],
    ) -> tuple:
        candidate_columns = SourceStructureAnalyzer.split_columns(candidate.column_name)
        incoming_sources = {
            edge.source_table
            for edge in joins
            if edge.target_table == candidate.table_name
            and SourceStructureAnalyzer.split_columns(edge.target_column) == candidate_columns
        }
        outgoing_targets = {
            edge.target_table
            for edge in joins
            if edge.source_table == candidate.table_name
            and SourceStructureAnalyzer.split_columns(edge.source_column) == candidate_columns
        }
        key_like_columns = sum(1 for column in candidate_columns if is_key_like_column(column))

        # Incoming references identify the key owned by this table. A candidate
        # that mainly points elsewhere behaves more like a foreign key.
        return (
            len(incoming_sources) - len(outgoing_targets),
            len(incoming_sources),
            key_like_columns,
            candidate.identifiability_score,
            -len(candidate_columns),
            candidate.column_name,
        )

    @staticmethod
    def select_relationships(
        joins: list[JoinPrimaryKeyCandidate],
        entity_keys: dict[str, PrimaryKeyCandidate],
    ) -> list[JoinPrimaryKeyCandidate]:
        selected = []
        seen = set()

        for edge in joins:
            target_key = entity_keys.get(edge.target_table)
            if target_key is None or edge.target_column != target_key.column_name:
                continue
            signature = (
                edge.source_table,
                edge.source_column,
                edge.target_table,
                edge.target_column,
            )
            if signature in seen:
                continue
            selected.append(edge)
            seen.add(signature)

        return selected

    @staticmethod
    def split_columns(columns: str) -> tuple[str, ...]:
        return tuple(column.strip() for column in columns.split(",") if column.strip())
