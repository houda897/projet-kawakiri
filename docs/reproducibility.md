# Reproducibility

This guide describes how to reproduce Kawakiri's tests and bundled end-to-end example.

## Record the environment

For a reproducible run, record:

- the Kawakiri Git commit or release tag;
- Python and ClickHouse versions;
- the operating system;
- the input dataset version or DOI;
- the `.env` database names, excluding credentials;
- the exact command and configuration used.

The README pins the Docker example to ClickHouse 25.8 LTS. A different ClickHouse
version may produce different query plans, while the validation semantics should remain
unchanged.

## Create an isolated installation

```bash
git clone https://github.com/houda897/projet-kawakiri.git
cd projet-kawakiri
chmod +x install.sh
./install.sh --dev
source .venv/bin/activate
```

Use dedicated ClickHouse databases for the run:

```dotenv
CH_DATABASE=kawakiri_reproduction
META_DB=kawakiri_reproduction_meta
```

## Run automated checks

```bash
ruff format --check code tests examples
ruff check code tests examples
pytest -m "not integration" --cov=code --cov-report=term-missing
mkdocs build --strict
```

Run the ClickHouse integration test explicitly:

```bash
pytest --run-integration tests/integration/test_e2e_pipeline.py
```

## Reproduce the bundled model

```bash
kawakiri run-all code/data --report reproduction-report.json
```

Expected artifacts:

- `reproduction-report.json` with candidates, validations, coverage, and certification;
- `reproduction-report.mmd` with the inferred entity-relationship representation;
- SQL views in `CH_DATABASE` when a model is certified.

Do not compare generated timestamps or database-specific identifiers byte for byte.
Compare inferred tables, relationships, validation statuses, issue codes, and model
coverage instead.

## Research datasets

Record the immutable DOI or checksum of every external dataset. Do not commit private
or redistribution-restricted data to the repository. The integration dataset referenced
by the README is archived separately on Zenodo.
