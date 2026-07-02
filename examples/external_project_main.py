"""Call the installed Kawakiri CLI from another Python project."""

from __future__ import annotations

import argparse
import shutil
import subprocess
from pathlib import Path


def run_kawakiri(data_directory: Path, report_path: Path, skip_sql_views: bool) -> None:
    """Run the complete Kawakiri pipeline through its supported CLI."""
    executable = shutil.which("kawakiri")
    if executable is None:
        raise RuntimeError(
            "The 'kawakiri' command was not found. Activate the environment "
            "where Kawakiri is installed."
        )

    if not data_directory.is_dir():
        raise FileNotFoundError(f"CSV directory not found: {data_directory}")

    report_path.parent.mkdir(parents=True, exist_ok=True)
    command = [
        executable,
        "run-all",
        str(data_directory.resolve()),
        "--report",
        str(report_path.resolve()),
    ]
    if skip_sql_views:
        command.append("--skip-sql-views")

    subprocess.run(command, check=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run Kawakiri from an external Python project.")
    parser.add_argument("data_directory", type=Path, help="Folder containing CSV files")
    parser.add_argument(
        "--report",
        type=Path,
        default=Path("kawakiri-report.json"),
        help="Output JSON report path",
    )
    parser.add_argument(
        "--skip-sql-views",
        action="store_true",
        help="Generate certification artifacts without SQL views",
    )
    args = parser.parse_args()

    run_kawakiri(args.data_directory, args.report, args.skip_sql_views)


if __name__ == "__main__":
    main()
