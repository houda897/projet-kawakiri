from inference.table_role import TableRoleEngine


def test_classify_table_as_fact() -> None:
    role, confidence, reason = TableRoleEngine.classify_table(
        row_count=100,
        outgoing_edges=2,
        incoming_edges=0,
        has_primary_key=True,
    )
    assert role == "FACT"
    assert confidence == 0.85
    assert "many_rows_and_multiple_links" in reason


def test_classify_table_as_dimension_with_incoming() -> None:
    role, confidence, reason = TableRoleEngine.classify_table(
        row_count=50,
        outgoing_edges=0,
        incoming_edges=2,
        has_primary_key=True,
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
    )
    assert role == "UNKNOWN"
