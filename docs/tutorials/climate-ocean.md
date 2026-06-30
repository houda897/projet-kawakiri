# Climate/Ocean Tutorial

This tutorial runs Kawakiri on the example files stored in
`code/climat_ocean_dataset/data`.

## Dataset

The folder contains independent public-data extracts covering:

- annual global temperature;
- monthly global temperature;
- atmospheric CO2 indicators and their codebook;
- sea-level observations.

These files are useful for testing ingestion, profiling, physical measures, temporal
grain, and ambiguous relationships. They are not guaranteed to describe one coherent
business process, so isolated tables or several competing candidates are legitimate
outcomes.

## Run the pipeline

Activate the project environment and verify the ClickHouse configuration first:

```bash
source .venv/bin/activate
kawakiri run-all code/climat_ocean_dataset/data --report climate-ocean-report.json
```

From a source checkout without the installed script:

```bash
python code/main.py run-all \
  code/climat_ocean_dataset/data \
  --report climate-ocean-report.json
```

Use `--skip-sql-views` when you only want to inspect the inferred candidates and their
validation results.

## Follow the reconstruction

The logs expose each stage:

1. imported files and row counts;
2. raw column profiles and statistical evidence;
3. functional groups and unassigned singletons;
4. materialized logical facts and dimensions;
5. inferred primary keys and joins;
6. adjacency matrix and table roles;
7. candidate models, ranking, and validation results;
8. final certification and generated artifacts.

Physical observations such as temperature, CO2, and sea level should be evaluated as
measure candidates from their type and distribution. Identifiers, temporal columns,
and repeated observation coordinates can contribute to the grain. A table with no
confirmed relationship remains isolated rather than being forced into the model.

## Inspect the outputs

The command writes:

- `climate-ocean-report.json`: certifications, issues, coverage, and excluded tables;
- `climate-ocean-report.mmd`: Mermaid representation of the selected model;
- SQL views in `CH_DATABASE` when a certified model exists.

Render the Mermaid file with a Mermaid-compatible editor or documentation renderer.
When no model is certified, inspect `models`, `issues`, and `excluded_tables` in the JSON
report. That outcome means the available files did not satisfy the implemented rules;
it is preferable to fabricating a relationship unsupported by the data.

## Reproducible step-by-step run

```bash
kawakiri ingest-folder code/climat_ocean_dataset/data
kawakiri profile-basic
kawakiri score-identifiability
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
kawakiri export-certification-report climate-ocean-report.json
```

Each command depends on metadata produced by the preceding stages.
