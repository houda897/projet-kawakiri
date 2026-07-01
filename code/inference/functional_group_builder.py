from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass
from itertools import combinations

from core.clickhouse_manager import CH_DB, META_DB, ClickHouseManager
from core.logger import get_logger
from core.meta import clear_metadata_table
from core.naming import (
    belongs_to_key_concept,
    is_descriptive_candidate,
    is_grain_like_column,
    is_key_like_column,
    is_location_like_column,
    is_lookup_key_candidate,
    is_measure_candidate,
    is_temporal_like_column,
)
from core.schema import is_temporal_type, q_ident
from inference.source_structure import SourceStructureAnalyzer, SourceTableStructure
from stats.functional_dependency import check_column_dependency

logger = get_logger(__name__)


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
    entropy_ratio: float = 0.0
    variation_coefficient: float = 0.0
    skewness_score: float = 0.0


@dataclass(frozen=True)
class FunctionalColumnGroup:
    database_name: str
    source_table: str
    group_name: str
    determinant_columns: tuple[str, ...]
    dependent_columns: tuple[str, ...]
    confidence: float
    reason: str
    group_score: float = 0.0
    group_role: str = "UNASSIGNED"
    determinant_distinct_count: int = 0
    determinant_uniqueness_ratio: float = 1.0
    repeated_row_count: int = 0

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
        source_structures = SourceStructureAnalyzer(self.db).load_structures()
        groups = []

        for table_name, profiles in profiles_by_table.items():
            dependency_groups = self.build_dependency_groups_for_table(
                table_name=table_name,
                profiles=profiles,
                source_structure=source_structures.get(table_name),
            )
            groups.extend(dependency_groups)

            grouped_columns = {
                column for group in dependency_groups for column in group.all_columns
            }
            groups.extend(
                self.build_singleton_groups(
                    table_name,
                    [profile for profile in profiles if profile.column_name not in grouped_columns],
                )
            )

        return groups

    def build_dependency_groups_for_table(
        self,
        table_name: str,
        profiles: list[FunctionalColumnProfile],
        source_structure: SourceTableStructure | None = None,
    ) -> list[FunctionalColumnGroup]:
        if source_structure and source_structure.is_normalized_entity_source:
            normalized_group = self.build_normalized_source_group(
                table_name,
                profiles,
                source_structure,
            )
            if normalized_group is not None:
                return [normalized_group]

        determinant_candidates = self.select_determinant_candidates(profiles)
        profiles_by_name = {profile.column_name: profile for profile in profiles}

        simple_groups = self.build_candidate_groups(
            table_name=table_name,
            profiles=profiles,
            determinant_candidates=determinant_candidates,
            min_width=1,
            max_width=1,
        )
        selected_groups = self.select_non_overlapping_groups(
            simple_groups,
            profiles_by_name,
        )

        assigned_columns = {column for group in selected_groups for column in group.all_columns}
        remaining_profiles = [
            profile for profile in profiles if profile.column_name not in assigned_columns
        ]
        remaining_determinants = [
            profile
            for profile in determinant_candidates
            if profile.column_name not in assigned_columns
        ]

        if len(remaining_determinants) > 1 and remaining_profiles:
            composite_groups = self.build_candidate_groups(
                table_name=table_name,
                profiles=remaining_profiles,
                determinant_candidates=remaining_determinants,
                min_width=2,
                max_width=min(2, len(remaining_determinants)),
            )
            selected_composite_groups = self.select_non_overlapping_groups(
                composite_groups,
                profiles_by_name,
                already_assigned=assigned_columns,
            )
            selected_groups.extend(selected_composite_groups)

        selected_groups = self.expand_groups_with_unassigned_columns(
            table_name=table_name,
            groups=selected_groups,
            profiles=profiles,
        )

        return sorted(selected_groups, key=lambda group: group.group_name)

    def expand_groups_with_unassigned_columns(
        self,
        table_name: str,
        groups: list[FunctionalColumnGroup],
        profiles: list[FunctionalColumnProfile],
    ) -> list[FunctionalColumnGroup]:
        """Complete groups by repeatedly testing their functional closure."""
        profiles_by_name = {profile.column_name: profile for profile in profiles}
        expanded_groups = list(groups)
        assigned_columns = {column for group in expanded_groups for column in group.all_columns}

        changed = True
        while changed:
            changed = False

            for index, group in enumerate(expanded_groups):
                closure_determinants = group.all_columns
                determinant_profiles = [
                    profiles_by_name[column]
                    for column in closure_determinants
                    if column in profiles_by_name
                ]
                if not self.can_expand_group(
                    table_name,
                    closure_determinants,
                    determinant_profiles,
                ):
                    continue

                new_dependents = []
                for profile in profiles:
                    if profile.column_name in assigned_columns:
                        continue
                    if check_column_dependency(
                        database=CH_DB,
                        table=table_name,
                        determinant_columns=list(closure_determinants),
                        dependent_column=profile.column_name,
                        db_manager=self.db,
                    ):
                        new_dependents.append(profile.column_name)

                if not new_dependents:
                    continue

                expanded_groups[index] = FunctionalColumnGroup(
                    database_name=group.database_name,
                    source_table=group.source_table,
                    group_name=group.group_name,
                    determinant_columns=closure_determinants,
                    dependent_columns=tuple(sorted(new_dependents)),
                    confidence=group.confidence,
                    reason="functional_dependency_closure_group",
                    group_score=group.group_score,
                    group_role=group.group_role,
                    determinant_distinct_count=group.determinant_distinct_count,
                    determinant_uniqueness_ratio=group.determinant_uniqueness_ratio,
                    repeated_row_count=group.repeated_row_count,
                )
                assigned_columns.update(new_dependents)
                changed = True

        return expanded_groups

    def can_expand_group(
        self,
        table_name: str,
        determinant_columns: tuple[str, ...],
        determinant_profiles: list[FunctionalColumnProfile],
    ) -> bool:
        """Reject closures made trivially true by a unique determinant tuple."""
        if not determinant_profiles:
            return False
        _, uniqueness_ratio, repeated_rows = self.compute_determinant_shape(
            table_name,
            determinant_columns,
            determinant_profiles,
        )
        return uniqueness_ratio < 0.999999999 and repeated_rows > 0

    def build_normalized_source_group(
        self,
        table_name: str,
        profiles: list[FunctionalColumnProfile],
        source_structure: SourceTableStructure,
    ) -> FunctionalColumnGroup | None:
        """Keep an already normalized referenced entity as one coherent group."""
        if source_structure.entity_key is None:
            return None
        determinant_columns = self.split_columns(source_structure.entity_key.column_name)
        profile_names = {profile.column_name for profile in profiles}
        if not determinant_columns or not set(determinant_columns) <= profile_names:
            return None
        dependents = tuple(
            profile.column_name
            for profile in profiles
            if profile.column_name not in determinant_columns
        )
        rows = max((profile.rows for profile in profiles), default=0)
        return FunctionalColumnGroup(
            database_name=CH_DB,
            source_table=table_name,
            group_name=self.make_group_name(table_name, determinant_columns),
            determinant_columns=determinant_columns,
            dependent_columns=dependents,
            confidence=1.0,
            reason="normalized_source_entity_group",
            group_score=1.0,
            group_role="NORMALIZED_ENTITY",
            determinant_distinct_count=rows,
            determinant_uniqueness_ratio=1.0,
            repeated_row_count=0,
        )

    def build_candidate_groups(
        self,
        table_name: str,
        profiles: list[FunctionalColumnProfile],
        determinant_candidates: list[FunctionalColumnProfile],
        min_width: int,
        max_width: int,
    ) -> list[FunctionalColumnGroup]:
        return self.collect_candidate_groups(
            table_name=table_name,
            profiles=profiles,
            determinant_candidates=determinant_candidates,
            min_width=min_width,
            max_width=max_width,
        )

    def collect_candidate_groups(
        self,
        table_name: str,
        profiles: list[FunctionalColumnProfile],
        determinant_candidates: list[FunctionalColumnProfile],
        min_width: int,
        max_width: int,
    ) -> list[FunctionalColumnGroup]:
        candidate_groups = []

        for determinant_combo in self.build_determinant_combinations(
            determinant_candidates,
            min_width=min_width,
            max_width=max_width,
        ):
            determinant_column_names = tuple(profile.column_name for profile in determinant_combo)
            determinant_distinct_count, determinant_uniqueness_ratio, repeated_rows = (
                self.compute_determinant_shape(
                    table_name,
                    determinant_column_names,
                    list(determinant_combo),
                )
            )
            if determinant_uniqueness_ratio >= 0.999999999 or repeated_rows <= 0:
                continue

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

            if not dependents:
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
                    group_score=0.0,
                    group_role="GROUP_CANDIDATE",
                    determinant_distinct_count=determinant_distinct_count,
                    determinant_uniqueness_ratio=determinant_uniqueness_ratio,
                    repeated_row_count=repeated_rows,
                )
            )

        return candidate_groups

    def compute_determinant_shape(
        self,
        table_name: str,
        determinant_columns: tuple[str, ...],
        determinant_profiles: list[FunctionalColumnProfile],
    ) -> tuple[int, float, int]:
        """Return tuple cardinality, uniqueness and repeated-row support."""
        if hasattr(self.db, "query"):
            columns_sql = ", ".join(q_ident(column) for column in determinant_columns)
            not_null_sql = " AND ".join(
                f"{q_ident(column)} IS NOT NULL" for column in determinant_columns
            )
            sql = f"""
            SELECT
                count() AS non_null_rows,
                uniqExact(tuple({columns_sql})) AS distinct_rows
            FROM {q_ident(CH_DB)}.{q_ident(table_name)}
            WHERE {not_null_sql}
            """
            row = self.db.query(sql).result_rows[0]
            non_null_rows = int(row[0] or 0)
            distinct_rows = int(row[1] or 0)
        else:
            non_null_rows = max((profile.rows for profile in determinant_profiles), default=0)
            # Unit-level profile evidence cannot reconstruct tuple cardinality;
            # use the strongest individual cardinality as a conservative bound.
            approximate_uniqueness = max(
                (profile.uniqueness_ratio for profile in determinant_profiles),
                default=1.0,
            )
            distinct_rows = round(non_null_rows * approximate_uniqueness)

        uniqueness_ratio = distinct_rows / non_null_rows if non_null_rows else 1.0
        return distinct_rows, uniqueness_ratio, max(non_null_rows - distinct_rows, 0)

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
                group_score=0.4,
                group_role="SINGLETON",
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
                group.group_score,
                group.group_role,
                group.determinant_distinct_count,
                group.determinant_uniqueness_ratio,
                group.repeated_row_count,
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
                "group_score",
                "group_role",
                "determinant_distinct_count",
                "determinant_uniqueness_ratio",
                "repeated_row_count",
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
            reason,
            group_score,
            group_role
            , determinant_distinct_count
            , determinant_uniqueness_ratio
            , repeated_row_count
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
                group_score=row[7],
                group_role=row[8],
                determinant_distinct_count=row[9],
                determinant_uniqueness_ratio=row[10],
                repeated_row_count=row[11],
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
            coalesce(i.identifiability_score, 0.0) AS identifiability_score,
            coalesce(s.entropy_ratio, 0.0) AS entropy_ratio,
            coalesce(s.variation_coefficient, 0.0) AS variation_coefficient,
            coalesce(s.skewness_score, 0.0) AS skewness_score
        FROM {q_ident(META_DB)}.column_profiles AS p
        LEFT JOIN {q_ident(META_DB)}.identifiability_scores AS i
            ON p.database_name = i.database_name
           AND p.table_name = i.table_name
           AND p.column_name = i.column_name
        LEFT JOIN (
            SELECT
                database_name,
                table_name,
                column_name,
                max(run_ts) AS latest_run_ts
            FROM {q_ident(META_DB)}.column_stats
            GROUP BY database_name, table_name, column_name
        ) AS latest
            ON p.database_name = latest.database_name
        AND p.table_name = latest.table_name
        AND p.column_name = latest.column_name
        LEFT JOIN {q_ident(META_DB)}.column_stats AS s
            ON s.database_name = latest.database_name
        AND s.table_name = latest.table_name
        AND s.column_name = latest.column_name
        AND s.run_ts = latest.latest_run_ts
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
                    entropy_ratio=row[8],
                    variation_coefficient=row[9],
                    skewness_score=row[10],
                )
            )

        return dict(profiles_by_table)

    @staticmethod
    def select_determinant_candidates(
        profiles: list[FunctionalColumnProfile],
    ) -> list[FunctionalColumnProfile]:
        candidates = [
            profile
            for profile in profiles
            if profile.null_ratio <= 0.05
            and profile.distinct_count > 1
            and profile.uniqueness_ratio < 0.95
            and (
                not is_temporal_type(profile.column_type) or is_key_like_column(profile.column_name)
            )
            and (
                not is_temporal_like_column(profile.column_name)
                or is_key_like_column(profile.column_name)
            )
            and not is_measure_candidate(profile)
        ]
        candidates.sort(
            key=lambda profile: (
                is_lookup_key_candidate(profile),
                profile.identifiability_score,
                profile.uniqueness_ratio,
                profile.distinct_count,
            ),
            reverse=True,
        )
        return candidates

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
        if dependent.distinct_count <= 1 and not is_location_like_column(
            dependent.column_name,
        ):
            return True

        if is_key_like_column(dependent.column_name):
            return True
        if is_grain_like_column(dependent.column_name):
            return True
        if is_measure_candidate(dependent):
            return True
        if not is_descriptive_candidate(dependent):
            return True

        determinant_capacity = 1
        for determinant in determinant_combo:
            determinant_capacity *= max(determinant.distinct_count, 1)

        if determinant_capacity < dependent.distinct_count:
            return True

        return False

    @staticmethod
    def is_invalid_dependent_column(dependent: FunctionalColumnProfile) -> bool:
        if is_key_like_column(dependent.column_name):
            return True
        if is_measure_candidate(dependent):
            return True
        if is_grain_like_column(dependent.column_name):
            return True
        if not is_descriptive_candidate(dependent):
            return True
        return False

    @staticmethod
    def select_non_overlapping_groups(
        groups: list[FunctionalColumnGroup],
        profiles_by_name: dict[str, FunctionalColumnProfile] | None = None,
        already_assigned: set[str] | None = None,
    ) -> list[FunctionalColumnGroup]:
        profiles_by_name = profiles_by_name or {}
        assigned_columns = set(already_assigned or set())
        groups = sorted(
            groups,
            key=lambda group: FunctionalGroupBuilder.score_group(group, profiles_by_name),
            reverse=True,
        )
        preferred_group_by_dependent = FunctionalGroupBuilder.preferred_group_by_dependent(
            groups,
            profiles_by_name,
        )
        selected = []

        for group in groups:
            if any(column in assigned_columns for column in group.determinant_columns):
                continue

            kept_dependents = tuple(
                column
                for column in group.dependent_columns
                if column not in assigned_columns
                and preferred_group_by_dependent.get(column, group.group_name) == group.group_name
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
                group_score=FunctionalGroupBuilder.score_group(
                    group,
                    profiles_by_name,
                ),
                group_role=group.group_role,
                determinant_distinct_count=group.determinant_distinct_count,
                determinant_uniqueness_ratio=group.determinant_uniqueness_ratio,
                repeated_row_count=group.repeated_row_count,
            )
            selected.append(selected_group)
            assigned_columns.update(selected_group.all_columns)

        return sorted(selected, key=lambda group: group.group_name)

    @staticmethod
    def score_group(
        group: FunctionalColumnGroup,
        profiles_by_name: dict[str, FunctionalColumnProfile],
    ) -> float:
        determinant_profiles = [
            profiles_by_name[column]
            for column in group.determinant_columns
            if column in profiles_by_name
        ]
        dependent_profiles = [
            profiles_by_name[column]
            for column in group.dependent_columns
            if column in profiles_by_name
        ]

        if determinant_profiles:
            avg_identifiability = sum(
                profile.identifiability_score for profile in determinant_profiles
            ) / len(determinant_profiles)
        else:
            avg_identifiability = 0.0

        compression_gain = max(0.0, 1.0 - group.determinant_uniqueness_ratio)
        support_ratio = group.repeated_row_count / max(
            group.repeated_row_count + group.determinant_distinct_count, 1
        )
        descriptive_richness = sum(
            1 for profile in dependent_profiles if is_descriptive_candidate(profile)
        )
        measure_dependents = len(dependent_profiles) - descriptive_richness

        return (
            group.confidence
            + compression_gain
            + support_ratio
            + 0.12 * descriptive_richness
            + 0.04 * measure_dependents
            + 0.1 * avg_identifiability
            + FunctionalGroupBuilder.key_like_bonus(determinant_profiles)
            + FunctionalGroupBuilder.compact_group_bonus(group)
            - FunctionalGroupBuilder.over_general_determinant_penalty(
                determinant_profiles,
            )
            - FunctionalGroupBuilder.near_grain_determinant_penalty(
                determinant_profiles,
                len(group.dependent_columns),
            )
            - 0.08 * max(len(group.determinant_columns) - 1, 0)
        )

    @staticmethod
    def preferred_group_by_dependent(
        groups: list[FunctionalColumnGroup],
        profiles_by_name: dict[str, FunctionalColumnProfile],
    ) -> dict[str, str]:
        best: dict[str, tuple[str, float]] = {}

        for group in groups:
            for dependent in group.dependent_columns:
                score = FunctionalGroupBuilder.score_dependency_owner(
                    group,
                    dependent,
                    profiles_by_name,
                )
                current = best.get(dependent)
                if current is None or score > current[1]:
                    best[dependent] = (group.group_name, score)

        return {dependent: group_name for dependent, (group_name, _) in best.items()}

    @staticmethod
    def score_dependency_owner(
        group: FunctionalColumnGroup,
        dependent: str,
        profiles_by_name: dict[str, FunctionalColumnProfile],
    ) -> float:
        score = FunctionalGroupBuilder.score_group(group, profiles_by_name)
        determinant_profiles = [
            profiles_by_name[column]
            for column in group.determinant_columns
            if column in profiles_by_name
        ]

        if FunctionalGroupBuilder.dependent_matches_determinant_concept(
            group.determinant_columns,
            dependent,
        ):
            score += 1.2

        if determinant_profiles:
            avg_uniqueness = sum(
                profile.uniqueness_ratio for profile in determinant_profiles
            ) / len(determinant_profiles)
            if avg_uniqueness >= 0.30:
                score -= avg_uniqueness

        score -= 0.10 * max(len(group.dependent_columns) - 1, 0)
        return score

    @staticmethod
    def dependent_matches_determinant_concept(
        determinant_columns: tuple[str, ...],
        dependent_column: str,
    ) -> bool:
        if any(belongs_to_key_concept(column, dependent_column) for column in determinant_columns):
            return True

        return any(
            is_location_like_column(column) for column in determinant_columns
        ) and is_location_like_column(dependent_column)

    @staticmethod
    def compact_group_bonus(group: FunctionalColumnGroup) -> float:
        if len(group.dependent_columns) <= 3:
            return 0.18
        return 0.0

    @staticmethod
    def key_like_bonus(
        determinant_profiles: list[FunctionalColumnProfile],
    ) -> float:
        if not determinant_profiles:
            return 0.0

        return sum(
            0.28
            for profile in determinant_profiles
            if is_key_like_column(profile.column_name) and 0.01 <= profile.uniqueness_ratio < 0.95
        )

    @staticmethod
    def over_general_determinant_penalty(
        determinant_profiles: list[FunctionalColumnProfile],
    ) -> float:
        if not determinant_profiles:
            return 0.0

        penalty = 0.0
        for profile in determinant_profiles:
            if profile.uniqueness_ratio >= 0.01:
                continue
            if is_key_like_column(profile.column_name):
                penalty += 0.25
            else:
                penalty += 1.2

        return penalty

    @staticmethod
    def near_grain_determinant_penalty(
        determinant_profiles: list[FunctionalColumnProfile],
        dependent_count: int,
    ) -> float:
        if not determinant_profiles:
            return 0.0

        avg_uniqueness = sum(profile.uniqueness_ratio for profile in determinant_profiles) / len(
            determinant_profiles
        )
        if avg_uniqueness <= 0.25:
            return 0.0

        return (avg_uniqueness - 0.25) * (1.4 + 0.08 * max(dependent_count - 1, 0))

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
