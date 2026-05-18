import argparse

from core.client import get_client
from core.schema import list_columns, list_tables
from ingestion.csv_loader import import_csv_to_clickhouse
from profiling.basic_profile import profile_database
from profiling.dimension import infer_dimension_candidates
from profiling.entropy import compute_entropy_for_column
from validation.entropy_rule import validate_entropy_rule


def run_entropy_pipeline() -> None:
    client = get_client()


    dict = get_table_stats("EuroStat","Effets_de_la_pollution_atmosphérique_sur_la_santé")
    #print(dict)

    obs_value = dict['obs_value']
    print('obs_value :\n', obs_value)

    obs_value_entropy = dict['obs_value']['entropy']
    print('obs_value_entropy : \n', obs_value_entropy)

            column_stats.append({**stats, **result})

            print(
                f"{col.name}: "
                f"H_ratio={result['entropy_ratio']} | "
                f"U_ratio={result['uniqueness_ratio']} | "
                f"C_ratio={result['completeness_ratio']} | "
                f"valid={result['is_valid_dimension_key']}"
            )

        dimension_candidates = infer_dimension_candidates(table, column_stats)

        if dimension_candidates:
            print("DIMENSIONS:")
            for candidate in dimension_candidates:
                keys = ", ".join(candidate["key_columns"])
                attrs = ", ".join(candidate["attribute_columns"]) if candidate["attribute_columns"] else "-"
                print(
                    f"  {candidate['table']}: key={keys} | attrs={attrs} | "
                    f"confidence={candidate['confidence']}"
                )
        else:
            print("DIMENSIONS: none")


def run_basic_profile() -> None:
    client = get_client()
    profiles = profile_database(client)
    print(f"Basic profile stored for {len(profiles)} columns")


def run_csv_ingestion(path: str, table: str | None) -> None:
    client = get_client()
    result = import_csv_to_clickhouse(client, path, table_name=table)

    print(
        f"Import terminé : {result['row_count']} lignes dans "
        f"{result['target_database']}.{result['target_table']}"
    )



def main() -> None:
    parser = argparse.ArgumentParser(description="Kawakiri inference pipeline")
    subparsers = parser.add_subparsers(dest="command")

    subparsers.add_parser("features", help="Show available features")
    subparsers.add_parser("entropy", help="Run entropy and dimension candidate pipeline")
    subparsers.add_parser("profile-basic", help="Store basic column profiles in lab_meta")

    ingest_parser = subparsers.add_parser("ingest-csv", help="Import a CSV file into ClickHouse")
    ingest_parser.add_argument("path", help="CSV file path")
    ingest_parser.add_argument("--table", help="Target table name")

    args = parser.parse_args()


    if args.command == "ingest-csv":
        run_csv_ingestion(args.path, args.table)
        return

    if args.command == "profile-basic":
        run_basic_profile()
        return

    if args.command == "entropy":
        run_entropy_pipeline()
        return


if __name__ == "__main__":
    main()
