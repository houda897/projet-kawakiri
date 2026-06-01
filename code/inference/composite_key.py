from __future__ import annotations

from collections import defaultdict
from typing import TYPE_CHECKING

from config.scoring import PK_WEIGHTS
from core.clickhouse_manager import META_DB, clickhouse_manager
from core.logger import get_logger
from core.schema import q_ident
from stats.functional_dependency import check_functional_dependency

from inference.key_ranking import KeyRankingPolicy, RankedKeyCandidate

if TYPE_CHECKING:
    from inference.primary_key import PrimaryKeyCandidate

logger = get_logger(__name__)


class CompositeKeyEngine:
    """
    Generate composite-key candidates for tables without a simple primary key.
    """

    def __init__(self, db: clickhouse_manager):
        self.db = db
        self.ranking_policy = KeyRankingPolicy()

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

            current_combo = []

            for column in table_columns:
                current_combo.append(column)

                if len(current_combo) < 2:
                    continue

                combo_names = tuple(col.column_name for col in current_combo)
                combo_types = tuple(col.column_type for col in current_combo)
                database_name = current_combo[0].database_name

                logger.info("Testing composite key for %s: %s", table, combo_names)

                is_valid = check_functional_dependency(
                    database_name,
                    table,
                    list(combo_names),
                    self.db,
                )

                if not is_valid:
                    continue

                logger.info("Composite key found for %s: %s", table, combo_names)

                cleaned_combo = list(current_combo)
                
                columns_to_test = sorted(
                    current_combo, 
                    key=lambda col: col.identifiability_score
                )
                
                for col_to_test in columns_to_test:
                    test_combo = [c for c in cleaned_combo if c != col_to_test]
                    
                    if len(test_combo) >= 2:
                        test_names = [c.column_name for c in test_combo]
                        
                        if check_functional_dependency(database_name, table, test_names, self.db):
                            cleaned_combo = test_combo

                current_combo = cleaned_combo
                combo_names = tuple(col.column_name for col in current_combo)
                combo_types = tuple(col.column_type for col in current_combo)

                logger.info("Final composite key for %s after pruning: %s\n", table, combo_names)

                composite_candidates.append(
                    self.ranking_policy.build_candidate(
                        database_name=database_name,
                        table_name=table,
                        column_names=combo_names,
                        column_types=combo_types,
                        rows=current_combo[0].rows,
                        null_ratio=max(col.null_ratio for col in current_combo),
                        uniqueness_ratio=1.0,
                        identifiability_score=sum(
                            col.identifiability_score for col in current_combo
                        )
                        / len(current_combo),
                        low_cardinality_columns=low_cardinality_columns,
                    )
                )

                break

        return composite_candidates

    def load_columns_for_composite_search(self) -> list[PrimaryKeyCandidate]:
        """
        Load column evidence used to build composite-key candidates.
        """

        from inference.primary_key import PrimaryKeyCandidate

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
        WHERE p.null_ratio <= 0.000001
          AND NOT startsWith(p.column_name, '__')
        ORDER BY p.table_name, p.column_name
        """

        rows = self.db.query(sql).result_rows
        columns = []

        for row in rows:
            confidence = round(PK_WEIGHTS["uniqueness"] * row[6]
    + PK_WEIGHTS["identifiability"] * row[7],
    6,)

            columns.append(
                PrimaryKeyCandidate(
                    database_name=row[0],
                    table_name=row[1],
                    column_name=row[2],
                    column_type=row[3],
                    rows=row[4],
                    null_ratio=row[5],
                    uniqueness_ratio=row[6],
                    identifiability_score=row[7],
                    confidence=confidence,
                    reason="column_evidence_for_composite_key_search",
                )
            )

        return columns
