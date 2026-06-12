from __future__ import annotations

import re

TECHNICAL_KEY_TOKENS = {"id", "fk", "pk", "key"}
KEY_LIKE_TOKENS = TECHNICAL_KEY_TOKENS | {"no", "code"}
SEPARATOR_REGEX = re.compile(r"[_\-\s]+")
CAMELCASE_KEY_SUFFIX_REGEX = re.compile(r"(?<=[a-z0-9])(ID|Id|FK|Fk|PK|Pk|Key|No)$")


def normalize_column_name(column_name: str | None) -> str:
    """
    Normalize a column name before semantic comparison.

    Technical key markers such as id/fk/pk/key are removed, then separators are
    stripped so names like customer_id and CustomerKey can be compared fairly.
    """
    if not column_name:
        return ""

    name = CAMELCASE_KEY_SUFFIX_REGEX.sub(r"_\1", column_name.strip()).lower()
    tokens = [
        token
        for token in SEPARATOR_REGEX.split(name)
        if token and token not in TECHNICAL_KEY_TOKENS
    ]

    return "".join(tokens)


def split_column_name_tokens(column_name: str | None) -> tuple[str, ...]:
    """
    Split a column name into semantic tokens without stripping useful words.
    """
    if not column_name:
        return ()

    name = CAMELCASE_KEY_SUFFIX_REGEX.sub(r"_\1", column_name.strip())
    return tuple(
        token.lower()
        for token in SEPARATOR_REGEX.split(name)
        if token
    )


def is_key_like_column(column_name: str | None) -> bool:
    """
    Detect technical identifier columns without corrupting words like valid or rapid.
    """
    return any(token in KEY_LIKE_TOKENS for token in split_column_name_tokens(column_name))
