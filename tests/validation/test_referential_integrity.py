from types import SimpleNamespace
from unittest.mock import MagicMock

from modeling.decision_model import DecisionModelEdge
from validation.referential_integrity import ReferentialIntegrityValidator


def test_build_orphan_count_sql_supports_composite_edges() -> None:
    db = MagicMock()
    validator = ReferentialIntegrityValidator(db, database="lab_db")
    edge = DecisionModelEdge(
        source_table="sales",
        target_table="products",
        source_columns=("product_id", "variant_id"),
        target_columns=("product_id", "variant_id"),
        join_success_ratio=1.0,
        depth=1,
    )

    sql = validator.build_orphan_count_sql(edge)

    assert "FROM `lab_db`.`sales`" in sql
    assert "FROM `lab_db`.`products`" in sql
    assert "`product_id` AS c0" in sql
    assert "`variant_id` AS c1" in sql
    assert "s.c0 = t.c0 AND s.c1 = t.c1" in sql
    assert "t.c0 IS NULL AND t.c1 IS NULL" in sql


def test_count_orphans_returns_clickhouse_count() -> None:
    db = MagicMock()
    db.query.return_value = SimpleNamespace(result_rows=[(3,)])
    validator = ReferentialIntegrityValidator(db)
    edge = DecisionModelEdge(
        source_table="sales",
        target_table="customers",
        source_columns=("customer_id",),
        target_columns=("customer_id",),
        join_success_ratio=1.0,
        depth=1,
    )

    orphan_count = validator.count_orphans(edge)

    assert orphan_count == 3
