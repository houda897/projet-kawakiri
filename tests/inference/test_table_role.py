from types import SimpleNamespace
from unittest.mock import MagicMock

from inference.table_role import TableRoleCandidate, TableRoleEngine


def test_classify_table_as_fact() -> None:
    role, confidence, reason = TableRoleEngine.classify_table(
        row_count=100,
        outgoing_edges=2,
        incoming_edges=0,
        has_primary_key=True,
        numeric_columns=4,
        text_columns=1,
        date_columns=0,
    )
    assert role == "FACT"
    assert confidence == 0.85
    assert "many_links_and_mostly_numeric_columns" in reason


def test_classify_table_as_dimension_with_incoming() -> None:
    role, confidence, reason = TableRoleEngine.classify_table(
        row_count=50,
        outgoing_edges=0,
        incoming_edges=2,
        has_primary_key=True,
        numeric_columns=1,
        text_columns=3,
        date_columns=0,
    )
    assert role == "DIMENSION"
    assert confidence == 0.85
    assert "referenced_by_other_tables" in reason


def test_classify_table_as_isolated_without_confirmed_relationships() -> None:
    role, confidence, reason = TableRoleEngine.classify_table(
        row_count=10,
        outgoing_edges=0,
        incoming_edges=0,
        has_primary_key=True,
        numeric_columns=1,
        text_columns=3,
        date_columns=0,
    )
    assert role == "ISOLATED"
    assert confidence == 0.9
    assert "no_confirmed_relationships" in reason


def test_classify_table_without_links_is_isolated_even_without_primary_key() -> None:
    role, confidence, reason = TableRoleEngine.classify_table(
        row_count=50,
        outgoing_edges=0,
        incoming_edges=0,
        has_primary_key=False,
        numeric_columns=1,
        text_columns=3,
        date_columns=0,
    )
    assert role == "ISOLATED"
    assert confidence == 0.9
    assert "no_confirmed_relationships" in reason


def test_classify_table_unknown_when_linked_evidence_is_inconclusive() -> None:
    role, confidence, reason = TableRoleEngine.classify_table(
        row_count=50,
        outgoing_edges=1,
        incoming_edges=0,
        has_primary_key=False,
        numeric_columns=1,
        text_columns=3,
        date_columns=0,
    )
    assert role == "UNKNOWN"
    assert confidence == 0.4
    assert "not_enough_evidence" in reason


def test_classify_table_small_fact_fallback() -> None:
    # A table with outgoing edges but < 5 rows should not be a FACT table.
    role, confidence, reason = TableRoleEngine.classify_table(
        row_count=2,
        outgoing_edges=3,
        incoming_edges=0,
        has_primary_key=False,
        numeric_columns=4,
        text_columns=1,
        date_columns=0,
    )
    assert role == "UNKNOWN"


def test_classify_linked_descriptive_table_as_dimension() -> None:
    role, confidence, reason = TableRoleEngine.classify_table(
        row_count=100,
        outgoing_edges=2,
        incoming_edges=1,
        has_primary_key=True,
        numeric_columns=2,
        text_columns=4,
        date_columns=0,
    )

    assert role == "DIMENSION"
    assert confidence == 0.75
    assert "mostly_descriptive_columns" in reason


def test_classify_transactional_table_as_fact_with_additive_measure() -> None:
    role, confidence, reason = TableRoleEngine.classify_table(
        row_count=1000,
        outgoing_edges=2,
        incoming_edges=0,
        has_primary_key=True,
        numeric_columns=2,
        text_columns=4,
        date_columns=0,
        additive_measure_columns=1,
        has_transactional_grain=True,
        is_lookup_table=False,
    )

    assert role == "FACT"
    assert confidence == 0.8
    assert "transactional_grain" in reason


def test_classify_quantitative_source_table_with_single_outgoing_link_as_fact() -> None:
    role, confidence, reason = TableRoleEngine.classify_table(
        row_count=2155,
        outgoing_edges=1,
        incoming_edges=0,
        has_primary_key=True,
        numeric_columns=5,
        text_columns=0,
        date_columns=0,
        additive_measure_columns=1,
        has_transactional_grain=True,
        is_lookup_table=False,
    )

    assert role == "FACT"
    assert confidence == 0.8
    assert "quantitative_grain" in reason


def test_classify_lookup_table_does_not_become_fact() -> None:
    role, confidence, reason = TableRoleEngine.classify_table(
        row_count=37,
        outgoing_edges=2,
        incoming_edges=2,
        has_primary_key=True,
        numeric_columns=2,
        text_columns=1,
        date_columns=0,
        additive_measure_columns=0,
        has_transactional_grain=True,
        is_lookup_table=True,
    )

    assert role == "DIMENSION"
    assert confidence == 0.85
    assert "referenced_by_other_tables" in reason


def test_is_additive_measure_column_rejects_keys_and_flat_counters() -> None:
    assert (
        TableRoleEngine.is_additive_measure_column(
            column_name="ProductKey",
            column_type="Int64",
            distinct_count=100,
            entropy_ratio=0.9,
            variation_coefficient=0.5,
            uniqueness_ratio=0.8,
        )
        is False
    )
    assert (
        TableRoleEngine.is_additive_measure_column(
            column_name="OrderLineItem",
            column_type="Int64",
            distinct_count=1,
            entropy_ratio=0.0,
            variation_coefficient=0.0,
            uniqueness_ratio=0.0,
        )
        is False
    )
    assert (
        TableRoleEngine.is_additive_measure_column(
            column_name="revenue",
            column_type="Float64",
            distinct_count=20,
            entropy_ratio=0.6,
            variation_coefficient=0.4,
            uniqueness_ratio=0.2,
        )
        is True
    )


def test_store_roles_persists_inferred_roles() -> None:
    db = MagicMock()
    engine = TableRoleEngine(db)
    roles = [
        TableRoleCandidate(
            table_name="sales",
            row_count=100,
            outgoing_edges=2,
            incoming_edges=0,
            numeric_columns=4,
            text_columns=1,
            date_columns=0,
            has_primary_key=True,
            role="FACT",
            confidence=0.85,
            reason="table_has_many_links_and_mostly_numeric_columns",
        )
    ]

    engine.store_roles(roles)

    db.command.assert_called_once()
    db.insert.assert_called_once()
    assert db.insert.call_args[0][0].endswith(".table_roles")


def test_load_roles_reads_stored_roles() -> None:
    db = MagicMock()
    db.query.return_value = SimpleNamespace(
        result_rows=[
            (
                "sales",
                100,
                2,
                0,
                4,
                1,
                0,
                True,
                "FACT",
                0.85,
                "table_has_many_links_and_mostly_numeric_columns",
            )
        ]
    )
    engine = TableRoleEngine(db)

    roles = engine.load_roles()

    assert len(roles) == 1
    assert roles[0].table_name == "sales"
    assert roles[0].role == "FACT"
    assert roles[0].confidence == 0.85


def test_infer_roles_combines_graph_profiles_and_logical_evidence() -> None:
    engine = TableRoleEngine(MagicMock())
    engine.load_table_row_counts = MagicMock(return_value={"fact_sales": 1000, "dim_customer": 100})
    engine.load_primary_key_tables = MagicMock(return_value={"fact_sales", "dim_customer"})
    engine.load_outgoing_edges = MagicMock(return_value={"fact_sales": 1})
    engine.load_incoming_edges = MagicMock(return_value={"dim_customer": 1})
    engine.load_column_type_counts = MagicMock(
        return_value={
            "fact_sales": {"numeric": 3, "text": 1, "date": 1},
            "dim_customer": {"numeric": 1, "text": 3, "date": 0},
        }
    )
    engine.load_additive_measure_counts = MagicMock(return_value={"fact_sales": 1})
    engine.load_transactional_grain_tables = MagicMock(return_value={"fact_sales"})
    engine.load_logical_table_roles = MagicMock(
        return_value={
            "fact_sales": "FACT_CANDIDATE",
            "dim_customer": "DIMENSION_CANDIDATE",
        }
    )

    roles = engine.infer_roles()

    assert [role.table_name for role in roles] == ["dim_customer", "fact_sales"]
    assert {role.table_name: role.role for role in roles} == {
        "fact_sales": "FACT",
        "dim_customer": "DIMENSION",
    }


def test_is_lookup_table_requires_reference_shape_without_measure() -> None:
    assert TableRoleEngine.is_lookup_table(50, 0, 1, True, 1, 3, 0) is True
    assert TableRoleEngine.is_lookup_table(50, 0, 1, False, 1, 3, 0) is False
    assert TableRoleEngine.is_lookup_table(50, 0, 1, True, 1, 3, 1) is False


def test_role_from_logical_table_preserves_ambiguous_role() -> None:
    assert TableRoleEngine.role_from_logical_table("FACT_CANDIDATE")[0] == "FACT"
    assert TableRoleEngine.role_from_logical_table("DIMENSION_CANDIDATE")[0] == "DIMENSION"
    assert TableRoleEngine.role_from_logical_table("UNKNOWN_CANDIDATE")[0] == "UNKNOWN"
