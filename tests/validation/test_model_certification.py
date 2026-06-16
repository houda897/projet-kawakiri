from unittest.mock import MagicMock

from modeling.decision_model import (
    DecisionModelCandidate,
    DecisionModelEdge,
    DecisionModelType,
)
from validation.model_certification import (
    CertificationIssue,
    ModelCertificationEngine,
    ModelCertificationResult,
)


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
        attribute_count=6,
        numeric_attribute_count=3,
    )


def test_certify_candidate_is_valid_when_all_rules_pass() -> None:
    engine = ModelCertificationEngine(db=MagicMock())
    candidate = make_candidate()

    result = engine.certify_candidate(
        candidate=candidate,
        parsimony_scores={candidate.model_id: 42.0},
        structural_results={
            candidate.model_id: {
                "is_valid": True,
                "issue_count": 0,
                "orphan_count": 0,
            }
        },
        granularity_results={
            candidate.model_id: [
                {
                    "fact_table": "sales",
                    "grain_columns": "customer_id",
                    "duplicate_count": 0,
                    "is_valid": True,
                    "reason": "Fact grain is deterministic.",
                }
            ]
        },
        homogeneity_results={
            "sales": {"is_valid": True, "reason": "ok"},
            "customers": {"is_valid": True, "reason": "ok"},
        },
        stability_results={
            candidate.model_id: [
                {
                    "fact_table": "sales",
                    "dimension_table": "customers",
                    "measure_column": "amount",
                    "is_stable": True,
                    "reason": "Stable",
                }
            ]
        },
    )

    assert result.status == "VALID"
    assert result.is_certified is True
    assert result.certification_score == 100.0
    assert result.parsimony_score == 42.0
    assert result.issue_count == 0


def test_certify_candidate_is_invalid_when_a_validation_fails() -> None:
    engine = ModelCertificationEngine(db=MagicMock())
    candidate = make_candidate()

    result = engine.certify_candidate(
        candidate=candidate,
        parsimony_scores={candidate.model_id: 42.0},
        structural_results={
            candidate.model_id: {
                "is_valid": False,
                "issue_count": 1,
                "orphan_count": 3,
            }
        },
        granularity_results={
            candidate.model_id: [
                {
                    "fact_table": "sales",
                    "grain_columns": "customer_id",
                    "duplicate_count": 2,
                    "is_valid": False,
                    "reason": "2 duplicated grain combination(s) found.",
                }
            ]
        },
        homogeneity_results={
            "sales": {"is_valid": True, "reason": "ok"},
            "customers": {
                "is_valid": False,
                "reason": "Dimension contains measure-like columns.",
            },
        },
        stability_results={
            candidate.model_id: [
                {
                    "fact_table": "sales",
                    "dimension_table": "customers",
                    "measure_column": "amount",
                    "is_stable": False,
                    "reason": "Data duplication during aggregation",
                }
            ]
        },
    )

    assert result.status == "INVALID"
    assert result.is_certified is False
    assert result.issue_count == 4
    assert {issue.rule_name for issue in result.issues} == {
        "STRUCTURAL_VALIDATION",
        "DETERMINISTIC_GRANULARITY",
        "SEMANTIC_HOMOGENEITY",
        "AGGREGATION_STABILITY",
    }


def test_certify_candidate_warns_when_expected_results_are_missing() -> None:
    engine = ModelCertificationEngine(db=MagicMock())
    candidate = make_candidate()

    result = engine.certify_candidate(
        candidate=candidate,
        parsimony_scores={},
        structural_results={},
        granularity_results={},
        homogeneity_results={},
        stability_results={},
    )

    assert result.status == "WARNING"
    assert result.is_certified is False
    assert result.issue_count == 6
    assert all(issue.severity == "WARNING" for issue in result.issues)


def test_store_results_persists_certifications_and_issues() -> None:
    db = MagicMock()
    engine = ModelCertificationEngine(db)
    result = ModelCertificationResult(
        model_id="star_sales",
        status="INVALID",
        is_certified=False,
        certification_score=65.0,
        parsimony_score=42.0,
        issue_count=1,
        issues=(
            CertificationIssue(
                rule_name="STRUCTURAL_VALIDATION",
                severity="ERROR",
                message="Structural validation failed.",
            ),
        ),
    )

    engine.store_results([result])

    assert db.command.call_count == 2
    assert db.insert.call_count == 2
    assert db.insert.call_args_list[0][0][0].endswith(".model_certifications")
    assert db.insert.call_args_list[1][0][0].endswith(".model_certification_issues")


def test_loaders_read_all_validation_result_types() -> None:
    db = MagicMock()
    db.query.side_effect = [
        MagicMock(result_rows=[("star_sales", 0.91)]),
        MagicMock(result_rows=[("star_sales", True, 0, 0)]),
        MagicMock(result_rows=[("star_sales", "sales", "customer_id", 0, True, "ok")]),
        MagicMock(result_rows=[("sales", True, 1.0, 0, "ok")]),
        MagicMock(
            result_rows=[
                (
                    "star_sales",
                    "sales",
                    "customers",
                    "amount",
                    "country",
                    True,
                    "Stable",
                )
            ]
        ),
        MagicMock(result_rows=[("geography", 0.9, "table_has_no_confirmed_relationships")]),
    ]
    engine = ModelCertificationEngine(db)

    assert engine.load_parsimony_scores() == {"star_sales": 0.91}
    assert engine.load_structural_results()["star_sales"]["is_valid"] is True
    assert engine.load_granularity_results()["star_sales"][0]["grain_columns"] == "customer_id"
    assert engine.load_homogeneity_results()["sales"]["homogeneity_score"] == 1.0

    stability = engine.load_stability_results()["star_sales"][0]
    assert stability["dimension_table"] == "customers"
    assert stability["group_column"] == "country"
    assert stability["is_stable"] is True

    isolated = engine.load_isolated_tables()
    assert isolated == [
        {
            "table_name": "geography",
            "role": "ISOLATED",
            "confidence": 0.9,
            "reason": "table_has_no_confirmed_relationships",
        }
    ]
