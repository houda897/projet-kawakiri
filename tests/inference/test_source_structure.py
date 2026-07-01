from inference.join_candidate import JoinPrimaryKeyCandidate
from inference.primary_key import PrimaryKeyCandidate
from inference.source_structure import SourceStructureAnalyzer


def make_key(table: str, column: str) -> PrimaryKeyCandidate:
    return PrimaryKeyCandidate(
        database_name="db",
        table_name=table,
        column_name=column,
        column_type="String",
        rows=100,
        null_ratio=0.0,
        uniqueness_ratio=1.0,
        identifiability_score=0.9,
        confidence=0.93,
        reason="exact",
        analysis_scope="SOURCE",
        is_official=False,
    )


def make_join(source: str, column: str, target: str) -> JoinPrimaryKeyCandidate:
    return JoinPrimaryKeyCandidate(
        source_table=source,
        source_column=column,
        target_table=target,
        target_column=column,
        source_non_null_rows=100,
        matched_rows=100,
        join_success_ratio=1.0,
        analysis_scope="SOURCE",
    )


def test_entity_key_is_the_candidate_owned_by_the_table() -> None:
    keys = [
        make_key("orders", "order_id"),
        make_key("orders", "customer_id"),
        make_key("customers", "customer_id"),
    ]
    joins = [
        make_join("items", "order_id", "orders"),
        make_join("payments", "order_id", "orders"),
        make_join("reviews", "order_id", "orders"),
        make_join("orders", "customer_id", "customers"),
        make_join("customers", "customer_id", "orders"),
    ]

    structures = SourceStructureAnalyzer.build_structures(keys, joins)

    assert structures["orders"].entity_key.column_name == "order_id"
    assert structures["customers"].entity_key.column_name == "customer_id"
    assert {edge.source_table for edge in structures["orders"].incoming_relationships} == {
        "items",
        "payments",
        "reviews",
    }
    assert {edge.target_table for edge in structures["orders"].outgoing_relationships} == {
        "customers"
    }


def test_foreign_unique_address_does_not_beat_referenced_entity_key() -> None:
    keys = [
        make_key("partners", "partner_id"),
        make_key("partners", "address_id"),
        make_key("addresses", "address_id"),
    ]
    joins = [
        make_join("sales", "partner_id", "partners"),
        make_join("products", "partner_id", "partners"),
        make_join("partners", "address_id", "addresses"),
        make_join("addresses", "address_id", "partners"),
    ]

    selected = SourceStructureAnalyzer.select_entity_keys(keys, joins)

    assert selected["partners"].column_name == "partner_id"
