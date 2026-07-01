from unittest.mock import MagicMock

from modeling.decision_model import (
    DecisionModelCandidate,
    DecisionModelEdge,
    DecisionModelType,
)
from validation.structural_validator import StructuralValidator


def make_candidate() -> DecisionModelCandidate:
    edge = DecisionModelEdge(
        source_table="sales",
        target_table="customers",
        source_columns=("customer_id",),
        target_columns=("customer_id",),
        join_success_ratio=1.0,
        depth=1,
    )

    return DecisionModelCandidate(
        model_type=DecisionModelType.STAR,
        fact_tables=("sales",),
        dimension_tables=("customers",),
        edges=(edge,),
        table_count=2,
        join_count=1,
        attribute_count=0,
        numeric_attribute_count=0,
    )


def test_validate_candidate_is_valid_without_topology_or_integrity_issues() -> None:
    db = MagicMock()
    validator = StructuralValidator(db)
    validator.integrity_validator.count_orphans = MagicMock(return_value=0)

    result = validator.validate_candidate(make_candidate())

    assert result.is_valid is True
    assert result.issue_count == 0
    assert result.orphan_count == 0


def test_validate_candidate_is_invalid_when_orphans_exist() -> None:
    db = MagicMock()
    validator = StructuralValidator(db)
    validator.integrity_validator.count_orphans = MagicMock(return_value=2)

    result = validator.validate_candidate(make_candidate())

    assert result.is_valid is False
    assert result.issue_count == 1
    assert result.orphan_count == 2
    assert result.issues[0].rule_name == "REFERENTIAL_INTEGRITY"


def test_store_results_persists_summary_and_issues() -> None:
    db = MagicMock()
    validator = StructuralValidator(db)
    validator.integrity_validator.count_orphans = MagicMock(return_value=2)
    result = validator.validate_candidate(make_candidate())

    validator.store_results([result])

    assert db.command.call_count == 2
    assert db.insert.call_count == 2
    assert db.insert.call_args_list[0][0][0].endswith(".decision_model_validations")
    assert db.insert.call_args_list[1][0][0].endswith(".decision_model_validation_issues")
