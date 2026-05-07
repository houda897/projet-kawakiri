import math


def entropy_ratio(entropy: float, non_null_rows: int) -> float:
    if non_null_rows <= 1:
        return 0.0
    return entropy / math.log2(non_null_rows)


def uniqueness_ratio(distinct_count: int, non_null_rows: int) -> float:
    if non_null_rows == 0:
        return 0.0
    return distinct_count / non_null_rows


def completeness_ratio(non_null_rows: int, rows: int) -> float:
    if rows == 0:
        return 0.0
    return non_null_rows / rows


def validate_entropy_rule(
    entropy: float,
    rows: int,
    non_null_rows: int,
    distinct_count: int,
    threshold: float = 0.95,
) -> dict:
    h_ratio = entropy_ratio(entropy, non_null_rows)
    u_ratio = uniqueness_ratio(distinct_count, non_null_rows)
    c_ratio = completeness_ratio(non_null_rows, rows)

    is_valid = (
        h_ratio >= threshold
        and u_ratio >= threshold
        and c_ratio >= threshold
    )

    return {
        "entropy_ratio": round(h_ratio, 4),
        "uniqueness_ratio": round(u_ratio, 4),
        "completeness_ratio": round(c_ratio, 4),
        "is_valid_dimension_key": is_valid,
        "threshold": threshold,
    }
# Ajoute la complétude pour éviter de valider comme clé une colonne presque entièrement NULL.
