# Kawakiri: Reverse Engineering for Decision Model Inference

## Summary

Kawakiri is an open-source reverse-engineering library for inferring decision models
from undocumented data sources. It ingests raw CSV data into ClickHouse, profiles table
structures, infers candidate keys and joins, builds decision-model candidates, validates
their structural consistency, and exports a final certification report.

The objective is to move from raw relational data to decision-model hypotheses such as
star schemas, snowflake schemas, and constellations. These hypotheses are not accepted
only because they look plausible. They are evaluated through statistical evidence and
structural validation rules.

## Statement of Need

Organizations often store operational data without complete documentation of primary
keys, foreign keys, dimensional roles, or analytical grain. In such contexts, building a
decision model manually is slow and error-prone. Several graph structures may appear
valid on noisy data, which creates a non-identifiability problem: different candidate
models can explain the same source tables.

Kawakiri addresses this problem by combining data profiling, key inference, join
testing, graph construction, fact/dimension classification, and model validation. The
goal is not only to discover a possible model, but also to reject weak or inconsistent
models using explicit decision-model rules.

## Scientific Metrics

Kawakiri does not infer keys, joins, and table roles only from column names. It uses
statistical evidence to support or reject structural hypotheses.

| Metric | Interpretation | Decision-model use |
| --- | --- | --- |
| `uniqueness_ratio` | Ratio between distinct values and total rows | A value close to `1` supports the hypothesis that a column can identify rows |
| `null_ratio` | Ratio of missing values | A key candidate should have a value close to `0`; many nulls weaken the key hypothesis |
| `entropy_ratio` | Normalized Shannon entropy of a column | High entropy supports identifier-like columns; low entropy suggests categories, flags, or repeated descriptors |
| `identifiability_score` | Combined score based on uniqueness, entropy, and completeness | Used to rank candidate identifiers before selecting primary keys |
| `variation_coefficient` | Normalized variability of numeric values | High variability can indicate fact measures such as amounts, prices, quantities, or durations |
| `skewness_score` | Asymmetry of a numeric distribution | Strong asymmetry can reveal measure-like behavior and helps detect suspicious columns inside dimensions |

These metrics are not sufficient to certify a model by themselves. They provide
statistical evidence. A model is accepted only when this evidence remains consistent
with structural rules such as referential integrity, deterministic granularity, semantic
separation, topology, and aggregation stability.

## Methodology

The current pipeline follows these steps:

```text
Raw tables
-> ingestion into ClickHouse
-> column profiling
-> identifiability scoring
-> primary-key inference
-> join inference
-> adjacency graph construction
-> fact/dimension role inference
-> candidate model generation
-> model ranking
-> structural validation
-> granularity validation
-> model certification
-> SQL view generation
-> JSON certification report
```

Candidate models are represented as decision-model graphs. A star model contains one
fact table connected directly to dimensions. A snowflake model extends this with
dimension-to-dimension links. A constellation model contains several fact tables that
share dimensions.

## Validation Rules

Kawakiri currently focuses on the following decision-model rules:

- **Referential integrity**: fact-to-dimension links should not create orphan values.
- **Topology**: the graph should match a decision-model shape and avoid invalid cycles,
  self-loops, and inappropriate fact-to-fact links.
- **Deterministic granularity**: fact rows should be uniquely identified by the grain
  induced by their dimension keys.
- **Semantic separation**: dimension tables should not behave like fact tables, and fact
  tables should not be dominated by descriptive attributes.
- **Aggregation stability**: measures should remain stable when aggregated through
  dimensional levels.

The final certification engine combines model ranking and validation outputs into a
model-level status: `VALID`, `WARNING`, or `INVALID`.

## Current Limitations

The aggregation stability rule is still being refined. The current implementation checks
whether joins with dimensions preserve aggregate values, which is useful for detecting
fan-out or data loss. The target rule should additionally compare a measure at the fine
grain with the same measure aggregated through a higher dimensional level, such as
month, category, or region.

Future work also includes stronger integration tests, public example datasets, and a
more formal discussion of scoring thresholds.
