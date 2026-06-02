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
    "Filter_margin" : 1.1,
    "JOIN_SAMPLE_ROWS": 100000,
    # Calculation for margin -> 1.1 = tolerate 10% more than the pk
}

PARSIMONY_WEIGHTS = {
    # --- Pénalités de complexité physique (allégées) ---
    "table_penalty": -1.0,           # Pénalité par table globale dans le modèle
    "attribute_penalty": -0.05,      # Pénalité très légère par colonne pour éviter les tables monstres
    
    # --- Récompenses de richesse de données ---
    "numeric_reward": 2.0,           # Récompense pour chaque indicateur numérique (les faits)
    "dimension_reward": 8.0,         # 🚀 BONUS : Points accordés pour chaque table de Dimension connectée
    
    # --- Bonus spécifiques à la Constellation (Galaxy Schema) ---
    "fact_coverage_bonus": 15.0,     # 🚀 BONUS : Gros points si le modèle unifie plusieurs faits (ex: Sales 2020 + 2021 + 2022)
    "shared_dimension_bonus": 10.0   # 🚀 BONUS : Points par dimension conformes (partagée entre plusieurs faits)
}
