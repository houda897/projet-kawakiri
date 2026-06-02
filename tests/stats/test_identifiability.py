import pytest
from unittest.mock import MagicMock, call
from stats.identifiability import IdentifiabilityEngine, IdentifiabilityResult 

@pytest.fixture
def mock_db():
    return MagicMock()

@pytest.fixture
def engine(mock_db):
    return IdentifiabilityEngine(
        db=mock_db,
        weight_uniqueness=0.5,
        weight_entropy=0.3,
        weight_completeness=0.2,
        threshold_high=0.8,
        threshold_medium=0.5,
        threshold_low=0.2
    )

def test_validate_weights_success(mock_db):
    '''Test that the engine initializes correctly when weights sum to 1.'''
    IdentifiabilityEngine(mock_db, 0.4, 0.4, 0.2)

def test_validate_weights_failure(mock_db):
    '''Test that the engine raises a ValueError when weights do not sum to 1.'''
    with pytest.raises(ValueError, match="Identifiability weights must sum to 1"):
        IdentifiabilityEngine(mock_db, 0.5, 0.5, 0.5)

def test_diagnose(engine):
    '''Test that the diagnose method returns the correct labels based on the thresholds.'''
    assert engine.diagnose(0.9) == "HIGH_IDENTIFIABILITY"
    assert engine.diagnose(0.8) == "HIGH_IDENTIFIABILITY"
    assert engine.diagnose(0.6) == "MEDIUM_IDENTIFIABILITY"
    assert engine.diagnose(0.3) == "LOW_IDENTIFIABILITY"
    assert engine.diagnose(0.1) == "VERY_LOW_IDENTIFIABILITY"

def test_compute_scores(engine, mock_db):
    '''Test that compute_scores correctly calculates the identifiability score and diagnoses based on mocked DB results.'''
    
    mock_result = MagicMock()
    mock_result.result_rows = [
        ("TestDB", "TableA", "Col1", 1000, 500, 0.8, 0.1), # Uniqueness = 0.5, Completeness = 0.9
        ("TestDB", "TableA", "ColEmpty", 0, 0, 0.0, 1.0)   # Test division par zéro
    ]
    mock_db.query.return_value = mock_result
    
    results = engine.compute_scores()
    
    assert len(results) == 2
    
    res1 = results[0]
    assert res1.column_name == "Col1"
    assert res1.uniqueness_ratio == 0.5
    assert res1.completeness == 0.9
    assert round(res1.identifiability_score, 2) == 0.67
    assert res1.diagnostic == "MEDIUM_IDENTIFIABILITY"
    
    res2 = results[1]
    assert res2.column_name == "ColEmpty"
    assert res2.uniqueness_ratio == 0.0

def test_store_scores(engine, mock_db):
    '''Test that store_scores correctly prepares data for DB insertion.'''
    dummy_results = [
        IdentifiabilityResult("TestDB", "TableA", "Col1", 1.0, 1.0, 1.0, 1.0, "HIGH_IDENTIFIABILITY")
    ]
    
    engine.store_scores(dummy_results)
    
    mock_db.insert.assert_called_once()
    
    args, kwargs = mock_db.insert.call_args
    table_name = args[0]
    rows_data = args[1]
    
    assert "identifiability_scores" in table_name
    assert len(rows_data) == 1
    assert rows_data[0] == ["TestDB", "TableA", "Col1", 1.0, 1.0, 1.0, 1.0, "HIGH_IDENTIFIABILITY"]
    assert "column_names" in kwargs

def test_store_scores_empty(engine, mock_db):
    '''Test that store_scores does not attempt to insert if the results list is empty.'''
    engine.store_scores([])
    mock_db.insert.assert_not_called()