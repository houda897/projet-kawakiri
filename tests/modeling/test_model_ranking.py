import unittest
from unittest.mock import MagicMock, patch

from modeling.decision_model import DecisionModelType
from modeling.model_ranking import ModelRanking


class DummyCandidate:
    """A mock object to simulate a DecisionModelCandidate"""

    def __init__(self, model_id, m_type, facts, dims, tables, attrs, num_attrs):
        self.model_id = model_id
        self.model_type = m_type
        self.fact_tables = facts
        self.dimension_tables = dims
        self.table_count = tables
        self.attribute_count = attrs
        self.numeric_attribute_count = num_attrs


class TestModelRanking(unittest.TestCase):
    def setUp(self):
        self.mock_db = MagicMock()
        self.ranking_engine = ModelRanking(self.mock_db)

    @patch(
        "modeling.model_ranking.PARSIMONY_WEIGHTS",
        {
            "table_penalty": -1.0,
            "attribute_penalty": -0.1,
            "numeric_reward": 2.0,
            "dimension_reward": 5.0,
            "fact_coverage_bonus": 10.0,
            "shared_dimension_bonus": 2.0,
        },
    )
    def test_calculate_score_star_schema(self):
        """Test the score for a simple star pattern"""
        candidate = DummyCandidate(
            "star_1", DecisionModelType.STAR, ["fact_A"], ["dim_1", "dim_2"], 3, 10, 4
        )

        score = self.ranking_engine._calculate_score(candidate)  # type: ignore
        self.assertEqual(score, 14.0)

    @patch(
        "modeling.model_ranking.PARSIMONY_WEIGHTS",
        {
            "table_penalty": -1.0,
            "attribute_penalty": -0.1,
            "numeric_reward": 2.0,
            "dimension_reward": 5.0,
            "fact_coverage_bonus": 10.0,
            "shared_dimension_bonus": 2.0,
        },
    )
    def test_calculate_score_constellation(self):
        """Test the score with the bonuses of a constellation model"""
        candidate = DummyCandidate(
            "const_1",
            DecisionModelType.CONSTELLATION,
            ["fact_A", "fact_B"],
            ["dim_1", "dim_2"],
            4,
            20,
            5,
        )

        score = self.ranking_engine._calculate_score(candidate)  # type: ignore
        self.assertEqual(score, 28.0)

    @patch("modeling.model_ranking.clear_metadata_table")
    def test_rank_and_store(self, mock_clear):
        """Test that the function correctly sorts the candidates and calls the database insertion"""
        cand1 = DummyCandidate("model_1", DecisionModelType.STAR, ["F1"], ["D1"], 2, 5, 1)
        cand2 = DummyCandidate(
            "model_2", DecisionModelType.STAR, ["F1"], ["D1", "D2", "D3"], 4, 5, 5
        )

        ranked = self.ranking_engine.rank_and_store([cand1, cand2])  # type: ignore

        self.assertEqual(len(ranked), 2)
        self.assertEqual(ranked[0][0].model_id, "model_2")
        self.assertEqual(ranked[0][1], 1.0)
        self.assertEqual(ranked[1][1], 0.0)
        self.assertTrue(self.mock_db.insert.called)
        self.mock_db.insert.assert_called_once()
        assert self.mock_db.insert.call_args.kwargs["column_names"] == [
            "database_name",
            "model_id",
            "parsimony_score",
            "normalized_score",
        ]
        mock_clear.assert_called()
