from types import SimpleNamespace
from unittest.mock import MagicMock

from generation.sql_view_generator import CertifiedModel, SQLViewGenerator


def test_load_best_certified_model_reads_certification_metadata() -> None:
    db = MagicMock()
    db.query.return_value = SimpleNamespace(
        result_rows=[
            ("star_sales", "VALID", "STAR", "sales,returns"),
        ]
    )
    generator = SQLViewGenerator(db)

    model = generator.load_best_certified_model()

    assert model == CertifiedModel(
        model_id="star_sales",
        model_type="STAR",
        status="VALID",
        fact_tables=("sales", "returns"),
    )
    sql = db.query.call_args[0][0]
    assert "model_certifications" in sql
    assert "decision_model_candidates" in sql


def test_load_best_certified_model_requires_certification() -> None:
    db = MagicMock()
    db.query.return_value = SimpleNamespace(result_rows=[])
    generator = SQLViewGenerator(db)

    try:
        generator.load_best_certified_model()
    except ValueError as exc:
        assert "Run certify-models" in str(exc)
    else:
        raise AssertionError("Expected ValueError when no certified model exists")


def test_load_model_edges_reads_only_the_selected_model_edges() -> None:
    db = MagicMock()
    db.query.return_value = SimpleNamespace(
        result_rows=[
            ("sales", "customers", "customer_id", "customer_id", 1.0, 1),
            ("customers", "countries", "country_id", "country_id", 1.0, 2),
        ]
    )
    generator = SQLViewGenerator(db)

    edges = generator.load_model_edges("snowflake_sales")

    assert edges == [
        {
            "source_table": "sales",
            "target_table": "customers",
            "source_columns": "customer_id",
            "target_columns": "customer_id",
            "join_success_ratio": 1.0,
            "depth": 1,
        },
        {
            "source_table": "customers",
            "target_table": "countries",
            "source_columns": "country_id",
            "target_columns": "country_id",
            "join_success_ratio": 1.0,
            "depth": 2,
        },
    ]
    assert db.query.call_args.kwargs["parameters"]["model_id"] == "snowflake_sales"


def test_generate_views_uses_the_best_certified_model() -> None:
    db = MagicMock()
    generator = SQLViewGenerator(db)
    generator.load_best_certified_model = MagicMock(
        return_value=CertifiedModel(
            model_id="snowflake_sales",
            model_type="SNOWFLAKE",
            status="VALID",
            fact_tables=("sales",),
        )
    )
    generator.load_model_edges = MagicMock(
        return_value=[
            {
                "source_table": "sales",
                "target_table": "customers",
                "source_columns": "customer_id",
                "target_columns": "customer_id",
                "join_success_ratio": 1.0,
                "depth": 1,
            },
            {
                "source_table": "customers",
                "target_table": "countries",
                "source_columns": "country_id",
                "target_columns": "country_id",
                "join_success_ratio": 1.0,
                "depth": 2,
            },
        ]
    )

    views = generator.generate_views()

    assert len(views) == 1
    assert views[0].fact_table == "sales"
    assert "LEFT JOIN" in views[0].sql
    assert "`customers`" in views[0].sql
    assert "`countries`" in views[0].sql
    assert "d1.`country_id` = d2.`country_id`" in views[0].sql


def test_select_edges_for_star_keeps_only_direct_fact_edges() -> None:
    generator = SQLViewGenerator(db=MagicMock())
    model = CertifiedModel(
        model_id="star_sales",
        model_type="STAR",
        status="VALID",
        fact_tables=("sales",),
    )
    edges = [
        {
            "source_table": "sales",
            "target_table": "customers",
            "source_columns": "customer_id",
            "target_columns": "customer_id",
            "join_success_ratio": 1.0,
            "depth": 1,
        },
        {
            "source_table": "customers",
            "target_table": "countries",
            "source_columns": "country_id",
            "target_columns": "country_id",
            "join_success_ratio": 1.0,
            "depth": 2,
        },
    ]

    selected = generator.select_edges_for_view(model, "sales", edges)

    assert len(selected) == 1
    assert selected[0]["target_table"] == "customers"


def test_select_edges_for_view_deduplicates_same_source_target_link() -> None:
    generator = SQLViewGenerator(db=MagicMock())
    model = CertifiedModel(
        model_id="star_sales",
        model_type="STAR",
        status="VALID",
        fact_tables=("sales",),
    )
    edges = [
        {
            "source_table": "sales",
            "target_table": "customers",
            "source_columns": "order_id",
            "target_columns": "customer_id",
            "join_success_ratio": 0.7,
            "depth": 1,
        },
        {
            "source_table": "sales",
            "target_table": "customers",
            "source_columns": "customer_id",
            "target_columns": "customer_id",
            "join_success_ratio": 1.0,
            "depth": 1,
        },
    ]

    selected = generator.select_edges_for_view(model, "sales", edges)
    sql = generator.build_view_sql("sales", selected)

    assert len(selected) == 1
    assert selected[0]["source_columns"] == "customer_id"
    assert sql.count("JOIN") == 1
    assert sql.count(" AS d1") == 1


def test_build_view_sql_joins_snowflake_edges_from_dimension_alias() -> None:
    generator = SQLViewGenerator(db=MagicMock())

    sql = generator.build_view_sql(
        fact_table="sales",
        edges=[
            {
                "source_table": "sales",
                "target_table": "customers",
                "source_columns": "customer_id",
                "target_columns": "customer_id",
                "join_success_ratio": 1.0,
                "depth": 1,
            },
            {
                "source_table": "customers",
                "target_table": "countries",
                "source_columns": "country_id",
                "target_columns": "country_id",
                "join_success_ratio": 1.0,
                "depth": 2,
            },
        ],
    )

    assert "`.`customers` AS d1" in sql
    assert "`.`countries` AS d2" in sql
    assert "f.`customer_id` = d1.`customer_id`" in sql
    assert "d1.`country_id` = d2.`country_id`" in sql


def test_load_table_roles_reads_stored_metadata() -> None:
    db = MagicMock()
    db.query.return_value = SimpleNamespace(
        result_rows=[
            ("sales", "FACT"),
            ("customers", "DIMENSION"),
        ]
    )
    generator = SQLViewGenerator(db)

    roles = generator.load_table_roles()

    assert roles == {
        "sales": "FACT",
        "customers": "DIMENSION",
    }
    sql = db.query.call_args[0][0]
    assert "table_roles" in sql


def test_load_table_roles_requires_stored_roles() -> None:
    db = MagicMock()
    db.query.return_value = SimpleNamespace(result_rows=[])
    generator = SQLViewGenerator(db)

    try:
        generator.load_table_roles()
    except ValueError as exc:
        assert "Run infer-table-roles" in str(exc)
    else:
        raise AssertionError("Expected ValueError when stored table roles are missing")
