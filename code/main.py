import argparse

from core.client import get_client
from core.logger import get_logger
from ingestion.csv_loader import CsvIngestionEngine
from inference.join_candidate import JoinEngine
from inference.primary_key import PrimaryKeyEngine
from profiling.basic_profile import ProfileEngine

logger = get_logger(__name__)


def run_csv_ingestion(path: str, table: str | None) -> None:
    client = get_client()
    engine = CsvIngestionEngine(client)
    result = engine.import_csv_to_clickhouse(path, table_name=table)

    logger.info(
        f"Import terminé : {result['row_count']} lignes dans "
        f"{result['target_database']}.{result['target_table']}"
    )


def run_folder_ingestion(path: str) -> None:
    client = get_client()
    engine = CsvIngestionEngine(client)
    results = engine.import_csv_folder_to_clickhouse(path)

    success_count = sum(1 for result in results if result["status"] == "success")
    failed_count = len(results) - success_count
    total_rows = sum(result["row_count"] for result in results)

    logger.info(f"Import dossier terminé : {success_count} succès, {failed_count} échec(s)")
    logger.info(f"Lignes importées : {total_rows}")


def run_basic_profile() -> None:
    client = get_client()
    engine = ProfileEngine(client)
    profiles = engine.profile_database()

    logger.info(f"Profilage terminé : {len(profiles)} colonnes profilées")


def run_pk_inference() -> None:
    client = get_client()
    engine = PrimaryKeyEngine(client)
    candidates = engine.infer_candidates()
    engine.print_candidates(candidates)


def run_join(
    source_table: str,
    source_column: str,
    target_table: str,
    target_column: str,
) -> None:
    client = get_client()

    primary_keys = PrimaryKeyEngine(client).infer_candidates()
    join_engine = JoinEngine(client)

    result = join_engine.evaluate_join_by_target(
        source_table=source_table,
        source_column=source_column,
        target_table=target_table,
        target_column=target_column,
        primary_keys=primary_keys,
    )

    JoinEngine.print_result(result)


def run_join_inference() -> None:
    client = get_client()

    primary_keys = PrimaryKeyEngine(client).infer_candidates()
    join_engine = JoinEngine(client)
    candidates = join_engine.evaluate_candidates(primary_keys)

    JoinEngine.print_candidates(candidates)


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
        help="Store basic column profiles in lab_meta",
    )
    subparsers.add_parser(
        "infer-pk",
        help="Infer simple primary-key candidates from column profiles",
    )
    subparsers.add_parser(
        "infer-joins",
        help="Infer join candidates from primary-key candidates",
    )

    join_parser = subparsers.add_parser(
        "evaluate-join",
        help="Evaluate join between source and target columns",
    )
    join_parser.add_argument("--source-table", required=True)
    join_parser.add_argument("--source-column", required=True)
    join_parser.add_argument("--target-table", required=True)
    join_parser.add_argument("--target-column", required=True)

    args = parser.parse_args()

    if args.command == "ingest-csv":
        run_csv_ingestion(args.path, args.table)
    elif args.command == "ingest-folder":
        run_folder_ingestion(args.path)
    elif args.command == "profile-basic":
        run_basic_profile()
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
