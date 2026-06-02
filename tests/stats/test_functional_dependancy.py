import pytest
from unittest.mock import MagicMock, patch
from inference.primary_key import PrimaryKeyCandidate
from stats.functional_dependency import check_functional_dependency, validate_dependency 

@pytest.fixture
def mock_db():
    return MagicMock()

def test_check_functional_dependency_single_column_valid(mock_db):
    '''Test that the function correctly identifies a valid functional dependency for a single column.'''
    mock_result = MagicMock()
    mock_result.result_rows = []
    mock_db.query.return_value = mock_result
    
    is_valid = check_functional_dependency("TestDB", "TableA", "CustomerID", mock_db)
    
    assert is_valid is True
    query_called = mock_db.query.call_args[0][0]
    assert "`CustomerID`" in query_called

def test_check_functional_dependency_composite_column_invalid(mock_db):
    '''Test with a composite key that is invalid (duplicates exist).'''
    mock_result = MagicMock()
    mock_result.result_rows = [(2, 123456789)]
    mock_db.query.return_value = mock_result
    
    is_valid = check_functional_dependency("TestDB", "TableA", ["OrderID", "ProductID"], mock_db)
    
    assert is_valid is False
    query_called = mock_db.query.call_args[0][0]
    assert "`OrderID`, `ProductID`" in query_called

@patch("stats.functional_dependency.clickhouse_manager")
@patch("stats.functional_dependency.check_functional_dependency")
def test_validate_dependency(mock_check_fd, mock_db_manager):
    '''Test that the function correctly filters valid and invalid candidates.'''
    
    candidate_valid = PrimaryKeyCandidate(
        database_name="TestDB", table_name="TableA", column_name="ValidKey",
        column_type="Int32", rows=10, null_ratio=0.0, uniqueness_ratio=1.0,
        identifiability_score=1.0, confidence=1.0, reason=""
    )
    candidate_invalid = PrimaryKeyCandidate(
        database_name="TestDB", table_name="TableA", column_name="InvalidKey",
        column_type="Int32", rows=10, null_ratio=0.0, uniqueness_ratio=0.5,
        identifiability_score=0.5, confidence=0.5, reason=""
    )
    
    candidates_list = [candidate_valid, candidate_invalid]
    
    def side_effect_fd(db, table, col, manager):
        return col == "ValidKey"
        
    mock_check_fd.side_effect = side_effect_fd
    
    filtered_list = validate_dependency(candidates_list)
    
    assert len(filtered_list) == 1
    assert filtered_list[0].column_name == "ValidKey"
    
    assert len(candidates_list) == 2