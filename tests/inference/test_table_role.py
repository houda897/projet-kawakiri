from inference.table_role import TableRoleEngine


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


def test_classify_table_as_dimension_isolated() -> None:
    role, confidence, reason = TableRoleEngine.classify_table(
        row_count=10,
        outgoing_edges=0,
        incoming_edges=0,
        has_primary_key=True,
        numeric_columns=1,
        text_columns=3,
        date_columns=0,
    )
    assert role == "DIMENSION"
    assert confidence == 0.65
    assert "few_confirmed_links" in reason


def test_classify_table_unknown() -> None:
    role, confidence, reason = TableRoleEngine.classify_table(
        row_count=50,
        outgoing_edges=0,
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
