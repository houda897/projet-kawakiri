from core.clickhouse_manager import get_manager
from core.logger import get_logger
from core.schema import get_columns_name

logger = get_logger(__name__)


def check_functional_dependency(database, table, col_A, col_B, limit_violations: int = 2):
    """Check whether column A functionally determines column B (A -> B)."""
    q_table = f"`{database}`.`{table}`"
    q_B = f"`{col_B}`"

    query_check = f"""
    SELECT
        {q_A} AS valeur_A,
        uniqExact({q_B}) AS nb_valeurs_B_differentes
    FROM {q_table}
    GROUP BY {q_A_group}
    HAVING nb_valeurs_B_differentes > 1
    ORDER BY nb_valeurs_B_differentes DESC
    LIMIT {limit_violations}
    """

    db = get_manager()
    df_violations = db.queryDf(query_check)

    if df_violations.empty:
        return True
    else:
        return False


def analyze_table_dependencies(database, table, col_name):
    """
    Check whether col_name has a functional dependency with every other column.
    Returns True if col_name is a valid primary-key candidate, False otherwise.
    """
    db = get_manager()
    all_columns = get_columns_name(db, database, table)
    other_columns = [col for col in all_columns if col != col_name]

    for target_column in other_columns:
        if check_functional_dependency(database, table, col_name, target_column):
            continue
        else:
            return False

    return True
