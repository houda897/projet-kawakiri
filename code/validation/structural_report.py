from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class StructuralValidationIssue:
    model_id: str
    rule_name: str
    severity: str
    message: str
    source_table: str = ""
    target_table: str = ""
    orphan_count: int = 0


@dataclass(frozen=True)
class StructuralValidationResult:
    model_id: str
    is_valid: bool
    issue_count: int
    orphan_count: int
    issues: tuple[StructuralValidationIssue, ...]
