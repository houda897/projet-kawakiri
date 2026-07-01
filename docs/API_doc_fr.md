# Référence de l'API Python

Cette page décrit les classes réellement utilisées par le pipeline en ligne de
commande. Kawakiri est principalement exécuté par la CLI, mais les moteurs peuvent être
appelés directement pour les tests ou une orchestration personnalisée.

Tous les moteurs accédant à ClickHouse reçoivent une instance de
`ClickHouseManager`.

## Socle et ingestion

### `core.clickhouse_manager.ClickHouseManager`

- `query(sql, parameters=None)` : exécute une requête et retourne le résultat du pilote.
- `command(sql, parameters=None)` : exécute une instruction sans jeu de résultats.
- `insert(table, data, column_names=None)` : insère un lot de lignes.
- `close_all()` : ferme les connexions créées par un traitement parallèle.

### `ingestion.csv_loader.CsvIngestionEngine`

- `import_csv_to_clickhouse(...)` : importe un fichier CSV.
- `import_csv_folder_to_clickhouse(...)` : importe tous les CSV d'un dossier.
- `detect_encoding(path)` : détecte un encodage supporté sans ignorer les octets invalides.
- `detect_delimiter(path)` : détecte la virgule, le point-virgule ou la tabulation.
- `infer_column_types(headers, sample_rows)` : infère les types ClickHouse.
- `insert_csv_rows(...)` : nettoie, convertit et insère les lignes par lots.

## Profilage et statistiques

### `profiling.basic_profile.ProfileEngine`

- `profile_database(table_names=None)` : profile les tables physiques ou logiques.
- `compute_basic_profile_for_column(...)` : calcule cardinalité, taux de nullité,
  unicité et extrema.
- `insert_column_profiles(profiles)` : enregistre les profils.

### `stats.stats_computing.compute_column_stats`

Calcule et stocke l'entropie normalisée, le coefficient de variation et l'asymétrie
d'une colonne.

### `stats.identifiability.IdentifiabilityEngine`

- `compute_scores()` : combine unicité, entropie et complétude.
- `store_scores(scores)` : persiste les scores d'identifiabilité.

### `stats.functional_dependency`

- `check_column_dependency(...)` : vérifie une dépendance `D -> c`.
- `check_functional_dependency(...)` : vérifie qu'un candidat simple ou composé
  identifie chaque ligne de manière unique.

## Reconstruction et inférence

### `inference.functional_group_builder.FunctionalGroupBuilder`

- `build_groups()` : construit les groupes de toutes les tables sources.
- `build_dependency_groups_for_table(...)` : génère les dépendances simples et composées.
- `expand_groups_with_unassigned_columns(...)` : calcule la fermeture fonctionnelle
  itérative des groupes retenus.
- `select_non_overlapping_groups(...)` : sélectionne des groupes sans chevauchement.
- `build_singleton_groups(...)` : conserve explicitement les colonnes non rattachées.
- `store_groups(groups)` / `load_groups()` : écrit ou relit les preuves de grouping.

`FunctionalColumnGroup` expose les déterminants, les dépendants, la confiance, le score
du groupe et la propriété `all_columns`.

### `inference.source_structure.SourceStructureAnalyzer`

- `load_structures()` : charge les clés et relations préliminaires des sources.
- `select_entity_keys(keys, joins)` : choisit la clé possédée par chaque table à partir
  des références entrantes et sortantes.
- `select_relationships(...)` : conserve les relations ciblant les clés exactes retenues.

### `modeling.fact_dimension_builder.FactDimensionBuilder`

- `build_plans()` : classe les groupes prouvés et construit les plans logiques.
- `build_dimension_tables(...)` : transforme les groupes descriptifs en dimensions sans
  ajouter de colonnes extérieures au groupe.
- `build_fact_tables(...)` : conserve grain, clés et mesures des sources événementielles.

### `modeling.logical_table_builder.LogicalTableBuilder`

- `build_logical_tables()` : construit et matérialise les tables logiques.
- `materialize(logical_table)` : crée la table ClickHouse correspondante.
- `load_logical_tables()` : recharge les définitions matérialisées.

### `inference.primary_key.PrimaryKeyEngine`

- `infer_candidates(...)` : recherche les clés exactes simples, composées et logiques
  dans les périmètres d'analyse `SOURCE` ou `LOGICAL`.
- `store_candidates(candidates)` / `load_candidates()` : persiste ou relit les clés.

### `inference.join_candidate.JoinEngine`

- `evaluate_join_to_primary_key(...)` : évalue une jointure physique.
- `evaluate_candidates(primary_keys, min_success_ratio=0.95, ...)` : teste les colonnes
  sources compatibles contre les clés cibles.
- `store_candidates(candidates)` / `load_candidates()` : persiste les jointures retenues.

### `inference.adjacency.AdjacencyMatrixEngine`

- `build_edges_from_join_candidates()` : transforme les jointures en arêtes orientées.
- `build_matrix(edges)` : construit la matrice d'adjacence.
- `store_edges(edges)` : persiste le graphe.

### `inference.table_role.TableRoleEngine`

- `infer_roles()` : classe les tables logiques à partir des plans et du graphe.
- `classify_table(...)` : retourne `FACT`, `DIMENSION`, `ISOLATED` ou `UNKNOWN`.
- `store_roles(roles)` / `load_roles()` : persiste ou recharge les rôles.

## Modèles candidats

### `modeling.candidate_builder.DecisionModelCandidateBuilder`

- `build_candidates()` : construit les topologies compatibles.
- `build_star_candidates(...)`, `build_snowflake_candidates(...)` et
  `build_constellation_candidates(...)` : construisent chaque famille de modèles.
- `store_candidates(candidates)` / `load_candidates()` : persiste les modèles.

### `modeling.model_ranking.ModelRanking`

- `rank_and_store(candidates=None)` : calcule et normalise les scores de parcimonie.
- `_calculate_score(candidate)` : calcule le score brut d'un candidat.

## Validation et certification

### `validation.structural_validator.StructuralValidator`

- `validate_stored_candidates()` : vérifie topologie et intégrité référentielle.

### `validation.granularity_validator.GranularityValidator`

- `validate_stored_candidates()` : vérifie l'unicité du grain des faits.
- `build_fact_grain(...)` : combine clés dimensionnelles et grain transactionnel.

### `validation.semantic_homogeneity_validator.SemanticHomogeneityValidator`

- `check_homogeneity(roles)` : contrôle la séparation faits/dimensions.

### `validation.aggregation_stability_validator.AggregationStabilityValidator`

- `validate_stored_candidates()` : compare les agrégats avant et après jointure.
- `select_additive_measure(...)` : choisit une mesure numérique non identifiante.

### `validation.model_certification.ModelCertificationEngine`

- `certify_stored_candidates()` : combine classement et validations.
- `certify_candidate(...)` : produit le statut, le score et les anomalies d'un modèle.

## Génération et rapport

### `generation.sql_view_generator.SQLViewGenerator`

- `generate_views()` : construit les définitions SQL du meilleur modèle certifié.
- `create_views()` : crée les vues dans ClickHouse.

### `reporting.certification_report.CertificationReportExporter`

- `build_report()` : construit le rapport complet.
- `write_json(path)` : écrit le rapport JSON.
- `write_mermaid_schema(path, report=None)` : écrit le schéma Mermaid.
- `build_best_model_schema(report=None)` : produit une représentation textuelle lisible.

## Limites de l'API

Les moteurs lèvent généralement `ValueError` ou `RuntimeError` lorsqu'une étape
précédente n'a produit aucune métadonnée. Un statut certifié atteste le respect des
règles implémentées ; il ne garantit pas à lui seul la signification métier ni
l'unicité du modèle inféré.
