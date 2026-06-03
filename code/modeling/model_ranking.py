from core.clickhouse_manager import CH_DB, META_DB, clickhouse_manager
from core.logger import get_logger
from core.meta import clear_metadata_table
from modeling.decision_model import DecisionModelCandidate, DecisionModelType
from config.scoring import PARSIMONY_WEIGHTS

logger = get_logger(__name__)

class ModelRanking:
    '''
    Evaluates decision model candidates based on a parsimony scoring system and stores the scores in a dedicated metadata table.
    The scoring system rewards models that are simpler (fewer tables and attributes) while also considering the richness of the data (numeric attributes, dimensions) and the structure (constellation schemas).
    '''

    def __init__(self, db: clickhouse_manager):
        self.db = db

    def _calculate_score(self, candidate: DecisionModelCandidate) -> float:
        '''Calculate a parsimony score for a given candidate based on its characteristics and the defined weights.'''
        score = (
            (candidate.table_count * PARSIMONY_WEIGHTS.get("table_penalty", -1.0)) +
            (candidate.attribute_count * PARSIMONY_WEIGHTS.get("attribute_penalty", -0.05)) +
            (candidate.numeric_attribute_count * PARSIMONY_WEIGHTS.get("numeric_reward", 2.0))
        )
        
        score += len(candidate.dimension_tables) * PARSIMONY_WEIGHTS.get("dimension_reward", 8.0)
        
        if candidate.model_type == DecisionModelType.CONSTELLATION and len(candidate.fact_tables) > 1:
            num_facts = len(candidate.fact_tables)
            num_dims = len(candidate.dimension_tables)
            
            score += (num_facts - 1) * PARSIMONY_WEIGHTS.get("fact_coverage_bonus", 15.0)
            score += num_dims * (num_facts - 1) * PARSIMONY_WEIGHTS.get("shared_dimension_bonus", 10.0)
            
        return round(score, 2)

    def rank_and_store(self, candidates: list[DecisionModelCandidate]) -> list[tuple[DecisionModelCandidate, float]]:
        '''
        Calculate scores for each candidate, store them in the metadata table, and return a sorted list of (candidate, score) tuples.
        '''
        if not candidates:
            logger.warning("Aucun candidat fourni pour le ranking.")
            return []

        scored_data = []
        for candidate in candidates:
            score = self._calculate_score(candidate)
            scored_data.append((candidate, score))
            
        scored_data.sort(key=lambda x: x[1], reverse=True)
        
        self._store_scores([
            (candidate.model_id, score) for candidate, score in scored_data
        ])
        
        logger.info("Évaluation et sauvegarde terminées pour %d modèles.", len(scored_data))
        return scored_data

    def _store_scores(self, scores_data: list[tuple[str, float]]) -> None:
        '''Store the parsimony scores in a dedicated metadata table'''
        clear_metadata_table(self.db, "decision_model_scores")
        
        rows = [
            [CH_DB, model_id, score]
            for model_id, score in scores_data
        ]

        self.db.insert(
            f"{META_DB}.decision_model_scores",
            rows,
            column_names=["database_name", "model_id", "parsimony_score"]
        )

    @staticmethod
    def print_ranked_models(scored_candidates: list[tuple[DecisionModelCandidate, float]]) -> None:
        '''Print the ranked models with their scores and key characteristics'''
        logger.info("=== MODELS RANKING ===")
        for i, (candidate, score) in enumerate(scored_candidates, 1):
            logger.info(
                "Rang %d | Score: %s | Type: %s | ID: %s",
                i, score, candidate.model_type.value, candidate.model_id
            )