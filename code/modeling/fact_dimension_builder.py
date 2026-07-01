from __future__ import annotations

import re
from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass

from core.clickhouse_manager import CH_DB, ClickHouseManager
from core.naming import (
    is_descriptive_candidate,
    is_grain_candidate,
    is_grain_like_column,
    is_key_like_column,
    is_lookup_key_candidate,
    is_measure_candidate,
    is_measure_like_column,
)
from inference.functional_group_builder import (
    FunctionalColumnGroup,
    FunctionalColumnProfile,
    FunctionalGroupBuilder,
)

DIMENSION_CANDIDATE = "DIMENSION_CANDIDATE"
FACT_CANDIDATE = "FACT_CANDIDATE"


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
            source_columns = {profile.column_name for profile in profiles}
            if any(
                set(dimension.columns) == source_columns
                for dimension in dimensions_by_source.get(source_table, [])
            ):
                continue
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
            dimension_key_columns.update(
                profile.column_name
                for profile in profiles
                if is_key_like_column(profile.column_name)
                or is_lookup_key_candidate(profile)
            )
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
        if any(
            is_grain_like_column(profile.column_name)
            for profile in determinant_profiles
        ):
            return False
        if determinant_profiles and all(
            profile.uniqueness_ratio >= 0.999999 for profile in determinant_profiles
        ):
            return not FactDimensionBuilder.has_strong_transaction_signal(
                list(source_profiles.values()),
            )

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

        return True

    @staticmethod
    def has_strong_transaction_signal(
        profiles: Sequence[FunctionalColumnProfile],
    ) -> bool:
        """Distinguish clear event sources from unique-key dimension groups."""
        measures = [profile for profile in profiles if is_measure_candidate(profile)]
        repeated_grain_columns = [
            profile
            for profile in profiles
            if FactDimensionBuilder.is_grain_signal_column(
                profile.column_name,
                profile,
            )
            and (
                profile.uniqueness_ratio < 0.95
                or is_grain_like_column(profile.column_name)
            )
        ]
        named_measures = [
            profile
            for profile in measures
            if is_measure_like_column(profile.column_name)
        ]
        return (
            len(measures) >= 2
            and len(repeated_grain_columns) >= 2
            and len(named_measures) >= 2
        )

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
