from unittest.mock import MagicMock, patch

import pytest
from inference.composite_key import CompositeKeyEngine  # Ajuste l'import
from inference.key_ranking import RankedKeyCandidate
from inference.primary_key import PrimaryKeyCandidate


@pytest.fixture
def mock_db():
    return MagicMock()


@pytest.fixture
def composite_engine(mock_db):
    return CompositeKeyEngine(db=mock_db)


@pytest.fixture
def dummy_columns():
    """Generate a fake list of columns returned by ClickHouse for composite key search."""
    return [
        PrimaryKeyCandidate(
            database_name="TestDB",
            table_name="FactSales",
            column_name="OrderNumber",
            column_type="String",
            rows=1000,
            null_ratio=0.0,
            uniqueness_ratio=0.5,
            identifiability_score=0.8,
            confidence=0.9,
            reason="test",
        ),
        PrimaryKeyCandidate(
            database_name="TestDB",
            table_name="FactSales",
            column_name="ProductKey",
            column_type="Int32",
            rows=1000,
            null_ratio=0.0,
            uniqueness_ratio=0.1,
            identifiability_score=0.9,
            confidence=0.8,
            reason="test",
        ),
        PrimaryKeyCandidate(
            database_name="TestDB",
            table_name="FactSales",
            column_name="OrderDate",
            column_type="Date",
            rows=1000,
            null_ratio=0.0,
            uniqueness_ratio=0.05,
            identifiability_score=0.4,
            confidence=0.4,
            reason="test",
        ),
    ]


@patch("inference.composite_key.check_functional_dependency")
def test_generate_composite_candidates_success(mock_check_fd, composite_engine, dummy_columns):
    """
    Simulate the discovery of a composite key and the pruning process.
    We test that the engine removes the OrderDate column if it's not needed.
    """
    composite_engine.load_columns_for_composite_search = MagicMock(return_value=dummy_columns)

    def side_effect_fd(db_name, table_name, cols, db):
        if set(cols) == {"OrderNumber", "ProductKey"}:
            return True
        if set(cols) == {"OrderNumber", "ProductKey", "OrderDate"}:
            return True
        return False

    mock_check_fd.side_effect = side_effect_fd

    tables_without_pk = ["FactSales"]
    low_card_cols = set()

    candidates = composite_engine.generate_composite_candidates(tables_without_pk, low_card_cols)

    assert len(candidates) == 1
    assert isinstance(candidates[0], RankedKeyCandidate)

    assert set(candidates[0].column_names) == {"OrderNumber", "ProductKey"}
    assert candidates[0].table_name == "FactSales"


def test_generate_composite_candidates_no_columns(composite_engine):
    """'Test the behavior if a table has fewer than 2 candidate columns (composite key impossible)."""
    composite_engine.load_columns_for_composite_search = MagicMock(
        return_value=[
            PrimaryKeyCandidate(
                database_name="TestDB",
                table_name="TinyTable",
                column_name="OnlyCol",
                column_type="String",
                rows=10,
                null_ratio=0.0,
                uniqueness_ratio=1.0,
                identifiability_score=1.0,
                confidence=1.0,
                reason="",
            )
        ]
    )

    candidates = composite_engine.generate_composite_candidates(["TinyTable"], set())
    assert len(candidates) == 0


def test_load_columns_for_composite_search(composite_engine, mock_db):
    """Test the parsing of the SQL result returned by ClickHouse."""

    mock_result = MagicMock()
    mock_result.result_rows = [
        ("TestDB", "Table1", "ColA", "Int32", 100, 0.0, 0.5, 0.8),
        ("TestDB", "Table1", "ColB", "String", 100, 0.0, 0.9, 0.2),
    ]
    mock_db.query.return_value = mock_result

    with patch.dict("config.scoring.PK_WEIGHTS", {"uniqueness": 0.5, "identifiability": 0.5}):
        columns = composite_engine.load_columns_for_composite_search()

        assert len(columns) == 2
        assert columns[0].table_name == "Table1"
        assert columns[0].column_name == "ColA"
        assert columns[0].confidence == 0.65
