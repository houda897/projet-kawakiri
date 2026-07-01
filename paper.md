---
title: 'Kawakiri: Reverse Engineering for Dimensional Model Inference from Undocumented Tabular Data'
tags:
  - Python
  - data engineering
  - dimensional modeling
  - data warehousing
  - schema inference
  - ClickHouse
authors:
  - name: "RAMDANE Nour el houda"
    affiliation: 1
  - name: "BERGER Maxime"
    affiliation: 2
affiliations:
  - index: 1
    name: "KOUSHIN, France"
  - index: 2
    name: "Aix-Marseille School of Economics - AMSE, France"
date: 19 June 2026
bibliography: paper.bib
---

## Summary

Kawakiri is an open-source library for reverse-engineering dimensional models from
undocumented tabular data sources. Given a folder of raw CSV exports, it ingests the
data into ClickHouse, profiles every column, reconstructs non-overlapping functional
column groups, materializes logical tables, infers candidate primary keys and join
relationships, classifies logical tables into fact and dimension roles, assembles candidate
dimensional-model graphs (star, snowflake, or constellation), and validates each
candidate against a fixed set of structural rules before certifying it in a JSON
report. Unlike tools that require an analyst to declare keys and relationships up
front, Kawakiri derives them from statistical evidence in the data itself —
uniqueness, entropy, null ratios, and aggregation behavior — and only accepts a
candidate model once it survives referential, granularity, semantic, and
aggregation-stability checks. The output is a certified, auditable dimensional model
together with generated SQL views, intended to shorten the path from an undocumented
data export to a query-ready analytical schema.

## Statement of need

Analytics and data engineering teams frequently receive tabular extracts — CSV dumps
from legacy systems, data-lake exports, or third-party feeds — with no documentation
of primary keys, foreign keys, or intended fact/dimension roles. Building a
dimensional model from such sources by hand is slow, and the diagnosis is rarely
unambiguous: several relationship graphs can fit the same noisy source tables equally
well, a non-identifiability problem that manual modeling does not address
systematically.

Kawakiri is aimed at data engineers and analytics engineers who need to bootstrap a
first dimensional-model hypothesis from undocumented relational extracts before
committing to a production warehouse design, as well as students and practitioners
studying automated approaches to dimensional modeling. It is not a substitute for
domain expertise: its output is a certified candidate model with an explicit,
inspectable evidence trail (which statistical tests passed, which structural rules
were checked) that a human modeler can confirm, reject, or refine, rather than a
black-box recommendation.

## State of the field

Existing tooling for dimensional-model construction falls into two broad categories.

Transformation and testing frameworks such as dbt [@dbt] and Dataform [@dataform] are
declarative: they let an engineer encode SQL transformations and assertions
(uniqueness, referential tests) once the model's keys and relationships are already
known. They do not attempt to discover those relationships from the data itself, so an
incorrect or incomplete manual declaration of keys propagates silently into the rest of
the pipeline.

Classical reverse-engineering and profiling tools such as SchemaSpy [@schemaspy]
reconstruct relationship diagrams from physical database metadata — declared
`FOREIGN KEY` constraints, naming conventions — and provide little value on
denormalized CSV or data-lake sources where no such metadata exists. Data-quality
frameworks such as Great Expectations [@greatexpectations] compute column-level
statistics (completeness, cardinality) but do not link those statistics to a
dimensional-model hypothesis or to structural validation rules such as deterministic
granularity or aggregation stability, both established concerns in dimensional-modeling
methodology [@kimball2013].

Kawakiri's contribution is to combine the two: it infers keys, joins, and
fact/dimension roles statistically, without requiring declared constraints. Column names
can contribute weak secondary evidence, but physical and statistical tests carry the
decision. Kawakiri then subjects the resulting candidate model to the same
class of structural checks (referential integrity, granularity, semantic separation,
aggregation stability) that a dimensional-modeling practitioner would apply manually.
For research and teaching contexts that involve undocumented or rapidly changing source
schemas, this removes the assumption — implicit in dbt, Dataform, and similar tools —
that the dimensional structure is already known, while going beyond what
general-purpose profilers report by tying statistical evidence directly to an
accept/reject decision on the candidate model.

## Software design

Kawakiri is organized as a sequential, inspectable pipeline rather than a single
monolithic inference step:

```text
-> ingestion 
-> profiling 
-> identifiability scoring 
-> functional-dependency grouping
-> logical fact/dimension materialization
-> logical-table profiling
-> primary-key inference
-> join inference 
-> adjacency-graph construction 
-> fact/dimension role inference
-> candidate-model construction 
-> ranking 
-> structural validation
-> granularity validation 
-> semantic validation 
-> aggregation-stability validation
-> certification 
-> (optional) SQL view generation 
-> JSON report export
```

Each stage persists its output to a metadata store kept in a database separate from
the analytical data being modeled (`META_DB` vs. `CH_DATABASE`), so a candidate model,
its supporting statistics, and its validation issues can be inspected independently.
Individual CLI stages can be rerun when their prerequisite metadata is still available;
`run-all` deliberately rebuilds computed metadata for a reproducible complete execution.

ClickHouse was chosen as the underlying engine because the profiling stage is
dominated by columnar aggregations (distinct-value counts, null ratios, entropy
estimates) over potentially large tables — the access pattern ClickHouse [@clickhouse]
is optimized for — and the same engine then hosts the inferred model's generated SQL
views, avoiding a second runtime dependency.

Join-acceptance and identifiability thresholds (e.g., the join-success-ratio cutoff
$\theta_{jsr}$) are exposed as configuration rather than hard-coded, since the noise
tolerance appropriate for a given source system is domain-dependent. Validation rules
are implemented as independent, named checks rather than a single pass/fail function,
so a certification report can state exactly which rule a candidate failed and why.

## Mathematics and algorithms

Kawakiri does not infer keys, joins, and table roles from column names alone; each
hypothesis is checked against physical or statistical evidence computed from the data.
Before key inference, functional dependencies reconstruct coherent logical groups. A
column is attached to a group only after a dependency test, while unassigned columns
remain explicit singletons in grouping metadata.

| Metric | Interpretation |
| --- | --- |
| `uniqueness_ratio` | Distinct values over total rows; close to 1 supports an identifier |
| `null_ratio` | Share of missing values; a key candidate should be close to 0 |
| `entropy_ratio` | Normalized Shannon entropy; high values support identifier-like columns |
| `identifiability_score` | Combined uniqueness, entropy, and completeness score used to rank primary-key candidates |
| `variation_coefficient` | Normalized numeric variability; high values can indicate a fact measure |

**Identifiability and semantic classification.** For a column $C$ with distinct values
$X = \{x_1, \dots, x_n\}$ and empirical probabilities $P(x_i)$, the engine computes the
Shannon entropy $H(C) = -\sum_i P(x_i)\log_2 P(x_i)$ [@shannon1948], normalized as
$H_{norm}(C) = H(C) / \log_2(N)$, where $N$ is the row count. Because $H_{norm}(C) \to
1$ only when nearly every value is unique ($n \to N$), this normalization is
deliberately stricter than the conventional entropy normalization by $\log_2(n)$: it is
designed to isolate identifier-like columns rather than to measure category diversity
in general. Coupled with the coefficient of variation $CV(C) = \sigma/\mu$ for numeric
columns (undefined when $\mu = 0$, in which case the column is excluded from
variability-based scoring), low-entropy columns support a dimension classification and
high-entropy, high-variability numeric columns support a fact classification.

**Join inference and topology.** A directed edge from a candidate foreign key $C_s$ in
table $T_s$ to a candidate primary key $K_t$ in table $T_t$ is accepted when the join
success ratio

$$JSR(C_s \rightarrow K_t) = \frac{N_{matched}}{N_{source,non-null}}$$

meets a configurable tolerance $\theta_{jsr}$ (default $0.95$) and where $N_{matched}$ is the number of rows successfully joined, and $N_{source,non-null}$ is the number of non-null rows in the source column.

 The accepted edges form
an adjacency matrix $A$, which is checked for cycles via a depth-first traversal; a
candidate model is rejected if $A$ is not acyclic, since a cyclic join graph cannot be
resolved into a well-defined star, snowflake, or constellation shape.



**Aggregation stability.** For a measure $M$ in fact table $F$ and a categorical
attribute $G$ of dimension $D$, the engine compares the row-level sum $\Sigma_{fine} =
\sum_{i \in F} M_i$ to the sum obtained after a left join and a `GROUP BY` on $G$,
$\Sigma_{agg}$. A model is accepted only if $|\Sigma_{fine} - \Sigma_{agg}| \le
\epsilon$. This check assumes a one-to-one join on the tested key, so a legitimate
multi-valued dimension attribute would also need to be excluded or pre-aggregated
before this test — a known limitation documented alongside the validator.

### Validation rules

Five structural rules currently gate certification:

- **Referential integrity**: fact-to-dimension links should not create orphan values.
- **Topology**: the join graph must be acyclic, with no self-loops or invalid
  fact-to-fact links.
- **Deterministic granularity**: fact rows must be uniquely identified by the grain
  induced by their dimension keys.
- **Semantic separation**: dimension tables should not behave like fact tables, and
  fact tables should not be dominated by descriptive attributes.
- **Aggregation stability**: measures must remain stable when aggregated through
  dimensional levels (see above).

A candidate model's final status — `VALID`, `WARNING`, or `INVALID` — combines its
ranking with the outcome of these five rules.

## Research impact statement

Kawakiri was developed during an academic internship and validated through an
end-to-end integration test suite that exercises the full pipeline against a reference
dataset with a known star-schema ground truth (one fact table, four dimensions, and one
deliberately isolated table), asserting that table-role classification, join
inference, and final certification status match the expected model. Each pipeline
stage and validation rule is implemented and tested as an independent unit, and the
certification report format is designed so that new structural rules can be added
without changing the report schema.

## AI usage disclosure

Generative AI assistance (Anthropic Claude 3.5 Sonnet and GitHub Copilot) was used during this project's development, specifically: (1)
drafting and debugging portions of the pipeline source code, (2) drafting portions of
the project documentation, and (3) drafting and revising this paper, including its
structure and compliance with JOSS submission requirements. All AI-assisted code was
reviewed and validated by the author and by the author's internship supervisor before
being merged; no AI-generated code was accepted without this review. Core design
decisions — the staged pipeline architecture, the choice of statistical metrics, the
set of structural validation rules, and the database separation between analytical and metadata storage  were made by the author.

## Acknowledgements

The author thanks Mickaël Martin novet from Aix-Marseille school of echonomics and Anthony Tinson from Koushin for active supervision and feedback during this internship. This work received no dedicated financial support