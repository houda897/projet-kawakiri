# Kawakiri Documentation

Kawakiri is a reverse-engineering tool for inferring decision models from raw
tabular data. It ingests CSV files, profiles the data, infers keys and joins,
builds candidate dimensional models, validates them, and exports a certification
report.

Use this documentation to:

- install and configure the project;
- understand the technical pipeline;
- run Kawakiri on your own CSV files;
- follow a concrete Climate/Ocean tutorial.

## Main Workflow

```text
CSV files
-> ingestion
-> profiling
-> key and join inference
-> model construction
-> validation
-> certification report
```

Start with the installation guide, then run the Climate/Ocean tutorial.
