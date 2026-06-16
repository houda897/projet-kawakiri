from __future__ import annotations

import hashlib
from dataclasses import dataclass
from enum import Enum


class DecisionModelType(str, Enum):
    STAR = "STAR"
    SNOWFLAKE = "SNOWFLAKE"
    CONSTELLATION = "CONSTELLATION"


@dataclass(frozen=True)
class DecisionModelEdge:
    source_table: str
    target_table: str
    source_columns: tuple[str, ...]
    target_columns: tuple[str, ...]
    join_success_ratio: float
    depth: int


@dataclass(frozen=True)
class DecisionModelCandidate:
    model_type: DecisionModelType
    fact_tables: tuple[str, ...]
    dimension_tables: tuple[str, ...]
    edges: tuple[DecisionModelEdge, ...]
    table_count: int
    join_count: int
    attribute_count: int
    numeric_attribute_count: int

    @property
    def model_id(self) -> str:
        facts = "_".join(self.fact_tables).lower() or "model"
        signature_parts = [
            self.model_type.value,
            ",".join(sorted(self.fact_tables)),
            ",".join(sorted(self.dimension_tables)),
            *(
                "|".join(
                    (
                        edge.source_table,
                        edge.target_table,
                        ",".join(edge.source_columns),
                        ",".join(edge.target_columns),
                        str(edge.depth),
                    )
                )
                for edge in sorted(
                    self.edges,
                    key=lambda item: (
                        item.source_table,
                        item.target_table,
                        item.source_columns,
                        item.target_columns,
                        item.depth,
                    ),
                )
            ),
        ]
        digest = hashlib.sha1("::".join(signature_parts).encode("utf-8")).hexdigest()[:8]

        return f"{self.model_type.value.lower()}_{facts}_{digest}"
