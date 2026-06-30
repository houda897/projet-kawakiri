# API Reference: Mathematical & Statistical Engines

This document covers the analytical core of **Kawakiri**. The modules below
transform raw tabular data into statistical indicators that allow the pipeline
to construct, rank, and certify dimensional models [@kimball2013] in a fully
deterministic way.

Functions are presented in pipeline execution order:

```
1.  Ingestion & Basic Profiling       →  basic_profile.py
2.  Identifiability Scoring           →  identifiability.py
3.  Composite Identifier Score        →  identifiability.py
4.  Primary Key Inference             →  pk_inference.py
5.  Join Inference                    →  join_candidate.py
6.  Graph Construction                →  adjacency.py
7.  Role Inference                    →  role_inference.py
8.  Candidate Model Construction      →  candidate_builder.py
9.  Ranking                           →  ranking.py
10. Validation (4 rules)              →  *_validator.py
11. Certification                     →  certification.py
12. SQL View & JSON Report Export     →  sql_generator.py / certification_report.py
```

---

## 1. Basic Profiling (`basic_profile.py`)

These functions compute the fundamental statistical footprint of each column
during the ingestion phase [@abedjan2015].

---

### `calculate_sparsity_ratio(column_data)`

Computes the sparsity ratio to assess the completeness of an attribute
[@abedjan2015].

**Formula:**

$$S(C) = \frac{N_{\text{null}}}{N_{\text{total}}}$$

**Interpretation:**

- $S(C) = 1.0$: the column is entirely empty and is excluded from all
  further analysis.
- $S(C) > 0.0$: the column is disqualified as a simple primary key, since
  entity integrity cannot be guaranteed.

---

### `calculate_uniqueness_ratio(column_data)`

Evaluates the discriminating power of a column (or column tuple) over its
non-null values [@abedjan2015]. Let $\mathcal{D}(C)$ be the set of distinct
values.

**Formula:**

$$U(C) = \frac{|\mathcal{D}(C)|}{N_{\text{total}} - N_{\text{null}}}$$

**Interpretation:**

The pipeline validates the existence of a strict functional dependency (primary
key) if and only if $U(C) \geq \theta_{\text{uni}}$ (configurable threshold,
default: $0.95$).

---

## 2. Identifiability Scoring (`identifiability.py`)

This module analyses the distribution and information diversity of each column
to semantically classify tables [@abedjan2015].

---

### `calculate_shannon_entropy(column_data, normalized=True)`

Computes Shannon entropy to measure uncertainty and value diversity within a
distribution [@shannon1948].

**Formula — raw entropy:**

$$H(C) = -\sum_{i=1}^{n} P(x_i) \log_2 P(x_i)$$

where $P(x_i)$ is the probability of occurrence of value $x_i$ [@shannon1948].

**Formula — normalised entropy** (returned by default, `normalized=True`):

$$H_{\text{norm}}(C) = \frac{H(C)}{\log_2(N)}$$

Normalising by $\log_2(N)$ (the theoretical maximum entropy) enables
comparison across tables of different sizes on a $[0, 1]$ scale.

> **Note:** This normalisation is intentionally stricter than the conventional
> $\log_2(n)$ normalisation (where $n$ is the number of distinct values). It
> approaches $1$ only when almost every value is unique ($n \approx N$),
> precisely targeting identifier-like columns.

**Interpretation:**

- $H_{\text{norm}} \approx 0$: low-diversity categorical column
  (e.g. `status = Active/Inactive`) → Dimension signal.
- $H_{\text{norm}} \approx 1$: continuous or identifier-like column
  (e.g. `amount = 12.50, 19.99…`) → Fact or primary key signal.

This is the foundation of the **Semantic Role Separation** test [@kimball2013].

---

### `calculate_coefficient_of_variation(column_data)`

Measures the relative dispersion of numeric data around their mean,
independently of the unit of measurement [@abedjan2015].

**Formula:**

$$CV(C) = \frac{\sigma}{\mu}$$

where $\sigma$ is the standard deviation and $\mu$ the mean.

> **Edge case:** undefined when $\mu = 0$. The column is excluded from
> variability scoring in this case.

**Interpretation:**

- $H_{\text{norm}} \approx 1$ **AND** $CV \gg 0$: the column is a
  **fact measure** (high diversity and high variability) [@kimball2013].
- $CV \approx 0$: constant or technical attribute → Dimension signal.

---

### `calculate_skewness(column_data)`

Computes Fisher's skewness coefficient to detect distribution imbalances
[@abedjan2015].

**Formula:**

$$\gamma_1 = \frac{\mathbb{E}[(X - \mu)^3]}{\sigma^3}$$

**Interpretation:**

- $\gamma_1 \approx 0$: symmetric distribution, consistent with an
  incremental primary key.
- $\gamma_1 \gg 1$: extreme skewness, indicating a column dominated by
  default values (e.g. `9999`) or data entry errors.

---

### `calculate_identifiability_score(column_data)`

Computes a composite score aggregated from the four previous metrics to produce
a single ranking of primary key candidates [@abedjan2015].

**Formula:**

$$I(C) = w_U \cdot U(C) + w_H \cdot H_{\text{norm}}(C) + w_S \cdot (1 - S(C)) - w_\gamma \cdot |\gamma_1(C)|$$

where $w_U$, $w_H$, $w_S$, $w_\gamma$ are configurable weights in the control
file, and the term $(1 - S(C))$ rewards completeness.

**Interpretation:**

A high $I(C)$ score indicates a strong primary key candidate. Columns are
sorted by descending $I(C)$ before being submitted to the greedy composite key
discovery algorithm.

---

## 3. Topological Inference & Graph Construction (`join_candidate.py` and `adjacency.py`)

---

### `calculate_join_success_ratio(source_col, target_col)`

Determines the viability of a Foreign Key → Primary Key relationship by
computing the set-inclusion rate between two value domains [@demarchi2002].

**Formula:**

Let $T_s$ be the source table and $T_t$ the target table (primary key $K_t$):

$$JSR(C_s \rightarrow K_t) = \frac{|\pi_{C_s}(T_s) \cap \pi_{K_t}(T_t)|}{|\pi_{C_s}(T_s)|}$$

**Interpretation:**

An edge is created in the graph if $JSR \geq \theta_{jsr}$ (configurable
threshold, default: $0.95$). This computation forms the basis of the
**referential integrity** validation of the model [@kimball2013].

---

### `build_adjacency_matrix(tables, joins)`

Builds the mathematical representation of the relational schema as a directed
graph [@lehner1998].

**Formula:**

The binary adjacency matrix $A$ of size $N \times N$ is defined such that for
two tables $T_i$ and $T_j$:

$$A_{i,j} = \begin{cases} 1 & \text{if } JSR(T_i \rightarrow T_j) \geq \theta_{jsr} \\ 0 & \text{otherwise} \end{cases}$$

**Interpretation:**

Matrix $A$ is the entry point for all subsequent steps: role inference, cycle
detection, candidate construction, and structural validation.

---

## 4. Model Construction & Evaluation (`role_inference.py` and `ranking.py`)

---

### `infer_table_roles(adjacency_matrix, entropy_scores)`

Determines the architectural role of each table (Fact, Dimension, or Isolated)
by combining graph theory and semantic scores, following dimensional modelling
methodology [@kimball2013] and multidimensional normal forms [@lehner1998].

**Decision logic:**

| Role | Criteria |
|---|---|
| **Dimension** | In-degree $> 0$ in $A$ AND low average $\overline{H_{\text{norm}}}$ [@kimball2013] |
| **Fact** | Maximum out-degree AND low or null in-degree AND high $\overline{CV}$ [@kimball2013] |
| **Isolated** | In-degree $= 0$ AND Out-degree $= 0$ (pruned from the candidate model) |

---

### `calculate_model_score(candidate_model)`

Generates a viability score to rank candidate architectures. Inspired by
**Occam's Razor**: prefer the simplest model that best explains the data
[@kimball2013].

**Formula:**

$$\mathbb{S}(M) = \sum_{i} w_i \cdot f_i(M) - \sum_{j} p_j \cdot g_j(M)$$

where:

- $f_i(M)$ are the **reward terms**: number of validated Fact → Dimension
  joins, number of numeric attributes (measures), number of connected dimensions,
- $g_j(M)$ are the **penalty terms**: total number of tables, presence of
  redundant intermediate tables,
- $w_i$ and $p_j$ are configurable weights in the control file.

Candidates are sorted by descending $\mathbb{S}$. Ties are broken by the
number of numeric attributes covered.

---

## 5. Candidate Validation Engine

The four rules below are applied in order. A model proceeds to rule $n+1$ only
if it has passed rule $n$.

---

### `validate_structural_topology(adjacency_matrix)` — Rule Level 1

Applies a Depth-First Search (DFS) to verify that the adjacency matrix forms a
**Directed Acyclic Graph (DAG)** [@lehner1998]. Detection of a single cycle
disqualifies the model, preventing infinite join loops in analytical queries.

---

### `validate_semantic_homogeneity(fact_table, dim_table)` — Rule Level 2

Verifies semantic separation between the fact table and its dimensions,
following the role separation principle [@kimball2013]. Let $F$ be the set of
fact table columns and $D$ the dimension columns (excluding join keys $K$):

$$( F \setminus K ) \cap ( D \setminus K ) = \emptyset$$

This rule detects columns appearing simultaneously in a Fact and a Dimension,
indicating ambiguous modelling or incorrect denormalisation [@lehner1998].

---

### `validate_deterministic_granularity(table, pk_columns)` — Rule Level 3

Validates the absence of hidden duplicates on entities, ensuring the fact grain
is deterministic [@kimball2013]. For a table $T$ and a grain defined by
columns $PK$ [@lehner1998]:

$$\text{Count}(T) = \text{Count}\!\left(\text{Distinct}\!\left(\pi_{PK}(T)\right)\right)$$

A duplicated tuple indicates an inadequate grain: either a missing key or an
incomplete composite key.

---

### `validate_aggregation_stability(fact_table, dim_table, measure_col)` — Rule Level 4

The most critical rule: verifies the absence of an involuntary Cartesian
product (*Fan-Out*) during a *Roll-Up* over an inferred dimension [@kimball2013].

**Step 1 — Fine-grain sum:**

$$\Sigma_{\text{fine}} = \sum_{i \in F} M_i$$

**Step 2 — Aggregation simulation:**

$$\Sigma_{\text{agg}} = \sum_{g \in \pi_A(D)} \left( \sum_{k \in \{F \bowtie D\}_{A=g}} M_k \right)$$

**Step 3 — Validation:**

$$\Delta = |\Sigma_{\text{fine}} - \Sigma_{\text{agg}}| \leq \epsilon$$

where $\epsilon$ is the machine tolerance (Float64).

If $\Delta > \epsilon$, the relationship is rejected: the join granularity is
incorrect and would produce erroneous aggregated sums in production.

> **Implicit assumption:** this test assumes a 1:N relationship on the tested
> join key. A legitimately multi-valued dimension attribute must be pre-aggregated
> or excluded before this step [@kimball2013].

---

## 6. Certification & Export (`certification.py` and `sql_generator.py`)

---

### `certify_model(model_score, validations)`

Combines the results of the four validation rules using boolean logic
[@kimball2013]. A model receives `is_certified = True` if and only if:

$$\prod_{i=1}^{4} \text{Valid}_i = 1$$

meaning no rule has been violated. The certification report exposes the detail
of passed rules, warnings, and detected issues, along with a certification
score $\in [0, 100]$.

---

### `generate_sql_view(certified_model)`

Deterministically translates the certified graph into an analytical SQL query
(ClickHouse dialect [@clickhouse]), converting validated relationships
($A_{i,j} = 1$) into `LEFT JOIN` operators [@kimball2013].

**Example output (star schema with 4 dimensions):**

```sql
SELECT
    f.sale_id         AS fact_sale_id,
    f.revenue         AS fact_revenue,
    d1.date_id        AS calendar_date_id,
    d1.month_name     AS calendar_month_name,
    d2.customer_name  AS customers_customer_name,
    d3.product_name   AS products_product_name,
    d4.carrier        AS shipments_carrier
FROM `schema`.`sales` AS f
LEFT JOIN `schema`.`calendar`  AS d1 ON f.date_id     = d1.date_id
LEFT JOIN `schema`.`customers` AS d2 ON f.customer_id = d2.customer_id
LEFT JOIN `schema`.`products`  AS d3 ON f.product_id  = d3.product_id
LEFT JOIN `schema`.`shipments` AS d4 ON f.sale_id     = d4.sale_id
```
