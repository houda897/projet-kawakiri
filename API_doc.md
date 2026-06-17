# API Documentation: Mathematical & Statistical Engines

This section documents the core analytical functions of Kawakiri. These modules transform raw data into statistical indicators, allowing our pipeline to mathematically prove the validity of a decision model.

## Basic Profiling Engine (`basic_profile.py`)

These functions calculate the fundamental footprint of each column during data ingestion.

### `calculate_sparsity_ratio(column_data)`

Calculates the sparsity ratio to determine the completeness of an attribute.

- **Mathematical Formula** :

    $$S(C) = \frac{N_{null}}{N_{total}}$$

- **Proof of Exclusion** : If $S(C)=1.0$, the column is completely empty. If $S(C)>0.0$, the column is mathematically disqualified from being a simple Primary Key, as entity integrity cannot be guaranteed.

### `calculate_uniqueness_ratio(column_data)`

Evaluates the discriminative power of a column (or a tuple of columns) based on its non-null values. Let $\mathcal{D}(C)$ be the set of distinct values.

- **Mathematical Formula** :

    $$U(C) = \frac{|\mathcal{D}(C)|}{N_{total} - N_{null}}$$

- **Proof of Inference (Primary Keys)** : 

    The system proves the existence of a strict functional dependency (Primary Key) if and only if $U(C) ≥ \theta_{uni}$​ (where $\theta_{uni}$​ is our tolerance threshold, e.g., 0.95).

## Information Theory Engine (`identifiability.py`)

This module analyzes the distribution and diversity of information to semantically classify tables.

### `calculate_shannon_entropy(column_data, normalized=True)`

Calculates Shannon entropy to measure the uncertainty and diversity of values within a distribution.

- **Mathematical Formula** :
    Raw entropy is calculated via the probability of occurrence $P(x_i​)$ of each distinct value:

    $$H(C) = -\sum_{i=1}^{n} P(x_i) \log_2 P(x_i)$$

    To compare tables of different sizes, the API returns the normalized entropy (divided by the theoretical maximum entropy $log_2​(N)$):

    $$H_{norm}(C) = \frac{H(C)}{\log_2(N)}$$

- **Semantic Proof** : A categorical dimension (e.g., `Status = Active/Inactive`) will present an $H_{norm}$​ close to 0. 
A continuous measure (e.g., `Amount = 12.50, 19.99...`) or a technical identifier will have an $H_{norm}$​ close to 1. 
This is the mathematical pillar of the Role Separation test.

### `calculate_coefficient_of_variation(column_data)`

Measures the relative dispersion of numerical data around its mean, independently of its scale (euros, kilograms, etc.).

- **Mathematical Formula** :

    $$CV(C) = \frac{\sigma}{\mu}$$

    (Where $\sigma$ is the standard deviation and μ is the mean).

    Semantic Proof: If $H_{norm} ​≈ 1$ AND $CV ≫ 0$ (far more than 0), the API proves that the column is a **Fact Measure** (it varies greatly and unpredictably). If $CV ≈ 0$, it is a constant or a technical attribute (Dimension).

### `calculate_skewness(column_data)`

Calculates Fisher's skewness coefficient to identify imbalances in the data distribution.

- **Mathematical Formula** :

    $$\gamma_1 = \frac{E[(X - \mu)^3]}{\sigma^3}$$

- **Anomaly Detection Proof** : An incremental primary key has a uniform distribution ($\gamma_1 ​≈ 0$). Extreme skewness ($\gamma_1 ​≫ 1$) proves an abnormal distribution, often signaling a column heavily populated with default values (e.g., `9999`) or data entry errors.

## Join Inference Engine (join_candidate.py)

### `calculate_join_success_ratio(source_col, target_col)`

Determines the viability of a $Foreign Key → Primary Key$ relationship by calculating the set inclusion rate.

- **Mathematical Formula** :
    Let $T_s$​ be the source table and $T_t$​ be the target table (with primary key $K_t$​).

    $$JSR(C_s \rightarrow K_t) = \frac{|\pi_{C_s}(T_s) \cap \pi_{K_t}(T_t)|}{|\pi_{C_s}(T_s)|}$$

- **Proof of Relationship** : The API proves the existence of a relationship (an edge in the graph) if the $JSR$ crosses the probabilistic threshold $\theta_{jsr}$​ (e.g., 0.95). This calculation mathematically validates the **Referential Integrity** of the candidate model.

## Aggregation Validation Engine (`aggregation_stability_validator.py`)

This is the most critical function of the API. It proves the absence of unintended Cartesian products (Fan-Out).

### `validate_aggregation_stability(fact_table, dim_table, measure_col)`

Verifies the law of conservation of measures during a Roll-Up operation across an inferred dimension.

- **Mathematical Formula** :
    The API calculates the sum at the finest grain $\Sigma_{fine}$ ​:

    $$\Sigma_{fine} = \sum_{i \in F} M_i$$

    Then, it simulates the aggregation via the inferred join ($\Sigma_{agg}$​) :

    $$\Sigma_{agg} = \sum_{g \in \pi_A(D)} \left( \sum_{k \in \{F \bowtie D\}_{A=g}} M_k \right)$$


    The Delta is evaluated against a machine tolerance $\epsilon$ (to account for Float64 arithmetic approximations) :

    $$\Delta = |\Sigma_{fine} - \Sigma_{agg}|$$

- **Proof of Stability** : The model is certified if and only if $\Delta ≤ \epsilon$. If $\Delta > \epsilon$, the API mathematically proves that the join granularity is incorrect (resulting in duplicated rows) and strictly rejects the relationship.