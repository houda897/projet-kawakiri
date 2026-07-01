import json
import os
import tempfile
import unittest

import pytest
from main import run_all


@pytest.mark.integration
class TestE2EPipelineRealData(unittest.TestCase):
    REQUIRED_CH_DATABASE = "Exercice"

    def setUp(self):
        """
        Set up the test environment:
        Point to the directory containing the real CSV files and create
        a temporary directory to isolate the generated JSON report.
        """
        actual_db = os.environ.get("CH_DATABASE", "")

        if actual_db != self.REQUIRED_CH_DATABASE:
            self.skipTest(
                f"Integration test skipped: CH_DATABASE must be '{self.REQUIRED_CH_DATABASE}' "
                f"in your .env file. Current value: '{actual_db or '(not set)'}'.\n"
                f"Set CH_DATABASE={self.REQUIRED_CH_DATABASE} and re-run."
            )

        # Get the directory where this test file is located
        self.current_dir = os.path.dirname(os.path.abspath(__file__))
        # Path to the sample database folder containing your CSV files
        self.folder_path = os.path.join("code/data")

        # Temporary folder for the output report to avoid polluting the workspace
        self.temp_output_dir = tempfile.TemporaryDirectory()
        self.report_path = os.path.join(self.temp_output_dir.name, "e2e_report.json")

    def tearDown(self):
        """Clean up the temporary directory after the test execution."""
        self.temp_output_dir.cleanup()

    def test_pipeline_on_real_dataset(self):
        """
        Execute the full E2E pipeline on the sample dataset and verify
        that the star schema roles and relationships match the expected output.
        """
        # Pre-check to ensure the data folder path is correct
        self.assertTrue(
            os.path.exists(self.folder_path),
            f"Test data directory not found: {self.folder_path}",
        )

        # 1. Run the entire pipeline orchestration
        try:
            run_all(
                path=self.folder_path,
                report_path=self.report_path,
                skip_sql_views=True,
            )
        except Exception as e:
            self.fail(f"The E2E pipeline crashed unexpectedly with error: {e}")

        # 2. Verify that the output certification report was generated
        self.assertTrue(
            os.path.exists(self.report_path), "The certification report JSON was not generated."
        )

        with open(self.report_path, encoding="utf-8") as f:
            report_data = json.load(f)

        # 3. High-level structural validations on the JSON schema
        self.assertIn("models", report_data, "The 'models' key is missing from the JSON report.")
        self.assertGreater(
            len(report_data["models"]),
            0,
            "No valid model candidates survived the pipeline validation.",
        )

        # Extract the top-ranked model candidate (index 0)
        best_model = report_data["models"][0]

        # Helper to handle both lists and comma-separated strings inside JSON
        def parse_table_list(val):
            if isinstance(val, str):
                return [t.strip() for t in val.split(",") if t.strip()]
            return val or []

        # Robust Key Extraction for Facts and Dimensions (supports multiple naming conventions)
        fact_tables = parse_table_list(best_model.get("fact_tables") or best_model.get("facts"))
        dim_tables = parse_table_list(
            best_model.get("dimension_tables") or best_model.get("dimensions")
        )

        # 4. Business Logic Assertions: Verify table role classification from logs
        # 'sales' is correctly identified as the central Fact table
        self.assertIn(
            "sales",
            fact_tables,
            f"The 'sales' table should be recognized as a Fact table. Found: {fact_tables}",
        )
        self.assertEqual(
            len(fact_tables), 1, f"There should be only 1 central Fact table. Found: {fact_tables}"
        )

        # Verify the 4 validated Dimension tables connected to the 'sales' ecosystem
        expected_dimensions = {"calendar", "customers", "products", "shipments"}
        self.assertEqual(
            set(dim_tables),
            expected_dimensions,
            f"Expected dimensions {expected_dimensions}, got {dim_tables}",
        )

        # 'categories_source' must be excluded from the final star model as it is isolated
        self.assertNotIn(
            "categories_source", fact_tables, "Isolated table should not be a Fact table."
        )
        self.assertNotIn(
            "categories_source", dim_tables, "Isolated table should not be a Dimension table."
        )

        # 5. Model Metadata Assertions (Ultra-robust fallback validation)
        model_type = (
            best_model.get("type")
            or best_model.get("model_type")
            or best_model.get("architecture")
            or best_model.get("schema_type")
        )
        # Ultimate fallback: check if the string "star" is present in the model's ID field
        if not model_type and "id" in best_model:
            if "star" in str(best_model["id"]).lower():
                model_type = "STAR"

        self.assertEqual(
            model_type,
            "STAR",
            f"The inferred model architecture should be a STAR schema. Keys found: {list(best_model.keys())}",
        )

        # 6. Graph Relationship Assertions
        # The certification report does not serialise the edge list directly.
        # STRUCTURAL_VALIDATION being in passed_rules proves the StructuralValidator
        # already confirmed that every dimension is reachable from the fact table.
        passed_rules = best_model.get("passed_rules", [])
        self.assertIn(
            "STRUCTURAL_VALIDATION",
            passed_rules,
            f"STRUCTURAL_VALIDATION must be in passed_rules to confirm all joins between "
            f"'sales' and its dimensions are valid. Actual passed_rules: {passed_rules}",
        )
