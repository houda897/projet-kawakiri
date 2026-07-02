# Contributing to Kawakiri

Thank you for contributing to Kawakiri. The project is research-oriented, so
contributions should keep the code simple, reproducible, and easy to explain.

## Development Setup

Follow the installation and configuration instructions in the `README.rst`, then install
the optional development dependencies:

```bash
./install.sh --dev
```

On Windows, use `install.bat --dev`. Manual installation with
`python -m pip install -e ".[dev]"` remains supported.

Do not commit `.env`, generated reports, local datasets, or cache files.

## Branch Naming

Use short, explicit branch names:

```text
feat/<feature-name>
fix/<bug-name>
docs/<documentation-change>
chore/<maintenance-change>
refactor/<refactor-name>
```

Examples:

```text
feat/final-certification-flow
docs/update-project-documentation
chore/code-quality-cleanup
```

## Code Style

Before opening a pull request, run:

```bash
ruff check code tests examples
ruff format --check code tests examples
pytest -q
```

To apply formatting:

```bash
ruff format code tests examples
```

The project favors:

- explicit imports instead of `import *`;
- small engine classes with one clear responsibility;
- ClickHouse metadata tables for reusable pipeline results;
- simple code over unnecessary abstraction;
- loggers instead of `print()` in project code.

## Pipeline Checks

For a full local run, provide your own folder of CSV files:

```bash
kawakiri run-all path/to/csv-folder --report report.json
```

If SQL views are not needed:

```bash
kawakiri run-all path/to/csv-folder --report report.json --skip-sql-views
```

## Pull Requests

Each pull request should include:

- a short summary of the change;
- the tests or commands that were run;
- any known limitation or follow-up.

User-visible changes should also be added to the `Unreleased` section of
`CHANGELOG.md`.

Keep pull requests focused. Documentation, validation logic, SQL generation, and
packaging changes should ideally be separated when they are large.
