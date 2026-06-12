from core.naming import is_key_like_column, normalize_column_name


def test_is_key_like_column_detects_real_identifier_tokens() -> None:
    assert is_key_like_column("customer_id")
    assert is_key_like_column("ProductKey")
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
