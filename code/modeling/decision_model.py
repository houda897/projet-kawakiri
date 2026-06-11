from __future__ import annotations

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
        facts = "_".join(self.fact_tables)
        return f"{self.model_type.value.lower()}_{facts.lower()}"
