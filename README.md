# Kawakiri 

![Python Version](https://img.shields.io/badge/python-3.10%2B-blue.svg)
![ClickHouse](https://img.shields.io/badge/ClickHouse-Ready-yellow.svg)

**Kawakiri** is an Open Source *Structure Data Science* library developed in collaboration with the AMSE laboratory. It allows for the automatic inference of decisional models (Facts / Dimensions) from raw and undocumented data sources (CSV/SQL).

## Project Goals

1. **Reverse Engineering**: Discover the structure of unknown sources and massively ingest them into ClickHouse.
2. **Structure Data Science**: Implement statistical compliance tests (Iron Rules, Entropy) to certify a decisional model.
3. **Open Source**: Aim for a scientific publication in JOSS (Journal of Open Source Software).

## Architecture

The project relies on **ClickHouse**'s computing power to execute heavy statistical calculations (Entropy, Cardinality, Nullity Ratio) without saturating local memory.

The code is structured around object-oriented `Engines`:
- `CsvIngestionEngine`: Separator detection, type inference, and batch ingestion.
- `ProfileEngine` & `EntropyEngine`: Calculation of statistical metrics.
- `PrimaryKeyEngine` & `DimensionEngine`: Inference of decisional structures.
- `JoinEngine`: Physical testing engine for joins.

## Installation

Prerequisites: 
- Python 3.10+
- A ClickHouse instance running locally or remotely.

```bash
# Create a virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install the library (development mode)
pip install -e ".[dev]"
```

## Configuration

Create a `.env` file at the root (never commit it to Git, base it on `.env.example`):

```env
CH_HOST=127.0.0.1
CH_PORT=11123
CH_DATABASE=lab_db
CH_USER=lab_usr_admin
CH_PASSWORD=your_password
```

## Usage

Kawakiri can be used via its CLI:

```bash
python code/main.py --help

# Ingest a CSV
python code/main.py ingest-csv ./data/sales.csv --table sales

# Profile the database
python code/main.py profile-basic

# Infer primary keys
python code/main.py infer-pk
```
