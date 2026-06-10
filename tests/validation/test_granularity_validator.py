from types import SimpleNamespace
from unittest.mock import MagicMock

from modeling.decision_model import (
    DecisionModelCandidate,
    DecisionModelEdge,
    DecisionModelType,
)
from validation.granularity_validator import GranularityValidator


def make_candidate() -> DecisionModelCandidate:
    edges = (
        DecisionModelEdge(
            source_table="sales",
            target_table="customers",
            source_columns=("customer_id",),
            target_columns=("customer_id",),
            join_success_ratio=1.0,
            depth=1,
        ),
        DecisionModelEdge(
            source_table="sales",
            target_table="products",
            source_columns=("product_id", "variant_id"),
            target_columns=("product_id", "variant_id"),
            join_success_ratio=1.0,
            depth=1,
        ),
    )

    return DecisionModelCandidate(
        model_type=DecisionModelType.STAR,
        fact_tables=("sales",),
        dimension_tables=("customers", "products"),
        edges=edges,
        table_count=3,
        join_count=2,
        attribute_count=10,
        numeric_attribute_count=5,
    )


def test_build_fact_grain_uses_all_fact_to_dimension_source_columns() -> None:
    grain = GranularityValidator.build_fact_grain(make_candidate(), "sales")

    assert grain == ("customer_id", "product_id", "variant_id")


def test_build_duplicate_grain_sql_supports_composite_grain() -> None:
    validator = GranularityValidator(db=MagicMock(), database="lab_db")

    sql = validator.build_duplicate_grain_sql(
        fact_table="sales",
        grain_columns=("customer_id", "product_id"),
    )

    assert "FROM `lab_db`.`sales`" in sql
    assert "GROUP BY `customer_id`, `product_id`" in sql
    assert "`customer_id` IS NOT NULL" in sql
    assert "`product_id` IS NOT NULL" in sql
    assert "HAVING count() > 1" in sql


def test_validate_returns_valid_when_no_duplicate_grain_exists() -> None:
    db = MagicMock()
    db.query.return_value = SimpleNamespace(result_rows=[(0,)])
    validator = GranularityValidator(db)

    results = validator.validate(make_candidate())

    assert len(results) == 1
    assert results[0].is_valid is True
    assert results[0].duplicate_count == 0


def test_validate_returns_invalid_when_duplicate_grain_exists() -> None:
    db = MagicMock()
    db.query.return_value = SimpleNamespace(result_rows=[(3,)])
    validator = GranularityValidator(db)

    results = validator.validate(make_candidate())

    assert results[0].is_valid is False
    assert results[0].duplicate_count == 3
    assert "duplicated grain" in results[0].reason


def test_store_results_persists_granularity_validation() -> None:
    db = MagicMock()
    db.query.return_value = SimpleNamespace(result_rows=[(0,)])
    validator = GranularityValidator(db)
    result = validator.validate(make_candidate())[0]

    validator.store_results([result])

    assert db.command.call_count == 1
    assert db.insert.call_count == 1
    assert db.insert.call_args_list[0][0][0].endswith(".granularity_validations")
