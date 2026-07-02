# Kawakiri Documentation

Kawakiri reconstructs candidate dimensional models from undocumented CSV data. The
software imports the sources into ClickHouse, measures their structure, reconstructs
functional column groups, materializes logical tables, and then infers keys, joins,
table roles, and dimensional-model candidates.

The result is not a semantic truth inferred from column names. Every accepted model is
accompanied by inspectable evidence and validation results. A domain expert must still
confirm that the selected candidate matches the intended business interpretation.

## Main workflow

```text
CSV sources
  -> ingestion and profiling
  -> functional groups
  -> logical facts and dimensions
  -> keys and joins
  -> adjacency graph and roles
  -> candidate models
  -> validation and certification
  -> SQL views + JSON report + Mermaid schema
```

## Start here

1. Follow the [installation guide](installation.md).
2. Follow the [usage guide](usage.md) and run the bundled example.
3. Read the [technical architecture](architecture.md).
4. Run the [Climate/Ocean tutorial](tutorials/climate-ocean.md).
5. Consult the [technical reference](technical-reference.md) or its
   [French version](technical-reference-fr.md).
6. Use the [reproducibility guide](reproducibility.md) for scientific runs.

Kawakiri is used through its command-line interface. The technical reference documents
implementation components for tests and contributors.

!!! warning "Alpha software"
    A `VALID` certification means that a candidate satisfies the rules currently
    implemented by Kawakiri. It does not prove business correctness, uniqueness of the
    interpretation, or suitability for production without review.
