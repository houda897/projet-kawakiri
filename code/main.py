from core.client import get_client
from core.schema import list_tables, list_columns
from profiling.entropy import compute_entropy_for_column
from profiling.dimension import infer_dimension_candidates
from validation.entropy_rule import validate_entropy_rule

def main():
    client = get_client()

    for table in list_tables(client):
        print(f"\n=== {table} ===")

        column_stats = []

        for col in list_columns(client, table):
            stats = compute_entropy_for_column(client, table, col)
            result = validate_entropy_rule(
                stats["entropy"],
                stats["rows"],
                stats["non_null_rows"],
                stats["distinct_count"],
            )

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

if __name__ == "__main__":
    main()