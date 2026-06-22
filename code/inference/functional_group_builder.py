from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass
from itertools import combinations

from config.scoring import FUNCTIONAL_GROUPING_SETTINGS
from core.clickhouse_manager import CH_DB, META_DB, ClickHouseManager
from core.logger import get_logger
from core.meta import clear_metadata_table
from core.schema import q_ident
from stats.functional_dependency import check_column_dependency

logger = get_logger(__name__)

MEASURE_NAME_TOKENS = (
    "amount",
    "cost",
    "discount",
    "freight",
    "price",
    "quantity",
    "qty",
    "rate",
    "revenue",
    "sales",
    "tax",
    "total",
    "value",
)


@dataclass(frozen=True)
class FunctionalColumnProfile:
    table_name: str
    column_name: str
    column_type: str
    rows: int
    null_ratio: float
    distinct_count: int
    uniqueness_ratio: float
    identifiability_score: float


@dataclass(frozen=True)
class FunctionalColumnGroup:
    database_name: str
    source_table: str
    group_name: str
    determinant_columns: tuple[str, ...]
    dependent_columns: tuple[str, ...]
    confidence: float
    reason: str

    @property
    def all_columns(self) -> tuple[str, ...]:
        return self.determinant_columns + tuple(
            column
            for column in self.dependent_columns
            if column not in set(self.determinant_columns)
        )


class FunctionalGroupBuilder:
    """
    Build logical column groups from functional dependencies found in raw tables.
    """

    def __init__(self, db: ClickHouseManager):
        self.db = db

    def build_groups(self) -> list[FunctionalColumnGroup]:
        profiles_by_table = self.load_profiles_by_table()
        groups = []

        for table_name, profiles in profiles_by_table.items():
            dependency_groups = self.build_dependency_groups_for_table(
                table_name=table_name,
                profiles=profiles,
                max_determinants=FUNCTIONAL_GROUPING_SETTINGS[
                    "MAX_DETERMINANTS_PER_TABLE"
                ],
                max_determinant_width=FUNCTIONAL_GROUPING_SETTINGS[
                    "MAX_DETERMINANT_WIDTH"
                ],
                min_dependent_columns=FUNCTIONAL_GROUPING_SETTINGS[
                    "MIN_DEPENDENT_COLUMNS"
                ],
            )
            groups.extend(dependency_groups)

            grouped_columns = {
                column for group in dependency_groups for column in group.all_columns
            }
            groups.extend(
                self.build_singleton_groups(
                    table_name,
                    [
                        profile
                        for profile in profiles
                        if profile.column_name not in grouped_columns
                    ],
                )
            )

        return groups

    def build_dependency_groups_for_table(
        self,
        table_name: str,
        profiles: list[FunctionalColumnProfile],
        max_determinants: int,
        max_determinant_width: int,
        min_dependent_columns: int,
    ) -> list[FunctionalColumnGroup]:
        determinant_candidates = self.select_determinant_candidates(
            profiles,
            max_determinants=max_determinants,
        )
        profiles_by_name = {profile.column_name: profile for profile in profiles}
        simple_groups = self.collect_candidate_groups(
            table_name=table_name,
            profiles=profiles,
            determinant_candidates=determinant_candidates,
            min_width=1,
            max_width=1,
            min_dependent_columns=min_dependent_columns,
        )
        selected_simple_groups = self.prune_overlapping_groups(
            simple_groups,
            profiles_by_name,
        )

        if selected_simple_groups or max_determinant_width <= 1:
            return selected_simple_groups

        composite_groups = self.collect_candidate_groups(
            table_name=table_name,
            profiles=profiles,
            determinant_candidates=determinant_candidates,
            min_width=2,
            max_width=max_determinant_width,
            min_dependent_columns=min_dependent_columns,
        )
        return self.prune_overlapping_groups(composite_groups, profiles_by_name)

    def collect_candidate_groups(
        self,
        table_name: str,
        profiles: list[FunctionalColumnProfile],
        determinant_candidates: list[FunctionalColumnProfile],
        min_width: int,
        max_width: int,
        min_dependent_columns: int,
    ) -> list[FunctionalColumnGroup]:
        candidate_groups = []

        for determinant_combo in self.build_determinant_combinations(
            determinant_candidates,
            min_width=min_width,
            max_width=max_width,
        ):
            determinant_column_names = tuple(profile.column_name for profile in determinant_combo)

            dependents = []

            for profile in profiles:
                if profile.column_name in determinant_column_names:
                    continue

                if self.should_skip_dependency_test(determinant_combo, profile):
                    continue

                if check_column_dependency(
                    database=CH_DB,
                    table=table_name,
                    determinant_columns=list(determinant_column_names),
                    dependent_column=profile.column_name,
                    db_manager=self.db,
                ):
                    dependents.append(profile.column_name)

            if len(dependents) < min_dependent_columns:
                continue

            candidate_groups.append(
                FunctionalColumnGroup(
                    database_name=CH_DB,
                    source_table=table_name,
                    group_name=self.make_group_name(table_name, determinant_column_names),
                    determinant_columns=determinant_column_names,
                    dependent_columns=tuple(sorted(dependents)),
                    confidence=self.group_confidence(determinant_combo, dependents),
                    reason="stable_functional_dependency_group",
                )
            )

        return candidate_groups

    def build_singleton_groups(
        self,
        table_name: str,
        profiles: list[FunctionalColumnProfile],
    ) -> list[FunctionalColumnGroup]:
        return [
            FunctionalColumnGroup(
                database_name=CH_DB,
                source_table=table_name,
                group_name=self.make_group_name(table_name, profile.column_name),
                determinant_columns=(profile.column_name,),
                dependent_columns=(),
                confidence=0.4,
                reason="column_has_no_functional_dependency_group",
            )
            for profile in profiles
        ]

    def store_groups(self, groups: list[FunctionalColumnGroup]) -> None:
        clear_metadata_table(self.db, "functional_column_groups")
        clear_metadata_table(self.db, "functional_group_columns")

        if not groups:
            return

        group_rows = [
            [
                group.database_name,
                group.source_table,
                group.group_name,
                ",".join(group.determinant_columns),
                ",".join(group.dependent_columns),
                group.confidence,
                group.reason,
            ]
            for group in groups
        ]
        column_rows = []

        for group in groups:
            for column in group.all_columns:
                column_rows.append(
                    [
                        group.database_name,
                        group.source_table,
                        group.group_name,
                        column,
                        column in group.determinant_columns,
                        column in group.dependent_columns,
                    ]
                )

        self.db.insert(
            f"{META_DB}.functional_column_groups",
            group_rows,
            column_names=[
                "database_name",
                "source_table",
                "group_name",
                "determinant_columns",
                "dependent_columns",
                "confidence",
                "reason",
            ],
        )
        self.db.insert(
            f"{META_DB}.functional_group_columns",
            column_rows,
            column_names=[
                "database_name",
                "source_table",
                "group_name",
                "column_name",
                "is_determinant",
                "is_dependent",
            ],
        )

    def load_groups(self) -> list[FunctionalColumnGroup]:
        sql = f"""
        SELECT
            database_name,
            source_table,
            group_name,
            determinant_columns,
            dependent_columns,
            confidence,
            reason
        FROM {q_ident(META_DB)}.functional_column_groups
        WHERE database_name = %(database)s
        ORDER BY source_table, group_name
        """

        rows = self.db.query(sql, parameters={"database": CH_DB}).result_rows
        return [
            FunctionalColumnGroup(
                database_name=row[0],
                source_table=row[1],
                group_name=row[2],
                determinant_columns=self.split_columns(row[3]),
                dependent_columns=self.split_columns(row[4]),
                confidence=row[5],
                reason=row[6],
            )
            for row in rows
        ]

    def load_profiles_by_table(self) -> dict[str, list[FunctionalColumnProfile]]:
        sql = f"""
        SELECT
            p.table_name,
            p.column_name,
            p.column_type,
            p.rows,
            p.null_ratio,
            p.distinct_count,
            p.uniqueness_ratio,
            coalesce(i.identifiability_score, 0.0) AS identifiability_score
        FROM {q_ident(META_DB)}.column_profiles AS p
        LEFT JOIN {q_ident(META_DB)}.identifiability_scores AS i
            ON p.database_name = i.database_name
           AND p.table_name = i.table_name
           AND p.column_name = i.column_name
        WHERE p.database_name = %(database)s
          AND NOT startsWith(p.column_name, '__')
        ORDER BY p.table_name, p.column_name
        """

        rows = self.db.query(sql, parameters={"database": CH_DB}).result_rows
        profiles_by_table: dict[str, list[FunctionalColumnProfile]] = defaultdict(list)

        for row in rows:
            profiles_by_table[row[0]].append(
                FunctionalColumnProfile(
                    table_name=row[0],
                    column_name=row[1],
                    column_type=row[2],
                    rows=row[3],
                    null_ratio=row[4],
                    distinct_count=row[5],
                    uniqueness_ratio=row[6],
                    identifiability_score=row[7],
                )
            )

        return dict(profiles_by_table)

    @staticmethod
    def select_determinant_candidates(
        profiles: list[FunctionalColumnProfile],
        max_determinants: int,
    ) -> list[FunctionalColumnProfile]:
        candidates = [
            profile
            for profile in profiles
            if profile.null_ratio <= 0.05
            and profile.distinct_count > 1
            and not FunctionalGroupBuilder.is_measure_like_column(profile.column_name)
        ]
        candidates.sort(
            key=lambda profile: (
                profile.identifiability_score,
                profile.uniqueness_ratio,
                profile.distinct_count,
            ),
            reverse=True,
        )
        return candidates[:max_determinants]

    @staticmethod
    def build_determinant_combinations(
        candidates: list[FunctionalColumnProfile],
        min_width: int = 1,
        max_width: int = 1,
    ) -> list[tuple[FunctionalColumnProfile, ...]]:
        combos = []
        min_width = max(1, min_width)
        max_width = max(1, max_width)

        for width in range(min_width, max_width + 1):
            combos.extend(combinations(candidates, width))

        return combos

    @staticmethod
    def should_skip_dependency_test(
        determinant_combo: tuple[FunctionalColumnProfile, ...],
        dependent: FunctionalColumnProfile,
    ) -> bool:
        if dependent.distinct_count <= 1:
            return True

        determinant_capacity = 1
        for determinant in determinant_combo:
            determinant_capacity *= max(determinant.distinct_count, 1)

        if determinant_capacity < dependent.distinct_count:
            return True

        return False

    @staticmethod
    def is_measure_like_column(column_name: str) -> bool:
        normalized = column_name.lower()
        return any(token in normalized for token in MEASURE_NAME_TOKENS)

    @staticmethod
    def prune_overlapping_groups(
        groups: list[FunctionalColumnGroup],
        profiles_by_name: dict[str, FunctionalColumnProfile] | None = None,
    ) -> list[FunctionalColumnGroup]:
        profiles_by_name = profiles_by_name or {}

        def average_determinant_uniqueness(group: FunctionalColumnGroup) -> float:
            scores = [
                profiles_by_name[column].uniqueness_ratio
                for column in group.determinant_columns
                if column in profiles_by_name
            ]
            if not scores:
                return 1.0
            return sum(scores) / len(scores)

        groups = sorted(
            groups,
            key=lambda group: (
                average_determinant_uniqueness(group) < 0.95,
                len(group.dependent_columns),
                group.confidence,
                -len(group.determinant_columns),
            ),
            reverse=True,
        )
        assigned_dependents: set[str] = set()
        selected = []

        for group in groups:
            kept_dependents = tuple(
                column for column in group.dependent_columns if column not in assigned_dependents
            )

            if not kept_dependents:
                continue

            selected_group = FunctionalColumnGroup(
                database_name=group.database_name,
                source_table=group.source_table,
                group_name=group.group_name,
                determinant_columns=group.determinant_columns,
                dependent_columns=kept_dependents,
                confidence=group.confidence,
                reason=group.reason,
            )
            selected.append(selected_group)
            assigned_dependents.update(kept_dependents)

        return sorted(selected, key=lambda group: group.group_name)

    @staticmethod
    def group_confidence(
        determinant_combo: tuple[FunctionalColumnProfile, ...],
        dependents: list[str],
    ) -> float:
        determinant_score = sum(
            determinant.identifiability_score for determinant in determinant_combo
        ) / len(determinant_combo)
        raw_score = 0.5 + 0.25 * determinant_score + 0.03 * len(dependents)
        return round(min(raw_score, 0.95), 6)

    @staticmethod
    def make_group_name(table_name: str, concept: str | tuple[str, ...]) -> str:
        cleaned_table = re.sub(r"[^0-9A-Za-z_]+", "_", table_name).strip("_").lower()
        concept_name = "_".join(concept) if isinstance(concept, tuple) else concept
        cleaned_concept = re.sub(r"[^0-9A-Za-z_]+", "_", concept_name).strip("_").lower()
        return f"logical_{cleaned_table}_{cleaned_concept}"

    @staticmethod
    def split_columns(columns: str) -> tuple[str, ...]:
        return tuple(column.strip() for column in columns.split(",") if column.strip())

    @staticmethod
    def print_groups(groups: list[FunctionalColumnGroup]) -> None:
        if not groups:
            logger.info("No functional column groups found.")
            return

        for group in groups:
            logger.info(
                "%s | source=%s | determinants=%s | dependents=%s | confidence=%s | reason=%s",
                group.group_name,
                group.source_table,
                ", ".join(group.determinant_columns),
                ", ".join(group.dependent_columns),
                group.confidence,
                group.reason,
            )
