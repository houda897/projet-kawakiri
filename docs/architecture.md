# Technical Architecture

Kawakiri is a staged pipeline. Each engine computes one category of evidence and stores
its result in ClickHouse metadata tables. This makes intermediate decisions observable
and allows individual commands to be rerun during development.

## Pipeline

```mermaid
flowchart TD
    A[CSV files] --> B[CsvIngestionEngine]
    B --> C[ProfileEngine and compute_column_stats]
    C --> D[IdentifiabilityEngine]
    D --> E[FunctionalGroupBuilder]
    E --> F[FactDimensionBuilder]
    F --> G[LogicalTableBuilder]
    G --> H[Logical-table profiling]
    H --> I[PrimaryKeyEngine]
    I --> J[JoinEngine]
    J --> K[AdjacencyMatrixEngine]
    K --> L[TableRoleEngine]
    L --> M[DecisionModelCandidateBuilder]
    M --> N[ModelRanking]
    N --> O[Validation engines]
    O --> P[ModelCertificationEngine]
    P --> Q[SQLViewGenerator]
    P --> R[CertificationReportExporter]
```

## Processing stages

| Stage | Input | Output |
| --- | --- | --- |
| Ingestion | CSV files | Physical ClickHouse tables and ingestion metadata |
| Profiling | Physical columns | Cardinality, null ratio, entropy, variability, skewness |
| Identifiability | Column profiles | Identifier suitability scores |
| Functional grouping | Raw profiles and FD tests | Non-overlapping groups and singletons |
| Logical modeling | Functional groups and profiles | Logical fact/dimension plans |
| Materialization | Logical plans | Logical ClickHouse tables |
| Key inference | Logical profiles | Simple and composite PK candidates |
| Join inference | Source columns and PK candidates | Directed joins with success ratios |
| Graph inference | Confirmed joins | Adjacency edges and table roles |
| Candidate modeling | Roles and graph | Star, snowflake, and constellation candidates |
| Validation | Candidate models | Structural, grain, semantic, and aggregation results |
| Certification | Ranking and validations | `VALID`, `WARNING`, or `INVALID` status |
| Generation | Best certified model | SQL views, JSON report, Mermaid schema |

## Functional grouping

`FunctionalGroupBuilder` tests dependencies of the form:

`D -> c`

where `D` is a simple or composite determinant and `c` is a candidate dependent
column. Candidate groups are scored and selected without column overlap. Remaining
columns are retained as singleton groups.

The builder also computes an iterative closure. If the current group columns determine
an unassigned column, the determinant is promoted to the complete current group before
the column is attached. This preserves the dependency that was actually tested.

`FactDimensionBuilder` does not enrich a dimension with unrelated source columns. It
classifies the functional groups already established by the grouping stage and builds
fact plans from grain, dimension keys, and statistical measure signals.

## Metadata separation

- `CH_DATABASE`: imported source tables, materialized logical tables, and generated views.
- `META_DB`: profiles, functional groups, logical-table definitions, keys, joins,
  adjacency edges, roles, model candidates, validation results, and certifications.

Computed metadata tables are cleared and rebuilt by their owning stage. Source tables
remain separate from this evidence.

## Table roles

Four final roles are used:

- `FACT`: an event or observation table with grain and measure evidence;
- `DIMENSION`: a descriptive lookup connected to facts or other dimensions;
- `ISOLATED`: a table with no confirmed edge;
- `UNKNOWN`: evidence is insufficient or contradictory.

The logical layer additionally uses `FACT_CANDIDATE` and `DIMENSION_CANDIDATE` before
the graph-based role inference step.

## Model validation

Certification combines several independent checks:

1. structural topology and referential integrity;
2. deterministic fact granularity;
3. semantic homogeneity of facts and dimensions;
4. aggregation stability through inferred joins;
5. model ranking and coverage information.

Certification validates the implemented conditions. It cannot resolve every case of
non-identifiability when multiple structures are equally compatible with the data.
