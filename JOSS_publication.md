## State of the Field

The governance and modeling of decision-making data architectures (such as star or snowflake schemas) traditionally rely on intensive human expertise and manual declarations. In the current data engineering landscape, existing tools primarily fall into two categories, against which **DŌTEI** introduces a paradigm shift.

### Transformation and Assertion Tools (e.g., dbt, Dataform)
Popular frameworks like `dbt` (data build tool) excel in modular SQL transformation programming and the application of data tests (assertions). However, these tools are purely **declarative** and **passive**: they rely entirely on the data engineer to manually define primary keys, relationships, and uniqueness constraints. They possess no algorithmic introspection capabilities to discover or validate the underlying structural coherence of an undocumented model. Human error during the configuration of these assertions remains a major vector for analytical regression.

### Reverse Engineering and Classical Profiling Tools (e.g., SchemaSpy, Great Expectations)
Traditional reverse-engineering tools reconstruct relationship graphs exclusively by inspecting physical database metadata (e.g., `FOREIGN KEY` constraints, column naming conventions). When faced with raw, denormalized data sources or data lakes (CSV, Parquet files), these tools systematically fail due to the lack of structural metadata. Furthermore, classical statistical profilers are limited to isolated metrics (completeness rates, raw cardinality) without ever linking these metrics to a global, multidimensional semantic validation.

### The DŌTEI Paradigm: Automation through Iron Rules
**DŌTEI** fundamentally distinguishes itself by positioning as an **active inference and mathematical certification engine**. Instead of relying on existing metadata or human configuration, DŌTEI treats raw data as a statistical and semantic vector space. 

Through the sequential application of its **Iron Rules**, it solves the problem of non-identifiability by executing semantic separation, deterministic granularity, and aggregation stability tests. It does not merely draw a graph: it mathematically proves whether a candidate model is stable, viable, and free of pathological behaviors (such as Fan-Out or infinite join loops), thereby offering a certification that no tool on the market provides today.

---

## Mathematics & Algorithms

The computational core of **DŌTEI** relies on the convergence of information theory, graph theory, and the structural analysis of relational databases.

### Information Theory and Semantic Classification

To autonomously classify tables into units of *Facts* (quantitative measures) or *Dimensions* (descriptive attributes), DŌTEI profiles each column $C$ by calculating its **Normalized Shannon Entropy**. 

Let $X = \{x_1, x_2, \dots, x_n\}$ be the set of distinct values observed in column $C$, and $P(x_i)$ the probability of occurrence of the value $x_i$. The raw entropy $H(C)$ is defined by:

$$H(C) = - \sum_{i=1}^{n} P(x_i) \log_2 P(x_i)$$

To eliminate the influence of table size (total number of rows $N$), the system calculates the normalized entropy $H_{norm}(C)$ relative to the theoretical maximum entropy ($\log_2 N$):

$$H_{norm}(C) = \frac{H(C)}{\log_2 N}$$

This metric is coupled with the **Coefficient of Variation** ($CV$) for numerical variables, measuring the relative dispersion around the mean $\mu$ with a standard deviation $\sigma$:

$$CV(C) = \frac{\sigma}{\mu}$$

* **Proof of Semantic Separation:** A table is classified as a *Dimension* if its semantic space is dominated by columns with low normalized entropy ($H_{norm}(C) \to 0$, characteristic of categorical variables). Conversely, a table is elected as a *Fact* if it is predominantly composed of continuous metrics with high entropy and a high coefficient of variation ($H_{norm}(C) \to 1, CV \gg 0$).

### Topology Algorithms and Adjacency Matrix

The inference of directional relationships between tables is based on the calculation of the **Join Success Ratio** ($JSR$). Let $T_s$ be a source table (containing a candidate foreign key $C_s$) and $T_t$ a target table (possessing a validated primary key $K_t$). The $JSR$ measures the set inclusion rate of the projections:

$$JSR(C_s \rightarrow K_t) = \frac{|\pi_{C_s}(T_s) \cap \pi_{K_t}(T_t)|}{|\pi_{C_s}(T_s)|}$$

A directed relationship (edge $e$) is validated if and only if $JSR(C_s \rightarrow K_t) \ge \theta_{jsr}$, where $\theta_{jsr}$ is a probabilistic tolerance threshold (e.g., $0.95$). 

From these edges, the engine constructs the **Adjacency Matrix** $A$ of the global model, where each element $A_{ij}$ is defined by:

$$A_{ij} = \begin{cases} 1 & \text{if } JSR(C_i \rightarrow K_j) \ge \theta_{jsr} \\ 0 & \text{otherwise} \end{cases}$$

* **Cycle Detection (Topology):** To prohibit infinite loops during analytical query generation, the adjacency matrix $A$ is subjected to a topological sorting algorithm (based on Depth-First Search - DFS). The model is disqualified if the graph is not a **Directed Acyclic Graph (DAG)**, proving the presence of a circular dependency.

### Aggregation Stability Validation

The final validation (Level 3 Iron Rule) mathematically simulates a grouping query (*Roll-Up*) to prove the absence of an unintended Cartesian product (*Fan-Out*). 

Let $M$ be a quantitative measure from the fact table $F$. The engine first calculates the raw reference sum at the finest grain:

$$\Sigma_{fine} = \sum_{i \in F} M_i$$

It then simulates the sum after executing a left join ($\bowtie$) with a dimension table $D$ and a grouping (`GROUP BY`) on a categorical attribute $G$ of the dimension:

$$\Sigma_{agg} = \sum_{g \in \pi_G(D)} \left( \sum_{k \in \{F \bowtie D\}_{G=g}} M_k \right)$$

The model only obtains its certification if the law of conservation of data mass is respected, evaluated against the machine precision tolerance $\epsilon$:

$$\Delta = |\Sigma_{fine} - \Sigma_{agg}| \le \epsilon$$

If $\Delta > \epsilon$, the engine mathematically proves that the model's granularity is unstable, resulting in the immediate rejection of the candidate.