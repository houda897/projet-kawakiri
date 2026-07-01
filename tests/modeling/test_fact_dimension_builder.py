from inference.functional_group_builder import FunctionalColumnGroup, FunctionalColumnProfile
from inference.join_candidate import JoinPrimaryKeyCandidate
from inference.primary_key import PrimaryKeyCandidate
from inference.source_structure import SourceTableStructure
from modeling.fact_dimension_builder import (
    DIMENSION_CANDIDATE,
    FACT_CANDIDATE,
    UNKNOWN_CANDIDATE,
    FactDimensionBuilder,
    LogicalTablePlan,
)


class FakeDb:
    pass


def make_source_structure(
    table: str,
    key: str,
    *,
    incoming: tuple[str, ...] = (),
    outgoing: tuple[tuple[str, str], ...] = (),
) -> SourceTableStructure:
    entity_key = PrimaryKeyCandidate(
        database_name="db",
        table_name=table,
        column_name=key,
        column_type="String",
        rows=100,
        null_ratio=0.0,
        uniqueness_ratio=1.0,
        identifiability_score=0.9,
        confidence=0.93,
        reason="exact",
        analysis_scope="SOURCE",
        is_official=False,
    )
    incoming_edges = tuple(
        JoinPrimaryKeyCandidate(
            source_table=source,
            source_column=key,
            target_table=table,
            target_column=key,
            source_non_null_rows=100,
            matched_rows=100,
            join_success_ratio=1.0,
            analysis_scope="SOURCE",
        )
        for source in incoming
    )
    outgoing_edges = tuple(
        JoinPrimaryKeyCandidate(
            source_table=table,
            source_column=source_column,
            target_table=target_table,
            target_column=source_column,
            source_non_null_rows=100,
            matched_rows=100,
            join_success_ratio=1.0,
            analysis_scope="SOURCE",
        )
        for source_column, target_table in outgoing
    )
    return SourceTableStructure(
        table_name=table,
        entity_key=entity_key,
        incoming_relationships=incoming_edges,
        outgoing_relationships=outgoing_edges,
    )


def make_profile(
    table_name: str,
    column_name: str,
    column_type: str = "String",
    uniqueness_ratio: float = 0.1,
    distinct_count: int = 10,
    identifiability_score: float = 0.5,
) -> FunctionalColumnProfile:
    return FunctionalColumnProfile(
        table_name=table_name,
        column_name=column_name,
        column_type=column_type,
        rows=100,
        null_ratio=0.0,
        distinct_count=distinct_count,
        uniqueness_ratio=uniqueness_ratio,
        identifiability_score=identifiability_score,
    )


def test_dimension_group_becomes_dimension_plan() -> None:
    group = FunctionalColumnGroup(
        database_name="db",
        source_table="sales_raw",
        group_name="logical_sales_raw_client_id",
        determinant_columns=("client_id",),
        dependent_columns=("client_name", "client_city"),
        confidence=0.9,
        reason="stable_functional_dependency_group",
    )
    profiles = {
        "client_id": make_profile("sales_raw", "client_id"),
        "client_name": make_profile("sales_raw", "client_name"),
        "client_city": make_profile("sales_raw", "client_city"),
    }

    plans = FactDimensionBuilder(FakeDb()).build_dimension_tables(
        [group],
        {"sales_raw": profiles},
    )

    assert len(plans) == 1
    assert plans[0].logical_table_role == DIMENSION_CANDIDATE
    assert plans[0].distinct_rows
    assert plans[0].columns == ("client_id", "client_name", "client_city")


def test_unique_line_identifier_group_is_not_dimension_plan() -> None:
    group = FunctionalColumnGroup(
        database_name="db",
        source_table="sales_raw",
        group_name="logical_sales_raw_id_ligne",
        determinant_columns=("id_ligne",),
        dependent_columns=("client_id", "amount"),
        confidence=0.95,
        reason="stable_functional_dependency_group",
    )
    profiles = {
        "id_ligne": make_profile("sales_raw", "id_ligne", uniqueness_ratio=1.0),
        "client_id": make_profile("sales_raw", "client_id"),
        "amount": make_profile("sales_raw", "amount", "Float64", uniqueness_ratio=0.2),
    }

    plans = FactDimensionBuilder(FakeDb()).build_dimension_tables(
        [group],
        {"sales_raw": profiles},
    )

    assert plans == []


def test_fact_plan_keeps_dimension_keys_and_measure_columns() -> None:
    dimension_plan = FactDimensionBuilder(FakeDb()).build_dimension_tables(
        [
            FunctionalColumnGroup(
                database_name="db",
                source_table="sales_raw",
                group_name="logical_sales_raw_client_id",
                determinant_columns=("client_id",),
                dependent_columns=("client_name", "client_city"),
                confidence=0.9,
                reason="stable_functional_dependency_group",
            )
        ],
        {
            "sales_raw": {
                "client_id": make_profile("sales_raw", "client_id"),
                "client_name": make_profile("sales_raw", "client_name"),
                "client_city": make_profile("sales_raw", "client_city"),
            }
        },
    )

    profiles = {
        "sales_raw": [
            make_profile("sales_raw", "client_id"),
            make_profile("sales_raw", "client_name"),
            make_profile("sales_raw", "client_city"),
            make_profile("sales_raw", "invoice_no"),
            make_profile("sales_raw", "product_id"),
            make_profile("sales_raw", "quantity", "Int64", uniqueness_ratio=0.2),
            make_profile("sales_raw", "amount", "Float64", uniqueness_ratio=0.2),
        ]
    }

    plans = FactDimensionBuilder(FakeDb()).build_fact_tables(
        groups=[],
        profiles_by_table=profiles,
        dimension_plans=dimension_plan,
    )

    assert len(plans) == 1
    assert plans[0].logical_table_role == FACT_CANDIDATE
    assert not plans[0].distinct_rows
    assert plans[0].columns == ("client_id", "invoice_no", "product_id", "quantity", "amount")


def test_measure_dependent_group_is_not_dimension_plan() -> None:
    group = FunctionalColumnGroup(
        database_name="db",
        source_table="sales_raw",
        group_name="logical_sales_raw_date_id_product_id",
        determinant_columns=("date_id", "product_id"),
        dependent_columns=("revenue", "sale_id"),
        confidence=0.9,
        reason="stable_functional_dependency_group",
    )
    profiles = {
        "date_id": make_profile("sales_raw", "date_id", "Date"),
        "product_id": make_profile("sales_raw", "product_id"),
        "revenue": make_profile("sales_raw", "revenue", "Float64"),
        "sale_id": make_profile("sales_raw", "sale_id"),
    }

    plans = FactDimensionBuilder(FakeDb()).build_dimension_tables(
        [group],
        {"sales_raw": profiles},
    )

    assert plans == []


def test_lookup_table_without_transactional_grain_does_not_become_fact() -> None:
    profiles = {
        "products": [
            make_profile("products", "product_id", uniqueness_ratio=1.0),
            make_profile("products", "product_name"),
            make_profile("products", "category"),
            make_profile("products", "unit_price", "Float64", uniqueness_ratio=0.5),
        ]
    }

    plans = FactDimensionBuilder(FakeDb()).build_fact_tables(
        groups=[],
        profiles_by_table=profiles,
        dimension_plans=[],
    )

    assert plans == []


def test_calendar_table_does_not_become_fact() -> None:
    profiles = {
        "calendar": [
            make_profile("calendar", "date_id", "Date", uniqueness_ratio=1.0),
            make_profile("calendar", "month", "Int64", uniqueness_ratio=0.1),
            make_profile("calendar", "month_name"),
            make_profile("calendar", "year", "Int64", uniqueness_ratio=0.1),
        ]
    }

    plans = FactDimensionBuilder(FakeDb()).build_fact_tables(
        groups=[],
        profiles_by_table=profiles,
        dimension_plans=[],
    )

    assert plans == []


def test_unresolved_source_is_preserved_as_neutral_logical_table() -> None:
    profiles = {
        "observations": [
            make_profile("observations", "label"),
            make_profile("observations", "comment"),
        ]
    }

    plans = FactDimensionBuilder(FakeDb()).build_unknown_tables(
        profiles,
        existing_plans=[],
    )

    assert len(plans) == 1
    assert plans[0].logical_table_role == UNKNOWN_CANDIDATE
    assert plans[0].columns == ("label", "comment")
    assert not plans[0].distinct_rows


def test_over_general_customer_group_is_rejected_when_unique_key_exists() -> None:
    group = FunctionalColumnGroup(
        database_name="db",
        source_table="customers",
        group_name="logical_customers_country_segment",
        determinant_columns=("country", "segment"),
        dependent_columns=("customer_name",),
        confidence=0.9,
        reason="stable_functional_dependency_group",
    )
    profiles = {
        "customer_id": make_profile(
            "customers",
            "customer_id",
            uniqueness_ratio=1.0,
            identifiability_score=1.0,
        ),
        "customer_name": make_profile("customers", "customer_name"),
        "country": make_profile("customers", "country"),
        "segment": make_profile("customers", "segment"),
    }

    plans = FactDimensionBuilder(FakeDb()).build_dimension_tables(
        [group],
        {"customers": profiles},
    )

    assert plans == []


def test_unique_functional_group_becomes_complete_dimension() -> None:
    group = FunctionalColumnGroup(
        database_name="db",
        source_table="customers",
        group_name="logical_customers_customer_id",
        determinant_columns=("customer_id",),
        dependent_columns=("customer_name", "country", "segment"),
        confidence=1.0,
        reason="stable_functional_dependency_group",
    )
    profiles = {
        "customer_id": make_profile("customers", "customer_id", uniqueness_ratio=1.0),
        "customer_name": make_profile("customers", "customer_name"),
        "country": make_profile("customers", "country"),
        "segment": make_profile("customers", "segment"),
    }

    plans = FactDimensionBuilder(FakeDb()).build_dimension_tables(
        [group],
        {"customers": profiles},
    )

    assert len(plans) == 1
    assert plans[0].logical_table_role == DIMENSION_CANDIDATE
    assert plans[0].columns == (
        "customer_id",
        "customer_name",
        "country",
        "segment",
    )


def test_lookup_source_with_numeric_attribute_does_not_become_fact() -> None:
    profiles = {
        "categories_source": [
            make_profile(
                "categories_source",
                "id",
                "Int64",
                uniqueness_ratio=1.0,
                identifiability_score=1.0,
            ),
            make_profile("categories_source", "nom", uniqueness_ratio=1.0),
            make_profile("categories_source", "priorite", "Int64", uniqueness_ratio=1.0),
        ]
    }

    plans = FactDimensionBuilder(FakeDb()).build_fact_tables(
        groups=[],
        profiles_by_table=profiles,
        dimension_plans=[],
    )

    assert plans == []


def test_sales_source_becomes_fact_with_keys_grain_and_measures() -> None:
    profiles = {
        "sales": [
            make_profile("sales", "sale_id", uniqueness_ratio=1.0),
            make_profile("sales", "customer_id"),
            make_profile("sales", "product_id"),
            make_profile("sales", "date_id", "Date"),
            make_profile("sales", "quantity", "Int64"),
            make_profile("sales", "revenue", "Float64"),
        ]
    }

    plans = FactDimensionBuilder(FakeDb()).build_fact_tables(
        groups=[],
        profiles_by_table=profiles,
        dimension_plans=[],
    )

    assert len(plans) == 1
    assert plans[0].logical_table_role == FACT_CANDIDATE
    assert plans[0].columns == (
        "sale_id",
        "customer_id",
        "product_id",
        "date_id",
        "quantity",
        "revenue",
    )


def legacy_contextual_dimensions_move_descriptive_columns_out_of_fact(monkeypatch) -> None:
    dependencies = {
        ("Product_ID",): {"Product_Name", "Category", "Sub_Category"},
        ("Customer_ID",): {"Customer_Name", "Segment"},
        ("Postal_Code",): {"City", "Country", "State", "Region"},
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
        "modeling.fact_dimension_builder.check_column_dependency",
        fake_check_column_dependency,
    )

    builder = FactDimensionBuilder(FakeDb())
    profiles = {
        "superstore": [
            make_profile("superstore", "Row_ID", uniqueness_ratio=1.0),
            make_profile("superstore", "Order_ID", uniqueness_ratio=0.5),
            make_profile("superstore", "Customer_ID", uniqueness_ratio=0.08),
            make_profile("superstore", "Customer_Name", uniqueness_ratio=0.08),
            make_profile("superstore", "Segment", uniqueness_ratio=0.0003),
            make_profile("superstore", "Postal_Code", uniqueness_ratio=0.06),
            make_profile("superstore", "City", uniqueness_ratio=0.05),
            make_profile("superstore", "Country", uniqueness_ratio=0.0001),
            make_profile("superstore", "State", uniqueness_ratio=0.005),
            make_profile("superstore", "Region", uniqueness_ratio=0.0004),
            make_profile("superstore", "Product_ID", uniqueness_ratio=0.18),
            make_profile("superstore", "Product_Name", uniqueness_ratio=0.18),
            make_profile("superstore", "Category", uniqueness_ratio=0.0003),
            make_profile("superstore", "Sub_Category", uniqueness_ratio=0.0017),
            make_profile("superstore", "Sales", "Float64", uniqueness_ratio=0.9),
            make_profile("superstore", "Quantity", "Int64", uniqueness_ratio=0.001),
            make_profile("superstore", "Discount", "Float64", uniqueness_ratio=0.002),
            make_profile("superstore", "Profit", "Float64", uniqueness_ratio=0.9),
        ]
    }
    product_dimension = LogicalTablePlan(
        database_name="db",
        logical_table_name="logical_superstore_product_id",
        source_table="superstore",
        group_name="logical_superstore_product_id",
        determinant_columns=("Product_ID",),
        columns=("Product_ID", "Category", "Sub_Category"),
        logical_table_role=DIMENSION_CANDIDATE,
        distinct_rows=True,
    )

    dimensions = builder.build_contextual_dimension_tables(
        profiles,
        existing_dimensions=[product_dimension],
    )
    dimensions = builder.enrich_dimension_tables(
        [product_dimension] + dimensions,
        profiles,
    )
    facts = builder.build_fact_tables(
        groups=[],
        profiles_by_table=profiles,
        dimension_plans=dimensions,
    )

    dimensions_by_key = {
        dimension.determinant_columns: set(dimension.columns) for dimension in dimensions
    }
    assert dimensions_by_key[("Product_ID",)] == {
        "Product_ID",
        "Product_Name",
        "Category",
        "Sub_Category",
    }
    assert dimensions_by_key[("Customer_ID",)] == {
        "Customer_ID",
        "Customer_Name",
        "Segment",
    }
    assert dimensions_by_key[("Postal_Code",)] == {
        "Postal_Code",
        "City",
        "Country",
        "State",
        "Region",
    }
    assert facts[0].columns == (
        "Row_ID",
        "Order_ID",
        "Customer_ID",
        "Postal_Code",
        "Product_ID",
        "Sales",
        "Quantity",
        "Discount",
        "Profit",
    )


def legacy_contextual_dimension_enrichment_requires_functional_dependency(monkeypatch) -> None:
    def fake_check_column_dependency(
        database,
        table,
        determinant_columns,
        dependent_column,
        db_manager,
        max_violations=0,
    ):
        return False

    monkeypatch.setattr(
        "modeling.fact_dimension_builder.check_column_dependency",
        fake_check_column_dependency,
    )

    builder = FactDimensionBuilder(FakeDb())
    profiles = {
        "sales": [
            make_profile("sales", "product_id", uniqueness_ratio=0.2),
            make_profile("sales", "product_name", uniqueness_ratio=0.2),
        ]
    }
    product_dimension = LogicalTablePlan(
        database_name="db",
        logical_table_name="logical_sales_product_id",
        source_table="sales",
        group_name="logical_sales_product_id",
        determinant_columns=("product_id",),
        columns=("product_id",),
        logical_table_role=DIMENSION_CANDIDATE,
        distinct_rows=True,
    )

    dimensions = builder.enrich_dimension_tables([product_dimension], profiles)

    assert dimensions[0].columns == ("product_id",)


def legacy_unstable_descriptive_column_promotes_dimension_to_composite_key(
    monkeypatch,
) -> None:
    def fake_check_column_dependency(
        database,
        table,
        determinant_columns,
        dependent_column,
        db_manager,
        max_violations=0,
    ):
        return tuple(determinant_columns) == (
            "Product_ID",
            "Product_Name",
        ) and dependent_column in {
            "Category",
            "Sub_Category",
        }

    monkeypatch.setattr(
        "modeling.fact_dimension_builder.check_column_dependency",
        fake_check_column_dependency,
    )

    builder = FactDimensionBuilder(FakeDb())
    dimensions = [
        LogicalTablePlan(
            database_name="db",
            logical_table_name="logical_superstore_product_id",
            source_table="superstore",
            group_name="logical_superstore_product_id",
            determinant_columns=("Product_ID",),
            columns=("Product_ID", "Category", "Sub_Category"),
            logical_table_role=DIMENSION_CANDIDATE,
            distinct_rows=True,
        )
    ]
    profiles = {
        "superstore": [
            make_profile("superstore", "Product_ID", uniqueness_ratio=0.18),
            make_profile("superstore", "Product_Name", uniqueness_ratio=0.18),
            make_profile("superstore", "Category", uniqueness_ratio=0.0003),
            make_profile("superstore", "Sub_Category", uniqueness_ratio=0.0017),
            make_profile("superstore", "Sales", "Float64", uniqueness_ratio=0.9),
            make_profile("superstore", "Row_ID", uniqueness_ratio=1.0),
        ]
    }

    promoted = builder.promote_composite_dimension_keys(dimensions, profiles)
    facts = builder.build_fact_tables(
        groups=[],
        profiles_by_table=profiles,
        dimension_plans=promoted,
    )

    assert promoted[0].determinant_columns == ("Product_ID", "Product_Name")
    assert promoted[0].columns == (
        "Product_ID",
        "Product_Name",
        "Category",
        "Sub_Category",
    )
    assert facts[0].columns == ("Product_ID", "Product_Name", "Sales", "Row_ID")


def test_composite_key_column_stays_in_fact_even_if_dependent_elsewhere() -> None:
    profiles = {
        "superstore": [
            make_profile("superstore", "Order_ID", uniqueness_ratio=0.5),
            make_profile("superstore", "Postal_Code", uniqueness_ratio=0.06),
            make_profile("superstore", "City", uniqueness_ratio=0.05),
            make_profile("superstore", "Country", uniqueness_ratio=0.0001),
            make_profile("superstore", "Sales", "Float64", uniqueness_ratio=0.9),
            make_profile("superstore", "Row_ID", uniqueness_ratio=1.0),
        ]
    }
    dimensions = [
        LogicalTablePlan(
            database_name="db",
            logical_table_name="logical_superstore_order_id",
            source_table="superstore",
            group_name="logical_superstore_order_id",
            determinant_columns=("Order_ID",),
            columns=("Order_ID", "City"),
            logical_table_role=DIMENSION_CANDIDATE,
            distinct_rows=True,
        ),
        LogicalTablePlan(
            database_name="db",
            logical_table_name="logical_superstore_postal_code_city",
            source_table="superstore",
            group_name="logical_superstore_postal_code_city",
            determinant_columns=("Postal_Code", "City"),
            columns=("Postal_Code", "City", "Country"),
            logical_table_role=DIMENSION_CANDIDATE,
            distinct_rows=True,
        ),
    ]

    facts = FactDimensionBuilder(FakeDb()).build_fact_tables(
        groups=[],
        profiles_by_table=profiles,
        dimension_plans=dimensions,
    )

    assert facts[0].columns == (
        "Order_ID",
        "Postal_Code",
        "City",
        "Sales",
        "Row_ID",
    )


def legacy_raw_table_with_measures_does_not_become_fallback_dimension() -> None:
    profiles = {
        "ventes_raw": [
            make_profile("ventes_raw", "id_ligne", uniqueness_ratio=1.0),
            make_profile("ventes_raw", "client_id", uniqueness_ratio=0.2),
            make_profile("ventes_raw", "product_id", uniqueness_ratio=0.4),
            make_profile("ventes_raw", "customer_name", uniqueness_ratio=0.2),
            make_profile("ventes_raw", "sales", "Float64", uniqueness_ratio=0.8),
            make_profile("ventes_raw", "quantity", "Int64", uniqueness_ratio=0.05),
        ]
    }

    plans = FactDimensionBuilder(FakeDb()).build_fallback_dimension_tables(
        profiles,
        existing_dimensions=[],
    )

    assert plans == []


def test_single_grain_table_with_measure_can_be_fact() -> None:
    profiles = {
        "daily_balance": [
            make_profile("daily_balance", "account_id"),
            make_profile("daily_balance", "amount", "Float64"),
        ]
    }

    plans = FactDimensionBuilder(FakeDb()).build_fact_tables(
        groups=[],
        profiles_by_table=profiles,
        dimension_plans=[],
    )

    assert len(plans) == 1
    assert plans[0].logical_table_role == FACT_CANDIDATE


def test_ocean_observations_become_fact_without_erp_measure_names() -> None:
    profiles = {
        "ocean_observations": [
            make_profile("ocean_observations", "station_id"),
            make_profile("ocean_observations", "observed_at", "DateTime", uniqueness_ratio=0.8),
            make_profile("ocean_observations", "temperature", "Float64", uniqueness_ratio=0.7),
            make_profile("ocean_observations", "salinity", "Float64", uniqueness_ratio=0.6),
            make_profile(
                "ocean_observations", "quality_flag", distinct_count=3, uniqueness_ratio=0.03
            ),
        ]
    }

    plans = FactDimensionBuilder(FakeDb()).build_fact_tables(
        groups=[],
        profiles_by_table=profiles,
        dimension_plans=[],
    )

    assert len(plans) == 1
    assert plans[0].logical_table_role == FACT_CANDIDATE
    assert plans[0].columns == (
        "station_id",
        "observed_at",
        "temperature",
        "salinity",
    )


def test_single_measure_payment_source_becomes_fact_with_relationship_evidence() -> None:
    profiles = {
        "payments": [
            make_profile("payments", "order_id", uniqueness_ratio=0.8),
            make_profile("payments", "payment_sequence", uniqueness_ratio=0.1),
            make_profile("payments", "payment_type"),
            make_profile("payments", "payment_value", "Float64", uniqueness_ratio=0.7),
        ]
    }
    structure = make_source_structure(
        "payments",
        "order_id, payment_sequence",
        outgoing=(("order_id", "orders"),),
    )

    plans = FactDimensionBuilder(FakeDb()).build_fact_tables(
        groups=[],
        profiles_by_table=profiles,
        dimension_plans=[],
        source_structures={"payments": structure},
    )

    assert len(plans) == 1
    assert plans[0].logical_table_role == FACT_CANDIDATE
    assert set(plans[0].columns) == {"order_id", "payment_sequence", "payment_value"}


def test_referenced_normalized_order_header_remains_one_dimension_group() -> None:
    profiles = {
        "order_id": make_profile("orders", "order_id", uniqueness_ratio=1.0),
        "customer_id": make_profile("orders", "customer_id", uniqueness_ratio=1.0),
        "order_status": make_profile("orders", "order_status"),
        "purchased_at": make_profile("orders", "purchased_at", "DateTime"),
    }
    group = FunctionalColumnGroup(
        database_name="db",
        source_table="orders",
        group_name="logical_orders_order_id",
        determinant_columns=("order_id",),
        dependent_columns=("customer_id", "order_status", "purchased_at"),
        confidence=1.0,
        reason="normalized_source_entity_group",
        group_role="NORMALIZED_ENTITY",
    )
    structure = make_source_structure(
        "orders",
        "order_id",
        incoming=("items", "payments"),
        outgoing=(("customer_id", "customers"),),
    )

    plans = FactDimensionBuilder(FakeDb()).build_dimension_tables(
        [group],
        {"orders": profiles},
        {"orders": structure},
    )

    assert len(plans) == 1
    assert plans[0].determinant_columns == ("order_id",)
    assert set(plans[0].columns) == set(profiles)


def legacy_uppercase_erp_lookup_sources_become_complete_dimensions() -> None:
    profiles = {
        "BusinessPartners": [
            make_profile("BusinessPartners", "PARTNERID", uniqueness_ratio=1.0),
            make_profile("BusinessPartners", "COMPANYNAME"),
            make_profile("BusinessPartners", "ADDRESSID"),
            make_profile("BusinessPartners", "CHANGEDBY", "Int64"),
        ],
        "Employees": [
            make_profile("Employees", "EMPLOYEEID", uniqueness_ratio=1.0),
            make_profile("Employees", "NAME_FIRST"),
            make_profile("Employees", "NAME_LAST"),
            make_profile("Employees", "ADDRESSID"),
        ],
        "Products": [
            make_profile("Products", "PRODUCTID", uniqueness_ratio=1.0),
            make_profile("Products", "PRODUCTPICURL"),
            make_profile("Products", "PRODCATEGORYID"),
            make_profile("Products", "PRICE", "Float64"),
        ],
    }

    plans = FactDimensionBuilder(FakeDb()).build_fallback_dimension_tables(
        profiles,
        existing_dimensions=[],
    )

    dimensions_by_source = {plan.source_table: plan for plan in plans}
    assert set(dimensions_by_source) == {"BusinessPartners", "Employees", "Products"}
    assert dimensions_by_source["BusinessPartners"].determinant_columns == ("PARTNERID",)
    assert dimensions_by_source["Employees"].determinant_columns == ("EMPLOYEEID",)
    assert dimensions_by_source["Products"].determinant_columns == ("PRODUCTID",)


def test_sales_order_items_become_fact_and_keep_external_reference_keys() -> None:
    profiles = {
        "SalesOrderItems": [
            make_profile("SalesOrderItems", "SALESORDERID", uniqueness_ratio=0.2),
            make_profile("SalesOrderItems", "SALESORDERITEM", uniqueness_ratio=0.02),
            make_profile("SalesOrderItems", "PRODUCTID", uniqueness_ratio=0.1),
            make_profile("SalesOrderItems", "QUANTITY", "Int64", uniqueness_ratio=0.05),
            make_profile("SalesOrderItems", "GROSSAMOUNT", "Float64", uniqueness_ratio=0.8),
            make_profile("SalesOrderItems", "NETAMOUNT", "Float64", uniqueness_ratio=0.8),
            make_profile("SalesOrderItems", "TAXAMOUNT", "Float64", uniqueness_ratio=0.7),
            make_profile("SalesOrderItems", "CURRENCY"),
            make_profile("SalesOrderItems", "DELIVERYDATE", "Date"),
        ]
    }

    plans = FactDimensionBuilder(FakeDb()).build_fact_tables(
        groups=[],
        profiles_by_table=profiles,
        dimension_plans=[],
    )

    assert len(plans) == 1
    assert plans[0].logical_table_role == FACT_CANDIDATE
    assert plans[0].columns == (
        "SALESORDERID",
        "SALESORDERITEM",
        "PRODUCTID",
        "QUANTITY",
        "GROSSAMOUNT",
        "NETAMOUNT",
        "TAXAMOUNT",
        "DELIVERYDATE",
    )


def legacy_product_texts_can_use_composite_dimension_key(monkeypatch) -> None:
    monkeypatch.setattr(
        "modeling.fact_dimension_builder.CompositeKeyEngine.find_minimal_composite_key",
        lambda database, table, columns, db: ("PRODUCTID", "LANGUAGE"),
    )
    profiles = {
        "ProductTexts": [
            make_profile("ProductTexts", "PRODUCTID", uniqueness_ratio=0.9),
            make_profile("ProductTexts", "LANGUAGE", uniqueness_ratio=0.05),
            make_profile("ProductTexts", "SHORT_DESCR", uniqueness_ratio=0.7),
            make_profile("ProductTexts", "LONG_DESCR", uniqueness_ratio=0.8),
        ]
    }

    plans = FactDimensionBuilder(FakeDb()).build_fallback_dimension_tables(
        profiles,
        existing_dimensions=[],
    )

    assert len(plans) == 1
    assert plans[0].determinant_columns == ("PRODUCTID", "LANGUAGE")
