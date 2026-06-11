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
    "COMPOSITE_KEY_COLUMN_RESTRICTION": 3,
    "Filter_margin": 1.1,
    "JOIN_SAMPLE_ROWS": 100000,
    # Calculation for margin -> 1.1 = tolerate 10% more than the pk
}

INGESTION_SETTINGS = {
    # Keep CSV ingestion robust by default: temporal values stay as String unless
    # this option is enabled for datasets with stable date/date-time formats.
    "INFER_TEMPORAL_TYPES": False,
}

PARSIMONY_WEIGHTS = {
    # Complexity penalties
    "table_penalty": -1.0,  # Penalty per table in the model
    "attribute_penalty": -0.05,  # Penalty for each column to discourage monster tables
    # Reward for numeric attribute
    "numeric_reward": 2.0,  # Reward for numeric attribute in facts tables
    "dimension_reward": 8.0,  # Reward for each connected dimension tables
    # Bonus for galaxy schema
    "fact_coverage_bonus": 15.0,  # Reward if the model unify multple fact tables
    "shared_dimension_bonus": 10.0,  # Reward for shared dimension between multiples fact tables
}

SEMANTIC_HOMOGENEITY_WEIGHTS = {
    "threshold": 0.85,
    "entropy_weight": 0.4,
    "variation_coef_weight": 0.3,
    "skewness_weight": 0.3,
}
