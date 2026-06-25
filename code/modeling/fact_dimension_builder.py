from __future__ import annotations

import re
from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, replace

from core.clickhouse_manager import CH_DB, ClickHouseManager
from core.naming import (
    belongs_to_key_concept,
    is_descriptive_candidate,
    is_grain_candidate,
    is_grain_like_column,
    is_key_like_column,
    is_location_like_column,
    is_lookup_key_candidate,
    is_measure_candidate,
    is_temporal_like_column,
)
from inference.functional_group_builder import (
    FunctionalColumnGroup,
    FunctionalColumnProfile,
    FunctionalGroupBuilder,
)
from stats.functional_dependency import check_column_dependency

DIMENSION_CANDIDATE = "DIMENSION_CANDIDATE"
FACT_CANDIDATE = "FACT_CANDIDATE"
SINGLETON = "SINGLETON"


@dataclass(frozen=True)
class LogicalTablePlan:
    database_name: str
    logical_table_name: str
    source_table: str
    group_name: str
    determinant_columns: tuple[str, ...]
    columns: tuple[str, ...]
    logical_table_role: str
    distinct_rows: bool


class FactDimensionBuilder:
    """
    Convert selected functional groups into logical dimensions and fact tables.
    """

    def __init__(self, db: ClickHouseManager):
        self.db = db

    def build_plans(self) -> list[LogicalTablePlan]:
        group_builder = FunctionalGroupBuilder(self.db)
        groups = group_builder.load_groups()
        profiles_by_table = group_builder.load_profiles_by_table()
        profiles_by_table_and_column = {
            table_name: {profile.column_name: profile for profile in profiles}
            for table_name, profiles in profiles_by_table.items()
        }

        dimension_plans = self.build_dimension_tables(
            groups,
            profiles_by_table_and_column,
        )
        dimension_plans.extend(
            self.build_fallback_dimension_tables(
                profiles_by_table,
                dimension_plans,
            )
        )
        dimension_plans.extend(
            self.build_contextual_dimension_tables(
                profiles_by_table,
                dimension_plans,
            )
        )
        dimension_plans = self.enrich_dimension_tables(
            dimension_plans,
            profiles_by_table,
        )
        dimension_plans = self.promote_composite_dimension_keys(
            dimension_plans,
            profiles_by_table,
        )
        fact_plans = self.build_fact_tables(
            groups,
            profiles_by_table,
            dimension_plans,
        )

        return sorted(
            dimension_plans + fact_plans,
            key=lambda plan: (plan.source_table, plan.logical_table_role, plan.logical_table_name),
        )

    def build_dimension_tables(
        self,
        groups: list[FunctionalColumnGroup],
        profiles_by_table_and_column: Mapping[str, Mapping[str, FunctionalColumnProfile]],
    ) -> list[LogicalTablePlan]:
        dimensions = []

        for group in groups:
            source_profiles = profiles_by_table_and_column.get(group.source_table, {})
            if not self.is_dimension_group(group, source_profiles):
                continue

            dimensions.append(
                LogicalTablePlan(
                    database_name=group.database_name,
                    logical_table_name=group.group_name,
                    source_table=group.source_table,
                    group_name=group.group_name,
                    determinant_columns=group.determinant_columns,
                    columns=group.all_columns,
                    logical_table_role=DIMENSION_CANDIDATE,
                    distinct_rows=True,
                )
            )

        return dimensions

    def enrich_dimension_tables(
        self,
        dimension_plans: list[LogicalTablePlan],
        profiles_by_table: Mapping[str, Sequence[FunctionalColumnProfile]],
    ) -> list[LogicalTablePlan]:
        enriched = []

        for dimension in dimension_plans:
            source_profiles = profiles_by_table.get(dimension.source_table, [])
            columns = list(dimension.columns)

            for profile in source_profiles:
                if profile.column_name in columns:
                    continue
                if self.is_invalid_dimension_dependent(profile.column_name):
                    continue
                if not is_descriptive_candidate(profile):
                    continue
                if self.is_contextual_dependent_for_dimension(
                    dimension.determinant_columns,
                    profile.column_name,
                ) and self.is_stable_dimension_dependent(
                    dimension.source_table,
                    dimension.determinant_columns,
                    profile.column_name,
                ):
                    columns.append(profile.column_name)

            enriched.append(replace(dimension, columns=tuple(columns)))

        return enriched

    def promote_composite_dimension_keys(
        self,
        dimension_plans: list[LogicalTablePlan],
        profiles_by_table: Mapping[str, Sequence[FunctionalColumnProfile]],
    ) -> list[LogicalTablePlan]:
        promoted = []

        for dimension in dimension_plans:
            source_profiles = profiles_by_table.get(dimension.source_table, [])
            profiles_by_name = {profile.column_name: profile for profile in source_profiles}
            promoted_dimension = dimension

            if len(dimension.determinant_columns) == 1:
                for profile in source_profiles:
                    if profile.column_name in dimension.columns:
                        continue
                    if not is_descriptive_candidate(profile):
                        continue
                    if not self.is_contextual_dependent_for_dimension(
                        dimension.determinant_columns,
                        profile.column_name,
                    ):
                        continue

                    candidate_determinants = (
                        *dimension.determinant_columns,
                        profile.column_name,
                    )
                    dependent_columns = tuple(
                        column
                        for column in dimension.columns
                        if column not in dimension.determinant_columns
                    )
                    if not dependent_columns:
                        continue
                    if not all(
                        self.is_stable_dimension_dependent(
                            dimension.source_table,
                            candidate_determinants,
                            dependent,
                        )
                        for dependent in dependent_columns
                    ):
                        continue

                    columns = candidate_determinants + tuple(
                        column
                        for column in dependent_columns
                        if column in profiles_by_name
                    )
                    table_name = self.make_dimension_table_name(
                        dimension.source_table,
                        "_".join(candidate_determinants),
                    )
                    promoted_dimension = replace(
                        dimension,
                        logical_table_name=table_name,
                        group_name=table_name,
                        determinant_columns=candidate_determinants,
                        columns=columns,
                    )
                    break

            promoted.append(promoted_dimension)

        return promoted

    def build_contextual_dimension_tables(
        self,
        profiles_by_table: Mapping[str, Sequence[FunctionalColumnProfile]],
        existing_dimensions: list[LogicalTablePlan],
    ) -> list[LogicalTablePlan]:
        existing_dimension_keys = {
            (dimension.source_table, dimension.determinant_columns)
            for dimension in existing_dimensions
        }
        contextual_dimensions = []

        for source_table, profiles in profiles_by_table.items():
            profiles_by_name = {profile.column_name: profile for profile in profiles}
            for key_profile in self.select_contextual_dimension_key_profiles(profiles):
                determinant_columns = (key_profile.column_name,)
                if (source_table, determinant_columns) in existing_dimension_keys:
                    continue

                dependents = [
                    profile.column_name
                    for profile in profiles
                    if profile.column_name != key_profile.column_name
                    and not self.is_invalid_dimension_dependent(profile.column_name)
                    and is_descriptive_candidate(profile)
                    and self.is_contextual_dependent_for_dimension(
                        determinant_columns,
                        profile.column_name,
                    )
                    and self.is_stable_dimension_dependent(
                        source_table,
                        determinant_columns,
                        profile.column_name,
                    )
                ]
                if not dependents:
                    continue

                columns = determinant_columns + tuple(
                    column
                    for column in dependents
                    if column in profiles_by_name
                )
                table_name = self.make_dimension_table_name(
                    source_table,
                    key_profile.column_name,
                )
                contextual_dimensions.append(
                    LogicalTablePlan(
                        database_name=CH_DB,
                        logical_table_name=table_name,
                        source_table=source_table,
                        group_name=table_name,
                        determinant_columns=determinant_columns,
                        columns=columns,
                        logical_table_role=DIMENSION_CANDIDATE,
                        distinct_rows=True,
                    )
                )
                existing_dimension_keys.add((source_table, determinant_columns))

        return contextual_dimensions

    def build_fallback_dimension_tables(
        self,
        profiles_by_table: Mapping[str, Sequence[FunctionalColumnProfile]],
        existing_dimensions: list[LogicalTablePlan],
    ) -> list[LogicalTablePlan]:
        dimension_sources = {dimension.source_table for dimension in existing_dimensions}
        fallback_dimensions = []

        for source_table, profiles in profiles_by_table.items():
            if source_table in dimension_sources:
                continue
            if not self.is_descriptive_source_table(source_table, profiles):
                continue

            key_profile = self.select_dimension_key_profile(profiles)
            if key_profile is None:
                continue

            columns = tuple(profile.column_name for profile in profiles)
            fallback_dimensions.append(
                LogicalTablePlan(
                    database_name=CH_DB,
                    logical_table_name=self.make_dimension_table_name(
                        source_table,
                        key_profile.column_name,
                    ),
                    source_table=source_table,
                    group_name=self.make_dimension_table_name(
                        source_table,
                        key_profile.column_name,
                    ),
                    determinant_columns=(key_profile.column_name,),
                    columns=columns,
                    logical_table_role=DIMENSION_CANDIDATE,
                    distinct_rows=True,
                )
            )

        return fallback_dimensions

    def build_fact_tables(
        self,
        groups: list[FunctionalColumnGroup],
        profiles_by_table: Mapping[str, Sequence[FunctionalColumnProfile]],
        dimension_plans: list[LogicalTablePlan],
    ) -> list[LogicalTablePlan]:
        dimensions_by_source: dict[str, list[LogicalTablePlan]] = defaultdict(list)
        for dimension in dimension_plans:
            dimensions_by_source[dimension.source_table].append(dimension)

        facts = []
        for source_table, profiles in profiles_by_table.items():
            if not self.is_transactional_source_table(source_table, profiles):
                continue

            dimension_dependent_columns = {
                column
                for dimension in dimensions_by_source.get(source_table, [])
                for column in dimension.columns
                if column not in dimension.determinant_columns
            }
            dimension_key_columns = {
                column
                for dimension in dimensions_by_source.get(source_table, [])
                for column in dimension.determinant_columns
            }
            fact_columns = self.select_fact_columns(
                profiles,
                dimension_dependent_columns,
                dimension_key_columns,
            )

            if not self.has_fact_signal(
                fact_columns,
                profiles,
                dimension_key_columns,
            ):
                continue

            facts.append(
                LogicalTablePlan(
                    database_name=CH_DB,
                    logical_table_name=self.make_fact_table_name(source_table),
                    source_table=source_table,
                    group_name=self.make_fact_table_name(source_table),
                    determinant_columns=tuple(sorted(dimension_key_columns)),
                    columns=tuple(fact_columns),
                    logical_table_role=FACT_CANDIDATE,
                    distinct_rows=False,
                )
            )

        return facts

    def select_fact_columns(
        self,
        profiles: Sequence[FunctionalColumnProfile],
        dimension_dependent_columns: set[str],
        dimension_key_columns: set[str],
    ) -> list[str]:
        fact_columns = []

        for profile in profiles:
            if profile.column_name in dimension_key_columns:
                fact_columns.append(profile.column_name)
                continue
            if profile.column_name in dimension_dependent_columns:
                continue
            if is_measure_candidate(profile):
                fact_columns.append(profile.column_name)
                continue
            if self.is_grain_signal_column(profile.column_name, profile):
                fact_columns.append(profile.column_name)

        return fact_columns

    @staticmethod
    def select_contextual_dimension_key_profiles(
        profiles: Sequence[FunctionalColumnProfile],
    ) -> list[FunctionalColumnProfile]:
        candidates = [
            profile
            for profile in profiles
            if profile.null_ratio <= 0.05
            and 0.01 <= profile.uniqueness_ratio < 0.95
            and is_lookup_key_candidate(profile)
            and not is_grain_like_column(profile.column_name)
            and not is_temporal_like_column(profile.column_name)
        ]
        candidates.sort(
            key=lambda profile: (
                is_location_like_column(profile.column_name),
                profile.identifiability_score,
                profile.uniqueness_ratio,
            ),
            reverse=True,
        )
        return candidates

    @staticmethod
    def is_contextual_dependent_for_dimension(
        determinant_columns: tuple[str, ...],
        dependent_column: str,
    ) -> bool:
        if any(
            belongs_to_key_concept(column, dependent_column)
            for column in determinant_columns
        ):
            return True

        return any(
            is_location_like_column(column) for column in determinant_columns
        ) and is_location_like_column(dependent_column)

    @staticmethod
    def is_dimension_group(
        group: FunctionalColumnGroup,
        source_profiles: Mapping[str, FunctionalColumnProfile],
    ) -> bool:
        if not group.dependent_columns:
            return False

        determinant_profiles = [
            source_profiles[column]
            for column in group.determinant_columns
            if column in source_profiles
        ]
        if determinant_profiles and all(
            profile.uniqueness_ratio >= 0.95 for profile in determinant_profiles
        ):
            return False

        if (
            determinant_profiles
            and not any(
                is_key_like_column(profile.column_name)
                for profile in determinant_profiles
            )
            and FactDimensionBuilder.has_unique_key_profile(source_profiles.values())
        ):
            return False

        descriptive_dependents = 0
        for column in group.dependent_columns:
            profile = source_profiles.get(column)
            if profile is None:
                continue
            if FactDimensionBuilder.is_invalid_dimension_dependent(column):
                return False
            if not is_descriptive_candidate(profile):
                return False
            descriptive_dependents += 1

        return descriptive_dependents > 0

    @staticmethod
    def has_unique_key_profile(profiles: Iterable[FunctionalColumnProfile]) -> bool:
        return any(
            profile.null_ratio <= 0.05
            and profile.uniqueness_ratio >= 0.95
            and is_key_like_column(profile.column_name)
            and not is_measure_candidate(profile)
            for profile in profiles
        )

    @staticmethod
    def has_fact_signal(
        fact_columns: list[str],
        profiles: Sequence[FunctionalColumnProfile],
        dimension_key_columns: set[str],
    ) -> bool:
        profiles_by_name = {profile.column_name: profile for profile in profiles}
        measure_columns = []
        grain_columns = set(dimension_key_columns)

        for column in fact_columns:
            profile = profiles_by_name[column]
            if column in dimension_key_columns:
                grain_columns.add(column)
                continue
            if is_measure_candidate(profile):
                measure_columns.append(column)
                continue
            if FactDimensionBuilder.is_grain_signal_column(column, profile):
                grain_columns.add(column)

        return bool(measure_columns) and bool(grain_columns)

    @staticmethod
    def is_transactional_source_table(
        source_table: str,
        profiles: Sequence[FunctionalColumnProfile],
    ) -> bool:
        measure_columns = [
            profile
            for profile in profiles
            if is_measure_candidate(profile)
        ]
        if not measure_columns:
            return False

        grain_columns = [
            profile
            for profile in profiles
            if FactDimensionBuilder.is_grain_signal_column(
                profile.column_name,
                profile,
            )
        ]
        if not grain_columns:
            return False

        descriptive_columns = [
            profile
            for profile in profiles
            if not FactDimensionBuilder.is_grain_signal_column(
                profile.column_name,
                profile,
            )
            and not is_measure_candidate(profile)
        ]

        if (
            len(grain_columns) == 1
            and grain_columns[0].uniqueness_ratio >= 0.95
            and descriptive_columns
        ):
            return False

        return len(descriptive_columns) <= len(grain_columns) + len(measure_columns)

    @staticmethod
    def is_descriptive_source_table(
        source_table: str,
        profiles: Sequence[FunctionalColumnProfile],
    ) -> bool:
        if FactDimensionBuilder.is_transactional_source_table(source_table, profiles):
            return False

        key_profile = FactDimensionBuilder.select_dimension_key_profile(profiles)
        if key_profile is None:
            return False

        measure_columns = [
            profile
            for profile in profiles
            if is_measure_candidate(profile)
        ]
        grain_columns = [
            profile
            for profile in profiles
            if FactDimensionBuilder.is_grain_signal_column(
                profile.column_name,
                profile,
            )
        ]
        descriptive_columns = [
            profile
            for profile in profiles
            if profile.column_name != key_profile.column_name
            and not is_measure_candidate(profile)
            and not FactDimensionBuilder.is_grain_signal_column(
                profile.column_name,
                profile,
            )
        ]

        if not descriptive_columns:
            return False

        if len(grain_columns) > 1:
            return False

        return len(measure_columns) <= max(1, len(descriptive_columns))

    def is_stable_dimension_dependent(
        self,
        source_table: str,
        determinant_columns: tuple[str, ...],
        dependent_column: str,
    ) -> bool:
        return check_column_dependency(
            database=CH_DB,
            table=source_table,
            determinant_columns=list(determinant_columns),
            dependent_column=dependent_column,
            db_manager=self.db,
        )

    @staticmethod
    def select_dimension_key_profile(
        profiles: Sequence[FunctionalColumnProfile],
    ) -> FunctionalColumnProfile | None:
        candidates = [
            profile
            for profile in profiles
            if profile.null_ratio <= 0.05
            and profile.uniqueness_ratio >= 0.95
            and is_key_like_column(profile.column_name)
            and not is_measure_candidate(profile)
        ]
        if not candidates:
            return None

        candidates.sort(
            key=lambda profile: (
                profile.identifiability_score,
                profile.uniqueness_ratio,
                -len(profile.column_name),
            ),
            reverse=True,
        )
        return candidates[0]

    @staticmethod
    def is_invalid_dimension_dependent(column_name: str) -> bool:
        if is_key_like_column(column_name):
            return True
        if is_grain_like_column(column_name):
            return True
        return False

    @staticmethod
    def is_grain_signal_column(
        column_name: str,
        profile: FunctionalColumnProfile,
    ) -> bool:
        return is_grain_candidate(profile)

    @staticmethod
    def make_fact_table_name(source_table: str) -> str:
        cleaned_table = re.sub(r"[^0-9A-Za-z_]+", "_", source_table).strip("_").lower()
        return f"logical_{cleaned_table}_fact"

    @staticmethod
    def make_dimension_table_name(source_table: str, key_column: str) -> str:
        cleaned_table = re.sub(r"[^0-9A-Za-z_]+", "_", source_table).strip("_").lower()
        cleaned_key = re.sub(r"[^0-9A-Za-z_]+", "_", key_column).strip("_").lower()
        return f"logical_{cleaned_table}_{cleaned_key}"
