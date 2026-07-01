from inference.functional_group_builder import (
    FunctionalColumnGroup,
    FunctionalColumnProfile,
    FunctionalGroupBuilder,
)


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
        return (
            tuple(determinant_columns) == ("order_id", "product_id")
            and dependent_column == "status"
        )

    monkeypatch.setattr(
        "inference.functional_group_builder.check_column_dependency",
        fake_check_column_dependency,
    )

    profiles = [
        make_profile("order_id", distinct_count=10, uniqueness_ratio=0.2),
        make_profile("product_id", distinct_count=10, uniqueness_ratio=0.2),
        make_profile("quantity", column_type="Int64", distinct_count=20, uniqueness_ratio=0.4),
        make_profile("unit_price", column_type="Float64", distinct_count=20, uniqueness_ratio=0.4),
        make_profile("status", distinct_count=20, uniqueness_ratio=0.4),
        make_profile("note", distinct_count=100, uniqueness_ratio=1.0),
    ]

    groups = FunctionalGroupBuilder(FakeDb()).build_dependency_groups_for_table(
        table_name="order_details",
        profiles=profiles,
    )

    assert any(group.determinant_columns == ("order_id", "product_id") for group in groups)
    combo_group = next(
        group for group in groups if group.determinant_columns == ("order_id", "product_id")
    )
    assert combo_group.dependent_columns == ("status",)
    assert (("order_id", "product_id"), "status") in calls


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
    )

    assert [group.determinant_columns for group in groups] == [("customer_id",)]
    assert (("customer_id", "customer_name"), "order_id") in calls


def test_measure_like_columns_are_not_selected_as_determinants() -> None:
    profiles = [
        make_profile("order_id", distinct_count=100, uniqueness_ratio=1.0),
        make_profile("ship_postal_code", distinct_count=50, uniqueness_ratio=0.5),
        make_profile("freight", column_type="Float64", distinct_count=100, uniqueness_ratio=1.0),
        make_profile("unit_price", column_type="Float64", distinct_count=100, uniqueness_ratio=1.0),
    ]

    candidates = FunctionalGroupBuilder.select_determinant_candidates(
        profiles,
    )

    assert [candidate.column_name for candidate in candidates] == [
        "ship_postal_code",
    ]


def test_existing_group_can_absorb_singleton_through_fd_closure(monkeypatch) -> None:
    def fake_check_column_dependency(
        database,
        table,
        determinant_columns,
        dependent_column,
        db_manager,
        max_violations=0,
    ):
        dependency = (tuple(determinant_columns), dependent_column)
        return dependency in {
            (("col1",), "col2"),
            (("col1", "col2"), "col3"),
        }

    monkeypatch.setattr(
        "inference.functional_group_builder.check_column_dependency",
        fake_check_column_dependency,
    )
    profiles = [
        make_profile("col1", uniqueness_ratio=0.2),
        make_profile("col2", uniqueness_ratio=0.2),
        make_profile("col3", uniqueness_ratio=0.2),
    ]

    groups = FunctionalGroupBuilder(FakeDb()).build_dependency_groups_for_table(
        table_name="observations",
        profiles=profiles,
    )

    assert len(groups) == 1
    assert groups[0].determinant_columns == ("col1", "col2")
    assert groups[0].dependent_columns == ("col3",)
    assert groups[0].all_columns == ("col1", "col2", "col3")
    assert groups[0].reason == "functional_dependency_closure_group"


def test_temporal_columns_are_not_selected_as_determinants() -> None:
    profiles = [
        make_profile("customer_id", distinct_count=10, uniqueness_ratio=0.1),
        make_profile("order_date", column_type="Date", distinct_count=10, uniqueness_ratio=0.1),
        make_profile("shipping_date", distinct_count=10, uniqueness_ratio=0.1),
    ]

    candidates = FunctionalGroupBuilder.select_determinant_candidates(
        profiles,
    )

    assert [candidate.column_name for candidate in candidates] == ["customer_id"]


def test_key_measure_and_grain_columns_are_not_dependents() -> None:
    assert FunctionalGroupBuilder.is_invalid_dependent_column(
        make_profile("customer_id"),
    )
    assert FunctionalGroupBuilder.is_invalid_dependent_column(
        make_profile("amount", column_type="Float64"),
    )
    assert FunctionalGroupBuilder.is_invalid_dependent_column(
        make_profile("order_line_item"),
    )
    assert not FunctionalGroupBuilder.is_invalid_dependent_column(
        make_profile("customer_name"),
    )


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
    )

    customer_group = next(
        group for group in groups if group.determinant_columns == ("customer_id",)
    )
    assert customer_group.dependent_columns == ("customer_city", "customer_name")
    assert customer_group.reason == "stable_functional_dependency_group"


def test_final_groups_do_not_share_columns(monkeypatch) -> None:
    def fake_check_column_dependency(
        database,
        table,
        determinant_columns,
        dependent_column,
        db_manager,
        max_violations=0,
    ):
        determinant_columns = tuple(determinant_columns)
        return (
            determinant_columns == ("order_id",) and dependent_column in {"ship_name", "order_date"}
        ) or (
            determinant_columns == ("ship_name",)
            and dependent_column in {"customer_id", "ship_city"}
        )

    monkeypatch.setattr(
        "inference.functional_group_builder.check_column_dependency",
        fake_check_column_dependency,
    )

    profiles = [
        make_profile("order_id", distinct_count=100, uniqueness_ratio=1.0),
        make_profile("order_date", distinct_count=30, uniqueness_ratio=0.3),
        make_profile("ship_name", distinct_count=20, uniqueness_ratio=0.2),
        make_profile("customer_id", distinct_count=20, uniqueness_ratio=0.2),
        make_profile("ship_city", distinct_count=10, uniqueness_ratio=0.1),
    ]

    groups = FunctionalGroupBuilder(FakeDb()).build_dependency_groups_for_table(
        table_name="orders",
        profiles=profiles,
    )

    assigned_columns = [column for group in groups for column in group.all_columns]

    assert len(assigned_columns) == len(set(assigned_columns))


def test_key_like_determinant_beats_over_general_combination() -> None:
    groups = FunctionalGroupBuilder.select_non_overlapping_groups(
        [
            FunctionalColumnGroup(
                database_name="db",
                source_table="customers",
                group_name="logical_customers_country_segment",
                determinant_columns=("country", "segment"),
                dependent_columns=("customer_name",),
                confidence=0.9,
                reason="stable_functional_dependency_group",
            ),
            FunctionalColumnGroup(
                database_name="db",
                source_table="customers",
                group_name="logical_customers_customer_id",
                determinant_columns=("customer_id",),
                dependent_columns=("customer_name",),
                confidence=0.8,
                reason="stable_functional_dependency_group",
            ),
        ],
        {
            "country": make_profile("country", distinct_count=1, uniqueness_ratio=0.001),
            "segment": make_profile("segment", distinct_count=2, uniqueness_ratio=0.002),
            "customer_id": make_profile(
                "customer_id",
                distinct_count=100,
                uniqueness_ratio=0.1,
                identifiability_score=0.9,
            ),
            "customer_name": make_profile(
                "customer_name", distinct_count=100, uniqueness_ratio=0.1
            ),
        },
    )

    assert [group.determinant_columns for group in groups] == [("customer_id",)]


def test_superstore_style_groups_prefer_entity_owners(monkeypatch) -> None:
    dependencies = {
        ("Order_ID",): {
            "Customer_Name",
            "Order_Date",
            "Region",
            "Segment",
            "Ship_Date",
            "Ship_Mode",
            "State",
        },
        ("Customer_ID",): {"Customer_Name", "Segment"},
        ("Product_ID",): {"Category", "Product_Name", "Sub_Category"},
        ("Postal_Code",): {"City", "Country", "Region", "State"},
    }

    def fake_check_column_dependency(
        database,
        table,
        determinant_columns,
        dependent_column,
        db_manager,
        max_violations=0,
    ):
        return dependent_column in dependencies.get(tuple(determinant_columns), set())

    monkeypatch.setattr(
        "inference.functional_group_builder.check_column_dependency",
        fake_check_column_dependency,
    )

    profiles = [
        make_profile("Row_ID", distinct_count=10000, uniqueness_ratio=1.0),
        make_profile("Order_ID", distinct_count=5000, uniqueness_ratio=0.5),
        make_profile("Customer_ID", distinct_count=800, uniqueness_ratio=0.08),
        make_profile("Customer_Name", distinct_count=800, uniqueness_ratio=0.08),
        make_profile("Segment", distinct_count=3, uniqueness_ratio=0.0003),
        make_profile("Postal_Code", distinct_count=600, uniqueness_ratio=0.06),
        make_profile("City", distinct_count=500, uniqueness_ratio=0.05),
        make_profile("Country", distinct_count=1, uniqueness_ratio=0.0001),
        make_profile("State", distinct_count=50, uniqueness_ratio=0.005),
        make_profile("Region", distinct_count=4, uniqueness_ratio=0.0004),
        make_profile("Product_ID", distinct_count=1800, uniqueness_ratio=0.18),
        make_profile("Product_Name", distinct_count=1800, uniqueness_ratio=0.18),
        make_profile("Category", distinct_count=3, uniqueness_ratio=0.0003),
        make_profile("Sub_Category", distinct_count=17, uniqueness_ratio=0.0017),
        make_profile("Order_Date", column_type="Date", distinct_count=1200, uniqueness_ratio=0.12),
        make_profile("Ship_Date", column_type="Date", distinct_count=1200, uniqueness_ratio=0.12),
        make_profile("Ship_Mode", distinct_count=4, uniqueness_ratio=0.0004),
        make_profile("Sales", column_type="Float64", distinct_count=9000, uniqueness_ratio=0.9),
        make_profile("Quantity", column_type="Int64", distinct_count=10, uniqueness_ratio=0.001),
    ]

    groups = FunctionalGroupBuilder(FakeDb()).build_dependency_groups_for_table(
        table_name="superstore",
        profiles=profiles,
    )
    groups_by_key = {group.determinant_columns: set(group.dependent_columns) for group in groups}

    assert groups_by_key[("Customer_ID",)] == {"Customer_Name", "Segment"}
    assert groups_by_key[("Product_ID",)] == {
        "Category",
        "Product_Name",
        "Sub_Category",
    }
    assert groups_by_key[("Postal_Code",)] == {
        "City",
        "Country",
        "Region",
        "State",
    }
    assert groups_by_key[("Order_ID",)] == {
        "Ship_Mode",
    }
