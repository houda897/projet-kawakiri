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

# Weights used to compute the confidence score of a primary-key candidate.
# confidence = PK_WEIGHTS["uniqueness"] * uniqueness_ratio
#            + PK_WEIGHTS["identifiability"] * identifiability_score
PK_WEIGHTS = {
    "uniqueness": 0.7,
    "identifiability": 0.3,
}
