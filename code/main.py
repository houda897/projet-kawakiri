import argparse

from core.logger import get_logger
from core.manager import get_manager
from inference.join_candidate import JoinEngine
from inference.primary_key import PrimaryKeyEngine
from ingestion.csv_loader import CsvIngestionEngine
from profiling.basic_profile import ProfileEngine
from stats.identifiability import IdentifiabilityEngine

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
    engine.print_scores(results)


def run_pk_inference() -> None:
    db = get_manager()
    engine = PrimaryKeyEngine(db)

    candidates = engine.infer_candidates()
    engine.store_candidates(candidates)
    engine.print_candidates(candidates)


def run_join(
    source_table: str,
    source_column: str,
    target_table: str,
    target_column: str,
) -> None:
    db = get_manager()

    primary_keys = PrimaryKeyEngine(db).infer_candidates()
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

    primary_keys = PrimaryKeyEngine(db).infer_candidates()
    join_engine = JoinEngine(db)

    candidates = join_engine.evaluate_candidates(primary_keys)
    join_engine.print_candidates(candidates)


def main() -> None:
    parser = argparse.ArgumentParser(description="Kawakiri")
    subparsers = parser.add_subparsers(dest="command", required=True)

    ingest_parser = subparsers.add_parser(
        "ingest-csv",
        help="Import a CSV file into ClickHouse",
    )
    ingest_parser.add_argument("path", help="CSV file path")
    ingest_parser.add_argument("--table", help="Target table name")

    folder_parser = subparsers.add_parser(
        "ingest-folder",
        help="Import all CSV files from a folder",
    )
    folder_parser.add_argument("path", help="Folder path")

    subparsers.add_parser(
        "profile-basic",
        help="Store basic and advanced column profiles in metadata",
    )

    subparsers.add_parser(
        "score-identifiability",
        help="Compute identifiability scores from advanced column statistics",
    )

    subparsers.add_parser(
        "infer-pk",
        help="Infer simple primary-key candidates from column profiles",
    )

    join_parser = subparsers.add_parser(
        "evaluate-join",
        help="Evaluate one physical join between a source column and a target key",
    )
    join_parser.add_argument("--source-table", required=True)
    join_parser.add_argument("--source-column", required=True)
    join_parser.add_argument("--target-table", required=True)
    join_parser.add_argument("--target-column", required=True)

    subparsers.add_parser(
        "infer-joins",
        help="Infer join candidates from primary-key candidates",
    )

    args = parser.parse_args()

    if args.command == "ingest-csv":
        run_csv_ingestion(args.path, args.table)

    elif args.command == "ingest-folder":
        run_folder_ingestion(args.path)

    elif args.command == "profile-basic":
        run_basic_profile()

    elif args.command == "score-identifiability":
        run_identifiability()

    elif args.command == "infer-pk":
        run_pk_inference()

    elif args.command == "evaluate-join":
        run_join(
            source_table=args.source_table,
            source_column=args.source_column,
            target_table=args.target_table,
            target_column=args.target_column,
        )

    elif args.command == "infer-joins":
        run_join_inference()


if __name__ == "__main__":
    main()
