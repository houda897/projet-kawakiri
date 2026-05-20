import argparse
from core.logger import get_logger
from core.clickhouse_manager import get_manager
from inference.join_candidate import JoinEngine
from inference.primary_key import PrimaryKeyEngine
from ingestion.csv_loader import CsvIngestionEngine
from profiling.basic_profile import ProfileEngine
from stats.identifiability import IdentifiabilityEngine
from stats.functional_dependency import validate_dependency
from inference.composite_key import CompositeKeyEngine

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
    pk_engine = PrimaryKeyEngine(db)
    composite_engine = CompositeKeyEngine(db)

    all_candidates = pk_engine.infer_candidates(threshold=0.0)
    for c in all_candidates:
        print(f"DB : {c.database_name} | Table : {c.table_name} | Column : {c.column_name} | Confidence : {c.confidence}")

    simple_candidates = [c for c in all_candidates if c.confidence >= 0.99]
    print(f"\n--- *** --- Colonnes > 0.99 confidence : {len(simple_candidates)} --- *** ---\n")

    final_candidates = validate_dependency(simple_candidates)
    print(f"\n--- *** --- Colonnes validées comme PK simples : {len(final_candidates)} --- *** ---")
    print(f"--- ***--- Colonnes écartées comme PK simples : {len(simple_candidates) - len(final_candidates)} --- *** ---\n")

    table_with_simple_pk = set(c.table_name for c in final_candidates)

    all_tables = set(c.table_name for c in all_candidates)
    tables_without_pk = list(all_tables - table_with_simple_pk)
    for t in tables_without_pk:
        print(f"--- ***--- Table sans PK simple : {t} --- ***---")

    composite_candidates = []
    final_composite_candidates = []
    if tables_without_pk:
        composite_candidates = composite_engine.generate_composite_candidates(
            all_columns=all_candidates,
            tables_without_pk=tables_without_pk,
            max_size=3,
        )
        print (f"--- ***--- Candidats composites générés : {len(composite_candidates)} --- ***---\n")
        for c in composite_candidates:
            print(f"DB : {c.database_name} | Table : {c.table_name} | Columns : {c.column_name} | Confidence : {c.confidence} | col_type : {type(c.column_name)}")

        if composite_candidates :
            final_composite_candidates = validate_dependency(composite_candidates)

    print(f"\n--- *** --- Final candidats simples : {len(final_candidates)} --- *** ---")
    final_candidates += final_composite_candidates
    print(f"--- *** --- Final candidats ajout composites : {len(final_candidates)} --- *** ---\n")

    pk_engine.store_candidates(final_candidates)
    print("\n--- vvv ---")
    pk_engine.print_candidates(final_candidates)
    print("--- ^^^ ---")


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
        help="Infer primary-key candidates from profiles and identifiability scores",
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