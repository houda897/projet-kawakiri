from core.naming import (
    is_key_like_column,
    is_partition_like_table_pair,
    normalize_column_name,
    normalize_key_concept,
    same_key_concept,
)


def test_is_key_like_column_detects_real_identifier_tokens() -> None:
    assert is_key_like_column("customer_id")
    assert is_key_like_column("ItemKey")
    assert is_key_like_column("ticket_no")
    assert is_key_like_column("status_code")


def test_is_key_like_column_avoids_semantic_false_positives() -> None:
    assert not is_key_like_column("valid")
    assert not is_key_like_column("paid")
    assert not is_key_like_column("rapid")
    assert not is_key_like_column("casino")
    assert not is_key_like_column("unicode")


def test_normalize_column_name_keeps_words_ending_like_keys() -> None:
    assert normalize_column_name("valid") == "valid"
    assert normalize_column_name("rapid") == "rapid"
    assert normalize_column_name("grid") == "grid"
    assert normalize_column_name("customer_id") == "customer"
    assert normalize_column_name("CustomerKey") == "customer"


def test_key_concept_preserves_business_level() -> None:
    assert normalize_key_concept("ItemKey") == "item"
    assert normalize_key_concept("ItemGroupKey") == "itemgroup"
    assert same_key_concept("ItemKey", "ItemKey")
    assert not same_key_concept("ItemKey", "ItemGroupKey")
    assert not same_key_concept("ItemSubgroupKey", "ItemGroupKey")
    assert not same_key_concept("ItemSubgroupKey", "GroupKey")


def test_key_concept_allows_more_specific_source_to_general_dimension_key() -> None:
    assert same_key_concept("OrderDate", "Date")
    assert same_key_concept("TerritoryKey", "SalesTerritoryKey")
    assert same_key_concept("ItemGroupKey", "GroupKey")


def test_generic_id_does_not_force_semantic_rejection() -> None:
    assert same_key_concept("customer_id", "id")


def test_partition_like_table_pair_detects_yearly_slices() -> None:
    assert is_partition_like_table_pair(
        "transactions_2021",
        "transactions_2022",
    )
    assert not is_partition_like_table_pair("sales", "sales_items")
