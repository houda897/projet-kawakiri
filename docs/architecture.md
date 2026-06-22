# Technical Architecture

Kawakiri is organized as a sequence of independent engines. Each engine computes
one kind of evidence and stores metadata in ClickHouse so later steps can reuse
the results.

| Layer | Responsibility |
| --- | --- |
| Ingestion | Import CSV files into ClickHouse |
| Profiling | Compute column-level statistics |
| Statistics | Compute entropy, identifiability, and dependency evidence |
| Inference | Infer primary keys, joins, adjacency graph, and table roles |
| Modeling | Build star, snowflake, and constellation candidates |
| Validation | Test structure, granularity, semantic homogeneity, and aggregation stability |
| Generation | Create SQL views for certified models |
| Reporting | Export JSON certification reports |

## Pipeline

```text
Raw CSV files
-> ClickHouse tables
-> column profiles
-> key candidates
-> join candidates
-> adjacency graph
-> table roles
-> model candidates
-> validation results
-> certified model
-> SQL view and JSON report
```

## Table Roles

Kawakiri uses four table roles:

- `FACT`: transactional or measurement-like table.
- `DIMENSION`: descriptive table used to contextualize facts.
- `ISOLATED`: table with no confirmed relationship to the inferred graph.
- `UNKNOWN`: table with ambiguous evidence.

`ISOLATED` and `UNKNOWN` tables are not forced into a model candidate.
