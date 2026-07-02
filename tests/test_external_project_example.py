import importlib.util
from pathlib import Path

import pytest

EXAMPLE_PATH = Path(__file__).parents[1] / "examples" / "external_project_main.py"
SPEC = importlib.util.spec_from_file_location("external_project_main", EXAMPLE_PATH)
assert SPEC is not None and SPEC.loader is not None
external_project_main = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(external_project_main)


def test_run_kawakiri_builds_cli_command(monkeypatch, tmp_path: Path) -> None:
    data_directory = tmp_path / "data"
    data_directory.mkdir()
    report_path = tmp_path / "reports" / "model.json"
    captured = {}

    monkeypatch.setattr(external_project_main.shutil, "which", lambda _: "/bin/kawakiri")

    def fake_run(command, check):
        captured["command"] = command
        captured["check"] = check

    monkeypatch.setattr(external_project_main.subprocess, "run", fake_run)

    external_project_main.run_kawakiri(
        data_directory,
        report_path,
        skip_sql_views=True,
    )

    assert captured == {
        "command": [
            "/bin/kawakiri",
            "run-all",
            str(data_directory.resolve()),
            "--report",
            str(report_path.resolve()),
            "--skip-sql-views",
        ],
        "check": True,
    }
    assert report_path.parent.is_dir()


def test_run_kawakiri_requires_installed_cli(monkeypatch, tmp_path: Path) -> None:
    data_directory = tmp_path / "data"
    data_directory.mkdir()
    monkeypatch.setattr(external_project_main.shutil, "which", lambda _: None)

    with pytest.raises(RuntimeError, match="command was not found"):
        external_project_main.run_kawakiri(
            data_directory,
            tmp_path / "report.json",
            skip_sql_views=False,
        )
