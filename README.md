# Kawakiri

![Python Version](https://img.shields.io/badge/python-3.10%2B-blue.svg)
![ClickHouse](https://img.shields.io/badge/ClickHouse-Ready-yellow.svg)

**Kawakiri** is an open-source reverse-engineering library for discovering decision
models from undocumented data sources. It ingests raw CSV files into ClickHouse,
profiles the data, infers keys and joins, classifies tables as facts or dimensions,
builds candidate decision models, validates them with structural rules, and exports a
final certification report.

The long-term goal is to support a scientific open-source deliverable for JOSS
publication by combining reverse engineering, structural data science, and formal
decision-model validation.

## Project Goals

1. **Reverse Engineering**: discover table structure from unknown CSV or SQL sources.
2. **Decision Modeling**: infer facts, dimensions, joins, stars, snowflakes, and constellations.
3. **Model Validation**: apply structural rules such as referential integrity, topology checks,
   deterministic granularity, semantic homogeneity, and aggregation stability.
4. **Certification**: compile validation results into a final confidence report for each model.

## Scientific Rationale

Kawakiri starts from a raw set of tables without documentation. Several decision
structures can look plausible on noisy data, so the project does not stop at discovering
one graph. It generates candidate models, scores them, and invalidates weak structures
with explicit rules.

The core idea is:

```text
Raw tables
-> statistical profiling
-> key and join inference
-> adjacency graph
-> fact/dimension roles
-> candidate models
-> validation rules
-> certification report
```

The current validation layer focuses on:

- **referential integrity**: detect orphan rows between fact and dimension tables;
- **topology**: reject self-loops, problematic cycles, and invalid fact-to-fact links;
- **deterministic granularity**: verify that fact rows are uniquely identified by their grain;
- **semantic homogeneity**: detect fact-like measures inside dimensions and descriptive
  attributes inside facts;
- **aggregation stability**: verify that measures remain stable after dimensional roll-up;
- **model certification**: combine ranking and validation results into a final status.

## Architecture

The project is organized around small engine classes. Each engine owns one step of the
pipeline and persists its reusable results in ClickHouse metadata tables.

| Layer | Main classes | Responsibility |
| --- | --- | --- |
| Ingestion | `CsvIngestionEngine` | Detect delimiters and types, create tables, insert CSV rows |
| Profiling | `ProfileEngine` | Store base column profiles and launch advanced statistics |
| Statistics | `IdentifiabilityEngine` | Score how suitable columns are as identifiers |
| Inference | `PrimaryKeyEngine`, `JoinEngine`, `AdjacencyMatrixEngine`, `TableRoleEngine` | Infer keys, joins, graph edges, and fact/dimension roles |
| Modeling | `DecisionModelCandidateBuilder`, `ModelRanking` | Build and rank STAR, SNOWFLAKE, and CONSTELLATION candidates |
| Validation | `StructuralValidator`, `GranularityValidator`, `SemanticHomogeneityValidator`, `AggregationStabilityValidator`, `ModelCertificationEngine` | Validate candidate models and produce certification results |
| Generation | `SQLViewGenerator` | Generate SQL views from the best certified model |
| Reporting | `CertificationReportExporter` | Export the final certification report as JSON |

## Installation

Prerequisites:

- Python 3.10+
- A running ClickHouse instance

Install the project:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

For development, install the optional development dependencies:

```bash
pip install -e ".[dev]"
```

The `pyproject.toml` file contains the runtime dependencies:

- `clickhouse-connect`
- `python-dotenv`
- `rapidfuzz`
- `colorama`

It also contains development tools such as `pytest`, `pytest-cov`, `black`, `ruff`,
`mkdocs`, and `mkdocs-material`.

## Configuration

Create a `.env` file at the project root. Do not commit this file.

```env
CH_HOST=localhost
CH_PORT=your_port
CH_DATABASE=your_database
CH_USER=your_user
CH_PASSWORD=your_password
```

The metadata schema is created automatically by the pipeline when needed.

### CSV Ingestion Options

CSV ingestion is conservative by default. Date and datetime values are kept as strings
unless temporal inference is explicitly enabled in `config/scoring.py`.

The main ingestion options are:

| Setting | Purpose |
| --- | --- |
| `INFER_TEMPORAL_TYPES` | Enables automatic `Date32` and `DateTime` inference when set to `True` |
| `DATE_FORMATS` | Accepted date formats, for example `%Y-%m-%d` or `%d/%m/%Y` |
| `DATETIME_FORMATS` | Accepted datetime formats |
| `NULL_TOKENS` | Text values interpreted as nulls during import |

Example:

```python
INGESTION_SETTINGS = {
    "INFER_TEMPORAL_TYPES": False,
    "DATE_FORMATS": ("%Y-%m-%d", "%d/%m/%Y"),
    "DATETIME_FORMATS": ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"),
    "NULL_TOKENS": ("", "null", "none", "nan", "n/a"),
}
```

Rows that look like export metadata or separator lines are skipped during CSV import and
counted in the ingestion metadata as `skipped_dirty_rows`.

## Quick Start

Prepare a folder containing the CSV files to analyze. Kawakiri expects one table per
CSV file, and the folder path is provided by the user.

Run the full available pipeline:

```bash
kawakiri run-all path/to/csv-folder --report certification-report.json
```

This command executes:

```text
ingest-folder
profile-basic
score-identifiability
infer-pk
infer-joins
build-adjacency
infer-table-roles
build-model-candidates
rank-models
validate-structure
validate-granularity
validate-semantic-homogeneity
validate-aggregation-stability
certify-models
generate-sql-views
export-certification-report
```

If all certified models are invalid, SQL view generation is skipped with a warning, but the
JSON certification report is still exported.

To run the full pipeline without creating SQL views:

```bash
kawakiri run-all path/to/csv-folder --report certification-report.json --skip-sql-views
```

## Step-by-Step Usage

Each stage can also be executed independently:

```bash
kawakiri ingest-folder path/to/csv-folder
kawakiri profile-basic
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
kawakiri export-certification-report certification-report.json
```

You can inspect all commands with:

```bash
kawakiri --help
```

## Certification Report

The report exporter writes a JSON file containing:

- the target database name;
- the generated timestamp;
- the best model according to certification and ranking;
- all certified models;
- passed, failed, missing, and warning rules;
- detailed validation issues.

Example:

```bash
kawakiri export-certification-report certification-report.json
```

## Contributing

Development setup, code quality checks, and contribution guidelines are described in
`CONTRIBUTING.md`.
