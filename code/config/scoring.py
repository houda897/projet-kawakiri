IDENTIFIABILITY_WEIGHTS = {
    "uniqueness": 0.5,
    "entropy": 0.3,
    "completeness": 0.2,
}

IDENTIFIABILITY_THRESHOLDS = {
    "high": 0.85,
    "medium": 0.5,
    "low": 0.2,
}

PK_WEIGHTS = {
    "uniqueness": 0.7,
    "identifiability": 0.3,
}

SEMANTIC_THRESHOLDS = {
    "confirmed": 0.75,
    "coincidence": 0.25,
}

SEMANTIC_WEIGHTS = {
    "join_success_ratio": 0.34,
    "semantic_similarity": 0.66,
}

EVALUATE_CANDIDATES = {
    "COMPOSITE_KEY_COLUMN_RESTRICTION" : 5,
    "Filter_margin" : 1.1
    # Calculation for margin -> 1.1 = tolerate 10% more than the pk
}