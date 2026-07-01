from __future__ import annotations

from typing import TYPE_CHECKING

from core.clickhouse_manager import ClickHouseManager, get_manager
from core.logger import get_logger
from core.schema import q_ident

if TYPE_CHECKING:
    from inference.primary_key import PrimaryKeyCandidate

logger = get_logger(__name__)


def check_functional_dependency(
    database: str,
    table: str,
    pk_candidate: str | list[str],
    db_manager: ClickHouseManager,
) -> bool:
    """
    Check whether a single-column or composite candidate uniquely identifies rows.
    """

    columns = pk_candidate if isinstance(pk_candidate, list) else [pk_candidate]
    q_table = f"{q_ident(database)}.{q_ident(table)}"
    q_cols = ", ".join(q_ident(column) for column in columns)

    query_check = f"""
    SELECT {q_cols}, count() AS duplicate_count
    FROM {q_table}
    GROUP BY {q_cols}
    HAVING duplicate_count > 1
    LIMIT 1
    """

    result = db_manager.query(query_check)

    return len(result.result_rows) == 0


def check_column_dependency(
    database: str,
    table: str,
    determinant_columns: str | list[str],
    dependent_column: str,
    db_manager: ClickHouseManager,
    max_violations: int = 0,
) -> bool:
    """
    Check whether determinant columns functionally determine one dependent column.

    A dependency A -> B is valid when each distinct value of A maps to at most
    one distinct non-null value of B.
    """

    determinants = (
        determinant_columns if isinstance(determinant_columns, list) else [determinant_columns]
    )
    determinant_sql = ", ".join(q_ident(column) for column in determinants)
    dependent_sql = q_ident(dependent_column)
    null_filter = " AND ".join(q_ident(column) + " IS NOT NULL" for column in determinants)
    q_table = f"{q_ident(database)}.{q_ident(table)}"

    query_check = f"""
    SELECT {determinant_sql}
    FROM {q_table}
    WHERE {null_filter}
      AND {dependent_sql} IS NOT NULL
    GROUP BY {determinant_sql}
    HAVING uniqExact({dependent_sql}) > 1
    LIMIT %(limit)s
    """

    result = db_manager.query(query_check, parameters={"limit": max_violations + 1})
    return len(result.result_rows) <= max_violations


def validate_dependency(candidates_list: list[PrimaryKeyCandidate]) -> list[PrimaryKeyCandidate]:
    new_candidates = candidates_list.copy()
    logger.info("Validating functional dependencies for %s candidates...", len(candidates_list))
    db_manager = get_manager()

    for candidate in candidates_list:
        is_valid = check_functional_dependency(
            candidate.database_name,
            candidate.table_name,
            candidate.column_name,
            db_manager,
        )

        if not is_valid:
            new_candidates.remove(candidate)

    logger.info(f"Keys removed : {len(candidates_list) - len(new_candidates)}")
    return new_candidates
