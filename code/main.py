import argparse

from core.client import get_client
from ingestion.csv_loader import import_csv_folder_to_clickhouse, import_csv_to_clickhouse
from inference.primary_key import infer_primary_key_candidates, print_primary_key_candidates
from profiling.basic_profile import profile_database


def run_csv_ingestion(path: str, table: str | None) -> None:
    client = get_client()
    result = import_csv_to_clickhouse(client, path, table_name=table)

    print(
        f"Import terminé : {result['row_count']} lignes dans "
        f"{result['target_database']}.{result['target_table']}"
    )


def run_folder_ingestion(path: str) -> None:
    client = get_client()
    results = import_csv_folder_to_clickhouse(client, path)

    success_count = sum(1 for result in results if result["status"] == "success")
    failed_count = len(results) - success_count
    total_rows = sum(result["row_count"] for result in results)

    print(f"Import dossier terminé : {success_count} succès, {failed_count} échec(s)")
    print(f"Lignes importées : {total_rows}")


def run_basic_profile() -> None:
    client = get_client()
    profiles = profile_database(client)

    print(f"Profilage terminé : {len(profiles)} colonnes profilées")


def run_pk_inference() -> None:
    client = get_client()
    candidates = infer_primary_key_candidates(client)
    print_primary_key_candidates(candidates)


def main() -> None:
    parser = argparse.ArgumentParser(description="Kawakiri")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser(
        "infer-pk",
        help="Infer simple primary-key candidates from column profiles",
    )

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

    args = parser.parse_args()

    if args.command == "ingest-csv":
        run_csv_ingestion(args.path, args.table)
    elif args.command == "ingest-folder":
        run_folder_ingestion(args.path)
    elif args.command == "profile-basic":
        run_basic_profile()
    elif args.command == "infer-pk":
        run_pk_inference()


if __name__ == "__main__":
    main()
