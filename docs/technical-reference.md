# Kawakiri Technical Reference

This page documents the engine classes and methods used internally by the command-line
pipeline. It is intended for tests, maintenance, and project contributors.

All engines that access ClickHouse receive a `ClickHouseManager` instance.

## Core and ingestion

### `core.clickhouse_manager.ClickHouseManager`

Central thread-aware ClickHouse access point.

- `query(sql, parameters=None)`: execute a query and return the driver result.
- `command(sql, parameters=None)`: execute a statement without a result set.
- `insert(table, data, column_names=None)`: insert a batch of rows.
- `close_all()`: close clients created by the current parallel workload.

### `ingestion.csv_loader.CsvIngestionEngine`

- `import_csv_to_clickhouse(csv_path, table_name=None, ...)`: import one CSV file.
- `import_csv_folder_to_clickhouse(folder_path, ...)`: import every CSV in a folder.
- `detect_encoding(path)`: select a supported encoding using strict decoding.
- `detect_delimiter(path)`: detect comma, semicolon, or tab separation.
- `infer_column_types(headers, sample_rows)`: infer ClickHouse types from a sample.
- `insert_csv_rows(...)`: clean, convert, batch, and insert data rows.

## Profiling and statistics

### `profiling.basic_profile.ProfileEngine`

- `profile_database(table_names=None)`: profile physical or selected logical tables.
- `compute_basic_profile_for_column(table, column, type)`: compute row count,
  distinct count, null ratio, uniqueness, and extrema.
- `insert_column_profiles(profiles)`: persist profiles in metadata.

### `stats.stats_computing.compute_column_stats`

Computes and stores entropy ratio, coefficient of variation, and skewness evidence for
one column.

### `stats.identifiability.IdentifiabilityEngine`

- `compute_scores()`: combine uniqueness, entropy, and completeness.
- `store_scores(scores)`: persist identifiability evidence.

### `stats.functional_dependency`

- `check_column_dependency(database, table, determinant_columns, dependent_column,
  db_manager)`: test `D -> c` by searching determinant values associated with several
  dependent values.
- `check_functional_dependency(database, table, pk_candidate, db_manager)`: test
  whether a simple or composite candidate uniquely identifies rows.

## Reconstruction and inference

### `inference.functional_group_builder.FunctionalGroupBuilder`

- `build_groups()`: construct groups for all profiled source tables.
- `build_dependency_groups_for_table(table_name, profiles)`: create simple and
  composite FD candidates for one table.
- `expand_groups_with_unassigned_columns(...)`: compute the iterative functional
  closure of selected groups.
- `select_non_overlapping_groups(...)`: choose scored groups without sharing columns.
- `build_singleton_groups(...)`: retain unassigned columns explicitly.
- `store_groups(groups)` / `load_groups()`: persist or reload grouping evidence.

`FunctionalColumnGroup` exposes `determinant_columns`, `dependent_columns`,
`confidence`, `group_score`, and the combined `all_columns` property.

### `inference.source_structure.SourceStructureAnalyzer`

- `load_structures()`: load preliminary source keys and relationships.
- `select_entity_keys(keys, joins)`: prefer the key owned by each source from incoming
  and outgoing reference evidence.
- `select_relationships(joins, entity_keys)`: retain relationships targeting the
  selected exact entity keys.

### `modeling.fact_dimension_builder.FactDimensionBuilder`

- `build_plans()`: classify proven groups and construct logical table plans.
- `build_dimension_tables(groups, profiles)`: convert suitable functional groups into
  dimension candidates without adding external columns.
- `build_fact_tables(groups, profiles, dimensions)`: retain grain, inferred keys, and
  measure candidates for transactional sources.

### `modeling.logical_table_builder.LogicalTableBuilder`

- `build_logical_tables()`: build plans, materialize logical tables, and store metadata.
- `materialize(logical_table)`: create a ClickHouse table from the selected source columns.
- `load_logical_tables()`: reload materialized logical-table definitions.

### `inference.primary_key.PrimaryKeyEngine`

- `infer_candidates(...)`: infer exact simple, composite, and logical determinant
  candidates for either the `SOURCE` or `LOGICAL` analysis scope.
- `store_candidates(candidates)` / `load_candidates()`: persist or reload PK evidence.

### `inference.join_candidate.JoinEngine`

- `evaluate_join_to_primary_key(...)`: calculate physical join evidence for one pair.
- `evaluate_candidates(primary_keys, min_success_ratio=0.95, ...)`: evaluate eligible
  source columns against inferred target keys.
- `store_candidates(candidates)` / `load_candidates()`: persist accepted joins.

### `inference.adjacency.AdjacencyMatrixEngine`

- `build_edges_from_join_candidates()`: convert accepted joins into directed edges.
- `build_matrix(edges)`: construct the adjacency matrix.
- `store_edges(edges)`: persist graph evidence.

### `inference.table_role.TableRoleEngine`

- `infer_roles()`: classify logical tables using logical plans and graph evidence.
- `classify_table(...)`: return `FACT`, `DIMENSION`, `ISOLATED`, or `UNKNOWN`.
- `store_roles(roles)` / `load_roles()`: persist or reload roles.

## Candidate models

### `modeling.candidate_builder.DecisionModelCandidateBuilder`

- `build_candidates()`: build all supported candidate topologies.
- `build_star_candidates(...)`, `build_snowflake_candidates(...)`, and
  `build_constellation_candidates(...)`: construct each model family.
- `store_candidates(candidates)` / `load_candidates()`: persist model definitions.

### `modeling.model_ranking.ModelRanking`

- `rank_and_store(candidates=None)`: score candidates and normalize their ranking.
- `_calculate_score(candidate)`: calculate the raw parsimony score.

## Validation and certification

### `validation.structural_validator.StructuralValidator`

- `validate_stored_candidates()`: run topology and referential checks.

### `validation.granularity_validator.GranularityValidator`

- `validate_stored_candidates()`: verify that each fact grain is deterministic.
- `build_fact_grain(candidate, fact_table)`: combine dimensional keys and transactional
  grain evidence.

### `validation.semantic_homogeneity_validator.SemanticHomogeneityValidator`

- `check_homogeneity(roles)`: validate fact/dimension separation.

### `validation.aggregation_stability_validator.AggregationStabilityValidator`

- `validate_stored_candidates()`: compare fine and post-join aggregations.
- `select_additive_measure(...)`: select a numeric measure that is not a key or a flat
  technical counter.

### `validation.model_certification.ModelCertificationEngine`

- `certify_stored_candidates()`: combine ranking and validation results.
- `certify_candidate(...)`: produce a status, score, and issue list for one model.

## Generation and reporting

### `generation.sql_view_generator.SQLViewGenerator`

- `generate_views()`: build view definitions from the best certified model.
- `create_views()`: create the generated views in ClickHouse.

### `reporting.certification_report.CertificationReportExporter`

- `build_report()`: build the complete certification payload.
- `write_json(path)`: write the JSON report.
- `write_mermaid_schema(path, report=None)`: write the Mermaid ER schema.
- `build_best_model_schema(report=None)`: return a readable text representation.

## Errors and guarantees

Most engines raise `ValueError` or `RuntimeError` when a required previous stage has no
metadata. A certification status describes the current implementation's checks; it is
not a guarantee of business meaning or uniqueness of the inferred interpretation.
