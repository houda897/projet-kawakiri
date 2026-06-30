# Installation Guide

## Requirements

- Python 3.10 or later.
- A running ClickHouse instance.

## Install

From the project root:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

For development:

```bash
pip install -e ".[dev]"
```

## Configure ClickHouse

Create a `.env` file:

```env
CH_HOST=localhost
CH_PORT=8123
CH_DATABASE=your_database
CH_USER=your_user
CH_PASSWORD=your_password
```

## Run

```bash
kawakiri run-all path/to/csv-folder --report certification-report.json
```

Equivalent direct command:

```bash
python code/main.py run-all path/to/csv-folder --report certification-report.json
```
