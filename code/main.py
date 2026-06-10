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
from semantic.semantic_engine import SemanticEngine
from stats.identifiability import IdentifiabilityEngine
from validation.granularity_validator import GranularityValidator
from validation.model_certification import ModelCertificationEngine
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
    matrix = adjacency_engine.build_matrix(edges)

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
        raise ValueError(
            "No decision model candidates found. Run build-model-candidates first."
        )

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


def run_model_certification() -> None:
    db = get_manager()
    ensure_meta_schema(db)
    engine = ModelCertificationEngine(db)
    results = engine.certify_stored_candidates()
    engine.store_results(results)
    engine.print_results(results)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Kawakiri")
    subparsers = parser.add_subparsers(dest="command", required=True)

    ingest_parser = subparsers.add_parser(
        "ingest-csv",
        help="Import a CSV file into ClickHouse",
    )
    ingest_parser.add_argument("path", help="CSV file path")
    ingest_parser.add_argument("--table", help="Target table name")
    ingest_parser.set_defaults(
        handler=lambda args: run_csv_ingestion(args.path, args.table)
    )

    folder_parser = subparsers.add_parser(
        "ingest-folder",
        help="Import all CSV files from a folder",
    )
    folder_parser.add_argument("path", help="Folder path")
    folder_parser.set_defaults(
        handler=lambda args: run_folder_ingestion(args.path)
    )

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
    model_candidates_parser.set_defaults(
        handler=lambda args: run_model_candidate_building()
    )

    model_ranking_parser = subparsers.add_parser(
        "rank-models",
        help="Rank stored decision model candidates by parsimony",
    )
    model_ranking_parser.set_defaults(handler=lambda args: run_model_ranking())

    structural_validation_parser = subparsers.add_parser(
        "validate-structure",
        help="Validate stored decision model candidates with structural rules",
    )
    structural_validation_parser.set_defaults(
        handler=lambda args: run_structural_validation()
    )

    granularity_validation_parser = subparsers.add_parser(
        "validate-granularity",
        help="Validate deterministic fact granularity for stored model candidates",
    )
    granularity_validation_parser.set_defaults(
        handler=lambda args: run_granularity_validation()
    )

    model_certification_parser = subparsers.add_parser(
        "certify-models",
        help="Certify stored decision model candidates from ranking and validation results",
    )
    model_certification_parser.set_defaults(
        handler=lambda args: run_model_certification()
    )

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    args.handler(args)


if __name__ == "__main__":
    main()
