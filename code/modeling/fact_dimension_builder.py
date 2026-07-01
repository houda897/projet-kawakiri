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
)
from inference.functional_group_builder import (
    FunctionalColumnGroup,
    FunctionalColumnProfile,
    FunctionalGroupBuilder,
)
from inference.source_structure import SourceStructureAnalyzer, SourceTableStructure

DIMENSION_CANDIDATE = "DIMENSION_CANDIDATE"
FACT_CANDIDATE = "FACT_CANDIDATE"
UNKNOWN_CANDIDATE = "UNKNOWN_CANDIDATE"


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
        source_structures = SourceStructureAnalyzer(self.db).load_structures()

        dimension_plans = self.build_dimension_tables(
            groups,
            profiles_by_table_and_column,
            source_structures,
        )
        fact_plans = self.build_fact_tables(
            groups,
            profiles_by_table,
            dimension_plans,
            source_structures,
        )
        unknown_plans = self.build_unknown_tables(
            profiles_by_table,
            dimension_plans + fact_plans,
            source_structures,
        )

        return sorted(
            dimension_plans + fact_plans + unknown_plans,
            key=lambda plan: (plan.source_table, plan.logical_table_role, plan.logical_table_name),
        )

    def build_dimension_tables(
        self,
        groups: list[FunctionalColumnGroup],
        profiles_by_table_and_column: Mapping[str, Mapping[str, FunctionalColumnProfile]],
        source_structures: Mapping[str, SourceTableStructure] | None = None,
    ) -> list[LogicalTablePlan]:
        source_structures = source_structures or {}
        dimensions = []

        for group in groups:
            source_profiles = profiles_by_table_and_column.get(group.source_table, {})
            if not self.is_dimension_group(
                group,
                source_profiles,
                source_structures.get(group.source_table),
            ):
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
        source_structures: Mapping[str, SourceTableStructure] | None = None,
    ) -> list[LogicalTablePlan]:
        source_structures = source_structures or {}
        dimensions_by_source: dict[str, list[LogicalTablePlan]] = defaultdict(list)
        for dimension in dimension_plans:
            dimensions_by_source[dimension.source_table].append(dimension)

        facts = []
        multi_table_source = len(profiles_by_table) > 1
        for source_table, profiles in profiles_by_table.items():
            source_structure = source_structures.get(source_table)
            source_columns = {profile.column_name for profile in profiles}
            if any(
                set(dimension.columns) == source_columns
                for dimension in dimensions_by_source.get(source_table, [])
            ):
                continue
            if (
                multi_table_source
                and source_structures
                and not dimensions_by_source.get(source_table)
                and (source_structure is None or source_structure.outgoing_count == 0)
            ):
                continue
            if not self.is_transactional_source_table(
                source_table,
                profiles,
                source_structure=source_structure,
            ):
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
                if is_key_like_column(profile.column_name) or is_lookup_key_candidate(profile)
            )
            if source_structure and source_structure.entity_key:
                dimension_key_columns.update(
                    self.split_columns(source_structure.entity_key.column_name)
                )
                dimension_key_columns.update(
                    column
                    for relationship in source_structure.outgoing_relationships
                    for column in self.split_columns(relationship.source_column)
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
                source_structure=source_structure,
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

    def build_unknown_tables(
        self,
        profiles_by_table: Mapping[str, Sequence[FunctionalColumnProfile]],
        existing_plans: list[LogicalTablePlan],
        source_structures: Mapping[str, SourceTableStructure] | None = None,
    ) -> list[LogicalTablePlan]:
        """Keep unresolved sources observable without forcing a fact/dimension role."""
        source_structures = source_structures or {}
        planned_sources = {plan.source_table for plan in existing_plans}
        unknown_plans = []

        for source_table, profiles in profiles_by_table.items():
            if source_table in planned_sources or not profiles:
                continue
            structure = source_structures.get(source_table)
            determinants = ()
            if structure and structure.entity_key:
                determinants = self.split_columns(structure.entity_key.column_name)
            cleaned_table = re.sub(r"[^0-9A-Za-z_]+", "_", source_table).strip("_").lower()
            table_name = f"logical_{cleaned_table}_unclassified"
            unknown_plans.append(
                LogicalTablePlan(
                    database_name=CH_DB,
                    logical_table_name=table_name,
                    source_table=source_table,
                    group_name=table_name,
                    determinant_columns=determinants,
                    columns=tuple(profile.column_name for profile in profiles),
                    logical_table_role=UNKNOWN_CANDIDATE,
                    distinct_rows=False,
                )
            )

        return unknown_plans

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
        source_structure: SourceTableStructure | None = None,
    ) -> bool:
        if not group.dependent_columns:
            return False

        if group.group_role == "NORMALIZED_ENTITY":
            if source_structure is None or source_structure.entity_key is None:
                return False
            return not FactDimensionBuilder.has_strong_transaction_signal(
                list(source_profiles.values()),
                source_structure=source_structure,
            )

        determinant_profiles = [
            source_profiles[column]
            for column in group.determinant_columns
            if column in source_profiles
        ]
        if any(is_grain_like_column(profile.column_name) for profile in determinant_profiles):
            return False
        if determinant_profiles and all(
            profile.uniqueness_ratio >= 0.999999 for profile in determinant_profiles
        ):
            return not FactDimensionBuilder.has_strong_transaction_signal(
                list(source_profiles.values()),
                source_structure=source_structure,
            )

        if (
            determinant_profiles
            and not any(is_key_like_column(profile.column_name) for profile in determinant_profiles)
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
        source_structure: SourceTableStructure | None = None,
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

        if measure_columns and grain_columns:
            return True
        if source_structure is None or source_structure.entity_key is None:
            return False
        entity_key_columns = FactDimensionBuilder.split_columns(
            source_structure.entity_key.column_name
        )
        return (
            len(entity_key_columns) > 1
            and source_structure.outgoing_count >= 2
            and bool(grain_columns)
        )

    @staticmethod
    def is_transactional_source_table(
        source_table: str,
        profiles: Sequence[FunctionalColumnProfile],
        source_structure: SourceTableStructure | None = None,
    ) -> bool:
        measure_columns = [profile for profile in profiles if is_measure_candidate(profile)]
        grain_columns = [
            profile
            for profile in profiles
            if FactDimensionBuilder.is_grain_signal_column(
                profile.column_name,
                profile,
            )
        ]
        if source_structure and source_structure.entity_key:
            entity_key_columns = FactDimensionBuilder.split_columns(
                source_structure.entity_key.column_name
            )
            has_composite_event_grain = len(entity_key_columns) > 1
            if source_structure.outgoing_count > 0 and measure_columns and grain_columns:
                return True
            if source_structure.outgoing_count >= 2 and has_composite_event_grain and grain_columns:
                return True
            if source_structure.incoming_count > 0:
                return False

        if not measure_columns or not grain_columns:
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
            (
                source_structure is None
                or (
                    source_structure.incoming_count == 0
                    and source_structure.outgoing_count == 0
                )
            )
            and len(grain_columns) == 1
            and grain_columns[0].uniqueness_ratio >= 0.95
            and descriptive_columns
            and len(measure_columns) <= len(descriptive_columns)
        ):
            return False

        return True

    @staticmethod
    def has_strong_transaction_signal(
        profiles: Sequence[FunctionalColumnProfile],
        source_structure: SourceTableStructure | None = None,
    ) -> bool:
        """Detect event evidence without requiring domain-specific measure names."""
        measures = [profile for profile in profiles if is_measure_candidate(profile)]
        repeated_grain_columns = [
            profile
            for profile in profiles
            if FactDimensionBuilder.is_grain_signal_column(
                profile.column_name,
                profile,
            )
            and (profile.uniqueness_ratio < 0.95 or is_grain_like_column(profile.column_name))
        ]
        if source_structure and source_structure.entity_key:
            entity_key_columns = FactDimensionBuilder.split_columns(
                source_structure.entity_key.column_name
            )
            if source_structure.outgoing_count > 0 and measures:
                has_temporal_column = any(
                    "Date" in profile.column_type or "Time" in profile.column_type
                    for profile in profiles
                )
                if len(entity_key_columns) > 1 or has_temporal_column:
                    return True
            if source_structure.outgoing_count >= 2 and len(entity_key_columns) > 1:
                return True

        return bool(measures) and len(repeated_grain_columns) >= 2

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
    def split_columns(columns: str) -> tuple[str, ...]:
        return tuple(column.strip() for column in columns.split(",") if column.strip())
