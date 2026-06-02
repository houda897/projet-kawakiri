from config.scoring import PARSIMONY_WEIGHTS
from modeling.decision_model import DecisionModelCandidate, DecisionModelType

def score_candidate(candidate: DecisionModelCandidate) -> float:
    """
    Compute a parsimony score for a single decision model candidate.

    Uses metrics pre-computed by DecisionModelCandidateBuilder — no SQL query needed.
    Constellation candidates receive additional bonuses for fact coverage
    and shared dimensions. Higher score is better.
    """
    score = (
        candidate.table_count            * PARSIMONY_WEIGHTS["table_penalty"]     +
        candidate.attribute_count        * PARSIMONY_WEIGHTS["attribute_penalty"]  +
        candidate.numeric_attribute_count * PARSIMONY_WEIGHTS["numeric_reward"]    +
        len(candidate.dimension_tables)  * PARSIMONY_WEIGHTS["dimension_reward"]
    )

    if candidate.model_type == DecisionModelType.CONSTELLATION:
        num_facts = len(candidate.fact_tables)
        num_dims  = len(candidate.dimension_tables)
        score += (num_facts - 1) * PARSIMONY_WEIGHTS["fact_coverage_bonus"]
        score += num_dims * (num_facts - 1) * PARSIMONY_WEIGHTS["shared_dimension_bonus"]

    return round(score, 4)

def rank_models_by_parsimony(
    candidates: list[DecisionModelCandidate],
) -> list[tuple[float, DecisionModelCandidate]]:
    """
    Rank decision model candidates by parsimony score, highest first.

    DecisionModelCandidate is a frozen dataclass — scores cannot be attached
    to the objects directly. Returns (score, candidate) pairs instead so the
    caller can access both without modifying the dataclass.

    Args:
        candidates: Candidates produced by DecisionModelCandidateBuilder.

    Returns:
        List of (score, candidate) sorted by descending score.
    """
    scored = [
        (score_candidate(candidate), candidate)
        for candidate in candidates
    ]
    return sorted(scored, key=lambda x: x[0], reverse=True)