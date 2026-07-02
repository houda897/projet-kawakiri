# Kawakiri

![Python Version](https://img.shields.io/badge/python-3.10%2B-blue.svg)
![ClickHouse](https://img.shields.io/badge/ClickHouse-required-yellow.svg)
![Status](https://img.shields.io/badge/status-alpha-orange.svg)
![Zenodo](https://img.shields.io/badge/DOI-Zenodo-red.svg)
![JOSS](https://img.shields.io/badge/JOSS-!!!VERSION!!!-lgreen.svg)

Kawakiri is an open-source platform that extracts decision-making models and reconstructs candidate dimensional deterministic models from various undocumented sources. Using column-based database profiling, functional dependencies, key and join inference, graph topology analysis, and explicit validation rules, Kawakiri generates auditable snowflake, star, or constellation models.

### Features

- automated dimensional modeling
- rule-based schema inference
- data profiling
- functional dependency discovery
- column-oriented data analysis
- axiom-based model synthesis
- database reverse engineering

## What the pipeline does

```text
CSV ingestion:
-> raw column profiling and statistics
-> identifiability scoring
-> preliminary source keys and relationships
-> functional column grouping
-> logical fact/dimension materialization, with unresolved sources kept neutral
-> logical-table profiling
-> primary-key and join inference
-> adjacency graph and table roles
-> STAR / SNOWFLAKE / CONSTELLATION candidates
-> ranking and validation
-> certification
-> SQL views, JSON report, and Mermaid schema
```

Functional groups are based on verified dependencies. A group can only be extended
when its current columns determine an unassigned column. Columns without
such evidence remain singletons in the grouping metadata and are not silently added
to a dimension. Referenced, normalized sources are kept as coherent entities,
while groups extracted from flat tables must demonstrate repeated determinant values
and real compression gains.

## Validation rules

Kawakiri currently checks the following:

- key uniqueness, completeness, and normalized Shannon entropy;
- referential integrity and orphan values;
- graph topology, including cycles and invalid fact-to-fact edges;
- deterministic fact granularity;
- minimality of the fact grain and model coverage;
- semantic separation between facts and dimensions;
- aggregation stability across inferred joins.

## Architecture

| Layer | Main classes | Responsibility |
| --- | --- | --- |
| Ingestion | `CsvIngestionEngine` | Detect encoding, delimiter and types; import CSV rows |
| Profiling | `ProfileEngine`, `compute_column_stats` | Compute cardinality, null ratio, entropy and numeric statistics |
| Grouping | `FunctionalGroupBuilder` | Build non-overlapping functional column groups |
| Logical modeling | `FactDimensionBuilder`, `LogicalTableBuilder` | Classify proven groups, preserve unresolved sources, and materialize logical tables |
| Inference | `PrimaryKeyEngine`, `JoinEngine`, `AdjacencyMatrixEngine`, `TableRoleEngine` | Infer keys, joins, graph edges and roles |
| Modeling | `DecisionModelCandidateBuilder`, `ModelRanking` | Build and rank dimensional-model candidates |
| Validation | Structural, granularity, semantic and aggregation validators | Apply the conformity rules |
| Generation | `SQLViewGenerator` | Generate views for the best certified model |
| Reporting | `CertificationReportExporter` | Export JSON and Mermaid results |

Computed evidence is stored in a dedicated ClickHouse metadata database.

## Requirements

- Internet connection;
- Git installed;
- Python 3.10 or later;
- a reachable ClickHouse server.

## Installation

```bash
pyt
Repository navigation
Code
Issues
Pull requests
Actions
Projects
Wiki
Security and quality
Insights
Settings
hon3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

Create `.env` at the repository root:

```env
CH_HOST=localhost
CH_PORT=your_port
CH_DATABASE=your_database
CH_USER=your_user
META_DB=your_metadata_database
CH_PASSWORD=your_password
```

The data and metadata databases are created when the pipeline initializes its schemas.

## Quick start

Place one CSV file per source table in a folder, then run:

```bash
kawakiri run-all path/to/csv-folder --report report.json
```

The equivalent source-tree command is:

```bash
python code/main.py run-all path/to/csv-folder --report report.json
```

The command creates:

- `report.json`: certification results and model coverage;
- `report.mmd`: Mermaid ER representation;
- ClickHouse SQL views, unless `--skip-sql-views` is used.

## Step-by-step execution

```bash
kawakiri ingest-folder path/to/csv-folder
kawakiri profile-basic
kawakiri score-identifiability
kawakiri infer-source-keys
kawakiri infer-source-joins
kawakiri infer-functional-groups
kawakiri build-logical-tables
kawakiri profile-logical-tables
kawakiri score-identifiability
kawakiri infer-pk
kawakiri infer-joins
kawakiri build-adjacency
kawakiri infer-table-roles
kawakiri build-model-candidates
kawakiri rank-models
kawakiri validate-structure
kawakiri validate-granularity
kawakiri validate-semantic-homogeneity
kawakiri validate-aggregation-stability
kawakiri certify-models
kawakiri generate-sql-views
kawakiri export-certification-report report.json
```

`score-identifiability` is intentionally run twice: first for the raw sources, then
after `profile-logical-tables` for the materialized logical tables.

Inspect the available commands with:

```bash
kawakiri --help
```

## Development

Run the unit tests:

```bash
pytest
```

Run the ClickHouse integration test explicitly:

```bash
pytest --run-integration tests/integration/test_e2e_pipeline.py
```

The integration test dataset can be download from Zenodo ([link here](https://zenodo.org/records/21100022)) or with de DOI :

```bash
10.5281/zenodo.21100022
```

Build the documentation with strict link and configuration checks:

```bash
mkdocs build --strict
```

Preview it locally with `mkdocs serve`.

See [CONTRIBUTING.md](CONTRIBUTING.md) and the documentation site for further details.

## Project Structure

```
Kawakiri
  └── code
  |     └── config
  |     └── core
  |     └── data
  |     └── generation
  |     └── inference
  |     └── modeling
  |     └── profiling
  |     └── reporting
  |     └── semantic
  |     └── stats
  |     └── validation
  |     └── main.py
  └── docs
  └── tests   
```

## Citation

Academic citation metadata is provided in [CITATION.cff](CITATION.cff). The JOSS paper
sources are available in [paper.md](paper.md) and [paper.bib](paper.bib).

## Contributors

See the [AUTHORS](AUTHORS.rst) file for a complete list of contributors to the project.

## License

Kawakiri is distributed under the [MIT License](LICENSE).
