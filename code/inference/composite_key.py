from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from itertools import combinations

from config.scoring import PK_WEIGHTS
from core.clickhouse_manager import CH_DB, META_DB, ClickHouseManager
from core.logger import get_logger
from core.schema import q_ident
from inference.key_ranking import KeyRankingPolicy, RankedKeyCandidate
from stats.functional_dependency import check_functional_dependency

logger = get_logger(__name__)


@dataclass(frozen=True)
class CompositeKeyColumnEvidence:
    """
    Column-level evidence used only during composite-key search.
    """

    database_name: str
    table_name: str
    column_name: str
    column_type: str
    rows: int
    null_ratio: float
    uniqueness_ratio: float
    identifiability_score: float
    confidence: float


class CompositeKeyEngine:
    """
    Generate composite-key candidates for tables without a simple primary key.
    """

    def __init__(self, db: ClickHouseManager):
        self.db = db
        self.ranking_policy = KeyRankingPolicy()

    @staticmethod
    def find_minimal_composite_key(
        database_name: str,
        table_name: str,
        candidate_columns: list[str],
        db: ClickHouseManager,
    ) -> tuple[str, ...]:
        """Return the smallest unique column combination in deterministic order."""
        columns = tuple(dict.fromkeys(candidate_columns))
        if len(columns) < 2:
            return ()

        # First find an upper bound cheaply. The exhaustive search then only
        # explores widths that can improve that bound.
        upper_bound = 0
        for width in range(2, len(columns) + 1):
            if check_functional_dependency(
                database_name,
                table_name,
                list(columns[:width]),
                db,
            ):
                upper_bound = width
                break

        if upper_bound == 0:
            return ()

        for width in range(2, upper_bound + 1):
            for candidate in combinations(columns, width):
                if check_functional_dependency(
                    database_name,
                    table_name,
                    list(candidate),
                    db,
                ):
                    return candidate

        return ()

    def generate_composite_candidates(
        self,
        tables_without_pk: list[str],
        low_cardinality_columns: set[tuple[str, str]],
    ) -> list[RankedKeyCandidate]:
        """
        Propose composite candidates, but do not make the final PK decision.
        """

        all_columns = self.load_columns_for_composite_search()
        columns_by_table = defaultdict(list)

        for column in all_columns:
            columns_by_table[column.table_name].append(column)

        composite_candidates = []

        for table in tables_without_pk:
            table_columns = columns_by_table.get(table, [])

            if len(table_columns) < 2:
                continue

            table_columns.sort(
                key=lambda column: (
                    column.confidence,
                    column.uniqueness_ratio,
                    column.identifiability_score,
                ),
                reverse=True,
            )

            database_name = table_columns[0].database_name
            evidence_by_name = {column.column_name: column for column in table_columns}
            combo_names = self.find_minimal_composite_key(
                database_name,
                table,
                [column.column_name for column in table_columns],
                self.db,
            )
            if not combo_names:
                continue

            current_combo = [evidence_by_name[column] for column in combo_names]
            combo_types = tuple(column.column_type for column in current_combo)
            logger.info("Final composite key for %s: %s\n", table, combo_names)

            composite_candidates.append(
                self.ranking_policy.build_candidate(
                    database_name=database_name,
                    table_name=table,
                    column_names=combo_names,
                    column_types=combo_types,
                    rows=current_combo[0].rows,
                    null_ratio=max(col.null_ratio for col in current_combo),
                    uniqueness_ratio=1.0,
                    identifiability_score=sum(col.identifiability_score for col in current_combo)
                    / len(current_combo),
                    low_cardinality_columns=low_cardinality_columns,
                )
            )

        return composite_candidates

    def load_columns_for_composite_search(self) -> list[CompositeKeyColumnEvidence]:
        """
        Load column evidence used to build composite-key candidates.
        """

        sql = f"""
        SELECT
            p.database_name,
            p.table_name,
            p.column_name,
            p.column_type,
            p.rows,
            p.null_ratio,
            p.uniqueness_ratio,
            coalesce(i.identifiability_score, 0.0) AS identifiability_score
        FROM {q_ident(META_DB)}.column_profiles AS p
        LEFT JOIN {q_ident(META_DB)}.identifiability_scores AS i
            ON p.database_name = i.database_name
           AND p.table_name = i.table_name
           AND p.column_name = i.column_name
        WHERE p.database_name = %(database)s
          AND p.null_rows = 0
          AND NOT startsWith(p.column_name, '__')
        ORDER BY p.table_name, p.column_name
        """

        rows = self.db.query(sql, parameters={"database": CH_DB}).result_rows
        columns = []

        for row in rows:
            confidence = round(
                PK_WEIGHTS["uniqueness"] * row[6] + PK_WEIGHTS["identifiability"] * row[7],
                6,
            )

            columns.append(
                CompositeKeyColumnEvidence(
                    database_name=row[0],
                    table_name=row[1],
                    column_name=row[2],
                    column_type=row[3],
                    rows=row[4],
                    null_ratio=row[5],
                    uniqueness_ratio=row[6],
                    identifiability_score=row[7],
                    confidence=confidence,
                )
            )

        return columns
