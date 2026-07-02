# Installation Guide

## Requirements

- Python 3.10 or later;
- a running ClickHouse server reachable through its HTTP interface;
- Git for a source checkout.

## Install the project

Clone the repository:

```bash
git clone https://github.com/houda897/projet-kawakiri.git
cd projet-kawakiri
```

### Automated installation

On Linux and macOS:

```bash
chmod +x install.sh
./install.sh
source .venv/bin/activate
```

On Windows Command Prompt:

```bat
install.bat
.venv\Scripts\activate
```

Use `--dev` to install test, lint, coverage, and documentation dependencies. Existing
`.env` files are never overwritten by the scripts.

### Manual installation

From the repository root:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -e ".[dev]"
```

The editable installation provides the `kawakiri` command. Commands can also be run
directly with `python code/main.py`.

## Configure ClickHouse

Copy `.env.example` to `.env`, then edit the ClickHouse connection:

```bash
cp .env.example .env
```

```env
CH_HOST=127.0.0.1
CH_PORT=8123
CH_DATABASE=kawakiri_data
META_DB=kawakiri_meta
CH_USER=default
CH_PASSWORD=
```

`CH_DATABASE` stores imported and logical tables. `META_DB` stores profiles, inferred
groups, keys, joins, candidates, scores, and validation results. Use distinct names for
these databases.

## Verify the installation

```bash
kawakiri --help
pytest
```

The integration test requires ClickHouse and is skipped by default:

```bash
pytest --run-integration tests/integration/test_e2e_pipeline.py
```

Build or preview the documentation with the development dependencies installed:

```bash
mkdocs build --strict
mkdocs serve
```

## Run the complete pipeline

```bash
kawakiri run-all path/to/csv-folder --report certification-report.json
```

Equivalent command from the source tree:

```bash
python code/main.py run-all path/to/csv-folder --report certification-report.json
```

Use `--skip-sql-views` when only the certification artifacts are required.

See the [usage guide](usage.md) for the external-project CLI example and individual
pipeline stages.

## CSV behavior

The loader detects UTF BOMs, UTF-8, Windows-1252 and Latin-1 without silently dropping
invalid bytes. It also detects comma, semicolon, and tab delimiters. Temporal inference
is controlled by `INGESTION_SETTINGS` in `code/config/scoring.py` and currently accepts
the formats declared in `DATE_FORMATS` and `DATETIME_FORMATS`.
