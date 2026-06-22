from inference.functional_group_builder import FunctionalColumnProfile, FunctionalGroupBuilder


class FakeDb:
    pass


def make_profile(
    column_name: str,
    column_type: str = "String",
    distinct_count: int = 10,
    uniqueness_ratio: float = 0.1,
    identifiability_score: float = 0.5,
) -> FunctionalColumnProfile:
    return FunctionalColumnProfile(
        table_name="observations",
        column_name=column_name,
        column_type=column_type,
        rows=100,
        null_ratio=0.0,
        distinct_count=distinct_count,
        uniqueness_ratio=uniqueness_ratio,
        identifiability_score=identifiability_score,
    )


def test_dependency_group_uses_existing_functional_dependency_checker(monkeypatch) -> None:
    calls = []

    def fake_check_column_dependency(
        database,
        table,
        determinant_columns,
        dependent_column,
        db_manager,
        max_violations=0,
    ):
        determinant_columns = tuple(determinant_columns)
        calls.append((table, determinant_columns, dependent_column))
        return determinant_columns == ("station_id",) and dependent_column in {
            "station_name",
            "latitude",
        }

    monkeypatch.setattr(
        "inference.functional_group_builder.check_column_dependency",
        fake_check_column_dependency,
    )

    profiles = [
        make_profile("station_id", distinct_count=20, uniqueness_ratio=0.2),
        make_profile("station_name", distinct_count=20, uniqueness_ratio=0.2),
        make_profile("latitude", column_type="Float64", distinct_count=20, uniqueness_ratio=0.2),
        make_profile("temperature", column_type="Float64", distinct_count=80, uniqueness_ratio=0.8),
    ]

    groups = FunctionalGroupBuilder(FakeDb()).build_dependency_groups_for_table(
        table_name="observations",
        profiles=profiles,
        max_determinants=5,
        max_determinant_width=1,
        min_dependent_columns=1,
    )

    assert len(groups) == 1
    assert groups[0].determinant_columns == ("station_id",)
    assert groups[0].dependent_columns == ("latitude", "station_name")
    assert calls


def test_dependency_group_can_use_column_combination(monkeypatch) -> None:
    calls = []

    def fake_check_column_dependency(
        database,
        table,
        determinant_columns,
        dependent_column,
        db_manager,
        max_violations=0,
    ):
        calls.append((tuple(determinant_columns), dependent_column))
        return tuple(determinant_columns) == ("order_id", "product_id") and dependent_column in {
            "quantity",
            "unit_price",
        }

    monkeypatch.setattr(
        "inference.functional_group_builder.check_column_dependency",
        fake_check_column_dependency,
    )

    profiles = [
        make_profile("order_id", distinct_count=10, uniqueness_ratio=0.2),
        make_profile("product_id", distinct_count=10, uniqueness_ratio=0.2),
        make_profile("quantity", column_type="Int64", distinct_count=20, uniqueness_ratio=0.4),
        make_profile("unit_price", column_type="Float64", distinct_count=20, uniqueness_ratio=0.4),
        make_profile("note", distinct_count=100, uniqueness_ratio=1.0),
    ]

    groups = FunctionalGroupBuilder(FakeDb()).build_dependency_groups_for_table(
        table_name="order_details",
        profiles=profiles,
        max_determinants=4,
        max_determinant_width=2,
        min_dependent_columns=1,
    )

    assert any(group.determinant_columns == ("order_id", "product_id") for group in groups)
    combo_group = next(group for group in groups if group.determinant_columns == ("order_id", "product_id"))
    assert combo_group.dependent_columns == ("quantity", "unit_price")
    assert (("order_id", "product_id"), "quantity") in calls


def test_simple_determinants_are_preferred_before_combinations(monkeypatch) -> None:
    calls = []

    def fake_check_column_dependency(
        database,
        table,
        determinant_columns,
        dependent_column,
        db_manager,
        max_violations=0,
    ):
        determinant_columns = tuple(determinant_columns)
        calls.append((determinant_columns, dependent_column))
        return determinant_columns == ("customer_id",) and dependent_column == "customer_name"

    monkeypatch.setattr(
        "inference.functional_group_builder.check_column_dependency",
        fake_check_column_dependency,
    )

    profiles = [
        make_profile("order_id", distinct_count=100, uniqueness_ratio=1.0),
        make_profile("customer_id", distinct_count=10, uniqueness_ratio=0.1),
        make_profile("customer_name", distinct_count=10, uniqueness_ratio=0.1),
    ]

    groups = FunctionalGroupBuilder(FakeDb()).build_dependency_groups_for_table(
        table_name="orders",
        profiles=profiles,
        max_determinants=5,
        max_determinant_width=2,
        min_dependent_columns=1,
    )

    assert [group.determinant_columns for group in groups] == [("customer_id",)]
    assert not any(len(determinants) > 1 for determinants, _ in calls)


def test_measure_like_columns_are_not_selected_as_determinants() -> None:
    profiles = [
        make_profile("order_id", distinct_count=100, uniqueness_ratio=1.0),
        make_profile("ship_postal_code", distinct_count=50, uniqueness_ratio=0.5),
        make_profile("freight", column_type="Float64", distinct_count=100, uniqueness_ratio=1.0),
        make_profile("unit_price", column_type="Float64", distinct_count=100, uniqueness_ratio=1.0),
    ]

    candidates = FunctionalGroupBuilder.select_determinant_candidates(
        profiles,
        max_determinants=10,
    )

    assert [candidate.column_name for candidate in candidates] == [
        "order_id",
        "ship_postal_code",
    ]


def test_repeated_determinant_can_form_stable_group(monkeypatch) -> None:
    def fake_check_column_dependency(
        database,
        table,
        determinant_columns,
        dependent_column,
        db_manager,
        max_violations=0,
    ):
        return tuple(determinant_columns) == ("customer_id",) and dependent_column in {
            "customer_name",
            "customer_city",
        }

    monkeypatch.setattr(
        "inference.functional_group_builder.check_column_dependency",
        fake_check_column_dependency,
    )

    profiles = [
        make_profile("customer_id", distinct_count=5, uniqueness_ratio=0.05),
        make_profile("customer_name", distinct_count=5, uniqueness_ratio=0.05),
        make_profile("customer_city", distinct_count=4, uniqueness_ratio=0.04),
        make_profile("order_id", distinct_count=100, uniqueness_ratio=1.0),
    ]

    groups = FunctionalGroupBuilder(FakeDb()).build_dependency_groups_for_table(
        table_name="orders",
        profiles=profiles,
        max_determinants=5,
        max_determinant_width=1,
        min_dependent_columns=1,
    )

    customer_group = next(
        group for group in groups if group.determinant_columns == ("customer_id",)
    )
    assert customer_group.dependent_columns == ("customer_city", "customer_name")
    assert customer_group.reason == "stable_functional_dependency_group"
