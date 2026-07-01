# Scoring System and Weights (Kawakiri)

This document details the algorithmic and business logic behind the weights and thresholds defined in the `scoring.py` file. Kawakiri uses a multi-criteria weighting system to evaluate columns, classify tables, and designate the optimal decision model.

## Identifiability and Key Detection (`IDENTIFIABILITY_WEIGHTS`)

The goal of this score is to determine whether a column possesses the statistical DNA of an identifier (Primary Key).

* **Uniqueness (0.5):** This is the king criterion. A primary key must guarantee entity uniqueness. This majority weight ensures that a column without duplicates always outranks the others.
* **Entropy (0.3):** Normalized Shannon entropy. It differentiates an incremental technical column (high entropy) from a highly dispersed status column that is not a key.
* **Completeness (0.2):** Rewards columns with a low `null_ratio`. Since a primary key cannot be null, this bonus breaks ties for candidates with good uniqueness but missing data.

> **Tolerance Thresholds (`IDENTIFIABILITY_THRESHOLDS`):** > An overall score > 0.85 is considered `high` (strong PK candidate). Below 0.5, the column is rejected for this role.

## Semantic Homogeneity (`SEMANTIC_HOMOGENEITY_WEIGHTS`)

This score is used by the "Iron Rules" to ensure that a Dimension table does not contain pure quantitative metrics, and vice versa.

* **Entropy Weight (0.4):** Entropy is the best indicator of diversity. A dimension should have moderate entropy (repeating categories).
* **Variation Coefficient (0.3):** Measures relative dispersion (Standard Deviation / Mean). High dispersion is characteristic of a Measure (Fact), not a Dimension attribute.
* **Skewness Weight (0.3):** Fisher's skewness penalizes columns with highly abnormal distributions (e.g., heavily skewed by default values like `9999`).

> **Alert Threshold:** A combined score exceeding **0.85** triggers a homogeneity violation (e.g., suspected presence of a Measure in a Dimension).

## Parsimony Score (`PARSIMONY_WEIGHTS`)

This is the heart of the candidate model evaluation system. It draws inspiration from Occam's Razor: all else being equal in explanatory power, the simplest model is always the best.

### Penalties (Complexity)
* **Table Penalty (-1.0):** Penalizes the addition of unnecessary intermediate tables (excessive snowflaking). It pushes the algorithm towards clean, simple star schemas.
* **Attribute Penalty (-0.05):** A very slight penalty per column to discourage the selection of denormalized "monster" (catch-all) tables and to encourage the separation of concepts.

### Rewards (Analytical Richness)
* **Numeric Reward (+2.0):** Each additive measure found in a fact table increases the score, as it represents the primary added value for Business Intelligence queries.
* **Dimension Reward (+8.0):** Connecting a validated dimension yields significant points, as it multiplies the available axes of analysis (Roll-up / Drill-down).
* **Fact Coverage Bonus (+15.0):** A massive bonus if the model successfully unifies several coherent fact tables.
* **Shared Dimension Bonus (+10.0):** Rewards the discovery of a "Galaxy Schema" (Constellation), where the same dimension (e.g., Time or Customers) is shared by multiple fact tables, enabling cross-process querying.

## Semantic Join Inference (`SEMANTIC_WEIGHTS`)

When a `Foreign Key -> Primary Key` relationship is evaluated, Kawakiri does not rely solely on raw mathematical data.

* **Semantic Similarity (0.66):** The algorithm gives overriding weight to the semantic match of column names (e.g., `customer_id` linked to `id` in the `customers` table). This prevents statistical "false joins" between entirely unrelated numeric identifiers.
* **Join Success Ratio (0.34):** The set inclusion rate confirms that the data actually intersects. It acts as a mathematical safety net against homonyms.

## Final Certification (`CERTIFICATION_SCORE_WEIGHTS`)

Each candidate model starts with a baseline confidence score of **100.0**. This score is then reduced by the structural validators (the Iron Rules).

* **Warning Penalty (-10.0):** Deducted for non-blocking anomalies (e.g., a dimension table lacking clear textual attributes). The model remains certifiable.
* **Error Penalty (-35.0):** A heavy penalty applied when a strict rule fails. Accumulating errors quickly disqualifies the model (the score can drop to a minimum of **0.0**).