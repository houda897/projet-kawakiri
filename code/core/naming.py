from __future__ import annotations

import re

TECHNICAL_KEY_TOKENS = {"id", "fk", "pk", "key"}
KEY_LIKE_TOKENS = TECHNICAL_KEY_TOKENS | {"no", "code", "ref"}
SEPARATOR_REGEX = re.compile(r"[_\-\s]+")
CAMELCASE_KEY_SUFFIX_REGEX = re.compile(r"(?<=[a-z0-9])(ID|Id|FK|Fk|PK|Pk|Key|No|Ref)$")
CAMELCASE_BOUNDARY_REGEX = re.compile(r"(?<=[a-z0-9])(?=[A-Z])")
YEAR_TOKEN_REGEX = re.compile(r"^(?:19|20)\d{2}$")


def normalize_column_name(column_name: str | None) -> str:
    """
    Normalize a column name before semantic comparison.

    Technical key markers such as id/fk/pk/key are removed, then separators are
    stripped so equivalent key spellings can be compared consistently.
    """
    if not column_name:
        return ""

    name = CAMELCASE_KEY_SUFFIX_REGEX.sub(r"_\1", column_name.strip())
    tokens = [
        token
        for token in _split_name_tokens(name)
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
    return tuple(token for token in _split_name_tokens(name) if token)


def _split_name_tokens(name: str) -> tuple[str, ...]:
    separated = CAMELCASE_BOUNDARY_REGEX.sub("_", name)
    return tuple(token.lower() for token in SEPARATOR_REGEX.split(separated) if token)


def is_key_like_column(column_name: str | None) -> bool:
    """
    Detect technical identifier columns without corrupting words like valid or rapid.
    """
    return any(token in KEY_LIKE_TOKENS for token in split_column_name_tokens(column_name))


def normalize_key_concept(column_name: str | None) -> str:
    """
    Return the normalized semantic concept carried by a key-like column.

    The concept is derived from semantic tokens rather than delegated to the
    generic column normalizer. This keeps identifier markers out of the concept
    while preserving meaningful hierarchy tokens used by join validation.
    """
    return "".join(normalize_key_concept_tokens(column_name))


def normalize_key_concept_tokens(column_name: str | None) -> tuple[str, ...]:
    """
    Return semantic tokens for a key concept, without identifier markers.
    """
    return tuple(
        token
        for token in split_column_name_tokens(column_name)
        if token not in KEY_LIKE_TOKENS
    )


def same_key_concept(left_column: str | None, right_column: str | None) -> bool:
    """
    Return True when two key columns can reasonably identify the same concept.

    Generic keys such as "id" do not carry enough semantic information on their
    own, so they are not rejected here. Otherwise, concepts must either match
    exactly or share the same terminal hierarchy tokens. This allows contextual
    names to point to a general dimension key while rejecting joins across
    different semantic hierarchy levels.
    """
    left_tokens = normalize_key_concept_tokens(left_column)
    right_tokens = normalize_key_concept_tokens(right_column)

    if not left_tokens or not right_tokens:
        return True

    if left_tokens == right_tokens:
        return True

    shortest = min(len(left_tokens), len(right_tokens))
    return left_tokens[-shortest:] == right_tokens[-shortest:]


def is_partition_like_table_pair(left_table: str | None, right_table: str | None) -> bool:
    """
    Detect tables that look like temporal partitions of the same logical table.

    Such tables often share key domains but represent slices of the same entity
    or fact process, not a parent-child dimensional relationship.
    """
    left_tokens = split_column_name_tokens(left_table)
    right_tokens = split_column_name_tokens(right_table)

    if not left_tokens or not right_tokens or left_tokens == right_tokens:
        return False

    left_without_year = tuple(token for token in left_tokens if not YEAR_TOKEN_REGEX.match(token))
    right_without_year = tuple(token for token in right_tokens if not YEAR_TOKEN_REGEX.match(token))

    if not left_without_year or left_without_year != right_without_year:
        return False

    return left_tokens != left_without_year and right_tokens != right_without_year
