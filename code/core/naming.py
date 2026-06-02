from __future__ import annotations

import re

COLUMN_NOISE_PATTERNS = (
    r"^id_",
    r"^fk_",
    r"^pk_",
    r"_id$",
    r"_fk$",
    r"_key$",
    r"id$",
    r"fk$",
    r"key$",
)

COLUMN_NOISE_REGEX = re.compile("|".join(COLUMN_NOISE_PATTERNS), re.IGNORECASE)


def normalize_column_name(column_name: str | None) -> str:
    """
    Normalize a column name before semantic comparison.

    Technical key markers such as id/fk/pk/key are removed, then separators are
    stripped so names like customer_id and CustomerKey can be compared fairly.
    """
    if not column_name:
        return ""

    name = column_name.strip().lower()

    previous_name = ""
    while name != previous_name:
        previous_name = name
        name = COLUMN_NOISE_REGEX.sub("", name)

    return name.replace("_", "").replace("-", "").strip()
