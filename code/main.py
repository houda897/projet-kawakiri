import argparse

from core.clickhouse_manager import get_manager
from core.logger import get_logger
from core.meta import clear_metadata_table, ensure_meta_schema
from generation.sql_view_generator import SQLViewGenerator
from inference.adjacency import AdjacencyMatrixEngine
from inference.join_candidate import JoinEngine
from inference.primary_key import PrimaryKeyEngine
from inference.table_role import TableRoleEngine
from ingestion.csv_loader import CsvIngestionEngine
from modeling.candidate_builder import DecisionModelCandidateBuilder
from modeling.model_ranking import ModelRanking
from profiling.basic_profile import ProfileEngine
from reporting.certification_report import CertificationReportExporter
from semantic.semantic_engine import SemanticEngine
from stats.identifiability import IdentifiabilityEngine
from validation.aggregation_stability_validator import AggregationStabilityValidator
from validation.granularity_validator import GranularityValidator
from validation.model_certification import ModelCertificationEngine
from validation.semantic_homogeneity_validator import SemanticHomogeneityValidator
from validation.structural_validator import StructuralValidator

logger = get_logger(__name__)


def run_csv_ingestion(path: str, table: str | None) -> None:
    db = get_manager()
    engine = CsvIngestionEngine(db)

    result = engine.import_csv_to_clickhouse(
        csv_path=path,
        table_name=table,
    )

    logger.info(
        "Import terminé : %s lignes dans %s.%s",
        result["row_count"],
        result["target_database"],
        result["target_table"],
    )


def run_folder_ingestion(path: str) -> None:
    db = get_manager()
    engine = CsvIngestionEngine(db)

    results = engine.import_csv_folder_to_clickhouse(path)

    success_count = sum(1 for result in results if result["status"] == "success")
    failed_count = len(results) - success_count
    total_rows = sum(result["row_count"] for result in results)

    logger.info("Import dossier terminé : %s succès, %s échec(s)", success_count, failed_count)
    logger.info("Lignes importées : %s", total_rows)


def run_basic_profile() -> None:
    db = get_manager()
    engine = ProfileEngine(db)

    profiles = engine.profile_database()

    logger.info("Profilage terminé : %s colonnes profilées", len(profiles))


def run_identifiability() -> None:
    db = get_manager()
    engine = IdentifiabilityEngine(db)

    results = engine.compute_scores()
    engine.store_scores(results)


def run_pk_inference() -> None:
    db = get_manager()
    engine = PrimaryKeyEngine(db)

    candidates = engine.infer_candidates()
    engine.store_candidates(candidates)


def run_join(
    source_table: str,
    source_column: str,
    target_table: str,
    target_column: str,
) -> None:
    db = get_manager()

    pk_engine = PrimaryKeyEngine(db)
    primary_keys = pk_engine.load_candidates() or pk_engine.infer_candidates()
    join_engine = JoinEngine(db)

    result = join_engine.evaluate_join_by_target(
        source_table=source_table,
        source_column=source_column,
        target_table=target_table,
        target_column=target_column,
        primary_keys=primary_keys,
    )

    join_engine.print_result(result)


def run_join_inference() -> None:
    db = get_manager()

    primary_keys = PrimaryKeyEngine(db).load_candidates()
    if not primary_keys:
        raise RuntimeError("No primary-key candidates found. Run infer-pk first.")

    join_engine = JoinEngine(db)

    clear_metadata_table(db, "join_candidates")
    candidates = join_engine.evaluate_candidates(primary_keys)
    join_engine.store_candidates(candidates)


def run_adjacency() -> None:
    db = get_manager()

    join_engine = JoinEngine(db)
    adjacency_engine = AdjacencyMatrixEngine(db, semantic_engine=SemanticEngine())

    join_candidates = join_engine.load_candidates()
    edges = adjacency_engine.build_edges_from_join_candidates(join_candidates)
    matrix = adjacency_engine.build_matrix(edges, adjacency_engine.load_profiled_tables())

    adjacency_engine.store_edges(edges)
    adjacency_engine.print_matrix(matrix)
    adjacency_engine.print_binary_matrix(matrix)


def run_table_roles() -> None:
    db = get_manager()
    ensure_meta_schema(db)
    engine = TableRoleEngine(db)

    roles = engine.infer_roles()
    engine.store_roles(roles)
    engine.print_roles(roles)


def run_sql_view_generation() -> None:
    db = get_manager()
    engine = SQLViewGenerator(db)
    views = engine.create_views()
    engine.print_views(views)


def run_model_candidate_building() -> None:
    db = get_manager()
    ensure_meta_schema(db)

    builder = DecisionModelCandidateBuilder(db)
    candidates = builder.build_candidates()
    builder.store_candidates(candidates)
    builder.print_candidates(candidates)


def run_model_ranking() -> None:
    db = get_manager()
    ensure_meta_schema(db)

    builder = DecisionModelCandidateBuilder(db)
    candidates = builder.load_candidates()

    if not candidates:
        raise ValueError("No decision model candidates found. Run build-model-candidates first.")

    ranking = ModelRanking(db)
    scored_candidates = ranking.rank_and_store(candidates)
    ranking.print_ranked_models(scored_candidates)


def run_structural_validation() -> None:
    db = get_manager()
    ensure_meta_schema(db)
    validator = StructuralValidator(db)
    results = validator.validate_stored_candidates()
    validator.store_results(results)
    validator.print_results(results)


def run_granularity_validation() -> None:
    db = get_manager()
    ensure_meta_schema(db)
    validator = GranularityValidator(db)
    results = validator.validate_stored_candidates()
    validator.store_results(results)
    validator.print_results(results)


def run_semantic_homogeneity_validation() -> None:
    db = get_manager()
    ensure_meta_schema(db)
    roles = TableRoleEngine(db).load_roles()

    if not roles:
        raise ValueError("No table roles found. Run infer-table-roles first.")

    validator = SemanticHomogeneityValidator(db)
    results = validator.check_homogeneity(roles)
    validator.store_homogeneity(results)
    validator.print_homogeneity(results)


def run_aggregation_stability_validation() -> None:
    db = get_manager()
    ensure_meta_schema(db)
    validator = AggregationStabilityValidator(db)
    results = validator.validate_stored_candidates()
    validator.store_stability(results)
    validator.print_stability(results)


def run_model_certification() -> None:
    db = get_manager()
    ensure_meta_schema(db)
    engine = ModelCertificationEngine(db)
    results = engine.certify_stored_candidates()
    engine.store_results(results)
    engine.print_results(results)


def run_certification_report_export(path: str) -> None:
    db = get_manager()
    ensure_meta_schema(db)
    exporter = CertificationReportExporter(db)
    exporter.write_json(path)
    logger.info("Certification report exported: %s", path)


def run_all(path: str, report_path: str, skip_sql_views: bool) -> None:
    """
    Run the full available pipeline from CSV ingestion to certification report.
    """

    steps = [
        ("ingest-folder", lambda: run_folder_ingestion(path)),
        ("profile-basic", run_basic_profile),
        ("score-identifiability", run_identifiability),
        ("infer-pk", run_pk_inference),
        ("infer-joins", run_join_inference),
        ("build-adjacency", run_adjacency),
        ("infer-table-roles", run_table_roles),
        ("build-model-candidates", run_model_candidate_building),
        ("rank-models", run_model_ranking),
        ("validate-structure", run_structural_validation),
        ("validate-granularity", run_granularity_validation),
        ("validate-semantic-homogeneity", run_semantic_homogeneity_validation),
        ("validate-aggregation-stability", run_aggregation_stability_validation),
        ("certify-models", run_model_certification),
    ]

    for step_name, step in steps:
        logger.info("=== %s ===", step_name)
        step()

    if skip_sql_views:
        logger.info("=== generate-sql-views skipped ===")
    else:
        logger.info("=== generate-sql-views ===")
        try:
            run_sql_view_generation()
        except ValueError as exc:
            logger.warning("SQL view generation skipped: %s", exc)

    logger.info("=== export-certification-report ===")
    run_certification_report_export(report_path)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Kawakiri")
    subparsers = parser.add_subparsers(dest="command", required=True)

    ingest_parser = subparsers.add_parser(
        "ingest-csv",
        help="Import a CSV file into ClickHouse",
    )
    ingest_parser.add_argument("path", help="CSV file path")
    ingest_parser.add_argument("--table", help="Target table name")
    ingest_parser.set_defaults(handler=lambda args: run_csv_ingestion(args.path, args.table))

    folder_parser = subparsers.add_parser(
        "ingest-folder",
        help="Import all CSV files from a folder",
    )
    folder_parser.add_argument("path", help="Folder path")
    folder_parser.set_defaults(handler=lambda args: run_folder_ingestion(args.path))

    profile_parser = subparsers.add_parser(
        "profile-basic",
        help="Store basic and advanced column profiles in metadata",
    )
    profile_parser.set_defaults(handler=lambda args: run_basic_profile())

    identifiability_parser = subparsers.add_parser(
        "score-identifiability",
        help="Compute identifiability scores from advanced column statistics",
    )
    identifiability_parser.set_defaults(handler=lambda args: run_identifiability())

    pk_parser = subparsers.add_parser(
        "infer-pk",
        help="Infer primary-key candidates from profiles and identifiability scores",
    )
    pk_parser.set_defaults(handler=lambda args: run_pk_inference())

    join_parser = subparsers.add_parser(
        "evaluate-join",
        help="Evaluate one physical join between a source column and a target key",
    )
    join_parser.add_argument("--source-table", required=True)
    join_parser.add_argument("--source-column", required=True)
    join_parser.add_argument("--target-table", required=True)
    join_parser.add_argument("--target-column", required=True)
    join_parser.set_defaults(
        handler=lambda args: run_join(
            source_table=args.source_table,
            source_column=args.source_column,
            target_table=args.target_table,
            target_column=args.target_column,
        )
    )

    infer_joins_parser = subparsers.add_parser(
        "infer-joins",
        help="Infer join candidates from primary-key candidates",
    )
    infer_joins_parser.set_defaults(handler=lambda args: run_join_inference())

    adjacency_parser = subparsers.add_parser(
        "build-adjacency",
        help="Build the directed adjacency matrix from inferred joins",
    )
    adjacency_parser.set_defaults(handler=lambda args: run_adjacency())

    table_roles_parser = subparsers.add_parser(
        "infer-table-roles",
        help="Infer fact and dimension roles from the adjacency graph",
    )
    table_roles_parser.set_defaults(handler=lambda args: run_table_roles())

    sql_views_parser = subparsers.add_parser(
        "generate-sql-views",
        help="Generate SQL views for star schemas based on the inferred adjacency graph and table roles",
    )
    sql_views_parser.set_defaults(handler=lambda args: run_sql_view_generation())

    model_candidates_parser = subparsers.add_parser(
        "build-model-candidates",
        help="Build plausible decision model candidates from confirmed edges and inferred table roles",
    )
    model_candidates_parser.set_defaults(handler=lambda args: run_model_candidate_building())

    model_ranking_parser = subparsers.add_parser(
        "rank-models",
        help="Rank stored decision model candidates by parsimony",
    )
    model_ranking_parser.set_defaults(handler=lambda args: run_model_ranking())

    structural_validation_parser = subparsers.add_parser(
        "validate-structure",
        help="Validate stored decision model candidates with structural rules",
    )
    structural_validation_parser.set_defaults(handler=lambda args: run_structural_validation())

    granularity_validation_parser = subparsers.add_parser(
        "validate-granularity",
        help="Validate deterministic fact granularity for stored model candidates",
    )
    granularity_validation_parser.set_defaults(handler=lambda args: run_granularity_validation())

    semantic_homogeneity_parser = subparsers.add_parser(
        "validate-semantic-homogeneity",
        help="Validate semantic separation between fact measures and dimension attributes",
    )
    semantic_homogeneity_parser.set_defaults(
        handler=lambda args: run_semantic_homogeneity_validation()
    )

    aggregation_stability_parser = subparsers.add_parser(
        "validate-aggregation-stability",
        help="Validate that measures remain stable after aggregation through dimensions",
    )
    aggregation_stability_parser.set_defaults(
        handler=lambda args: run_aggregation_stability_validation()
    )

    model_certification_parser = subparsers.add_parser(
        "certify-models",
        help="Certify stored decision model candidates from ranking and validation results",
    )
    model_certification_parser.set_defaults(handler=lambda args: run_model_certification())

    report_parser = subparsers.add_parser(
        "export-certification-report",
        help="Export final model certification results as JSON",
    )
    report_parser.add_argument("path", help="Output JSON file path")
    report_parser.set_defaults(handler=lambda args: run_certification_report_export(args.path))

    run_all_parser = subparsers.add_parser(
        "run-all",
        help="Run the full available pipeline and export a certification report",
    )
    run_all_parser.add_argument("path", help="Folder path containing CSV files")
    run_all_parser.add_argument(
        "--report",
        default="report.json",
        help="Output JSON report path",
    )
    run_all_parser.add_argument(
        "--skip-sql-views",
        action="store_true",
        help="Skip SQL view generation",
    )
    run_all_parser.set_defaults(
        handler=lambda args: run_all(
            path=args.path,
            report_path=args.report,
            skip_sql_views=args.skip_sql_views,
        )
    )

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    args.handler(args)


if __name__ == "__main__":
    main()
