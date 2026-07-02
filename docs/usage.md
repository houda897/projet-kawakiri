# Using Kawakiri

Kawakiri is installed and operated through its command-line interface.

## Install

On Linux or macOS:

```bash
chmod +x install.sh
./install.sh
source .venv/bin/activate
```

On Windows Command Prompt:

```bat
install.bat
.venv\Scripts\activate
```

Use `./install.sh --dev` or `install.bat --dev` to include test, lint, and
documentation dependencies. Both scripts preserve an existing `.env` file.

## Configure ClickHouse

Edit the `.env` file created from `.env.example`:

```dotenv
CH_HOST=localhost
CH_PORT=11123
CH_DATABASE=lab_db
CH_USER=default
CH_PASSWORD=
META_DB=lab_meta
```

Use port `8123` for a native ClickHouse server unless its HTTP port was changed.

## Run the complete pipeline

```bash
kawakiri run-all path/to/csv-folder --report report.json
```

The folder must contain one CSV file per source table. The command writes a JSON
certification report and a Mermaid model next to it. SQL views are generated only when
a suitable certified model exists.

## Run the bundled example

```bash
kawakiri run-all code/data --report example-report.json
```

## Call Kawakiri from another project

Copy `examples/external_project_main.py` into another project, activate the environment
in which Kawakiri is installed, and run:

```bash
python external_project_main.py path/to/csv-folder --report output/model.json
```

The example uses Python's `subprocess` module to execute the Kawakiri command and
propagates any non-zero exit status to the calling project.

## Run individual stages

Use `kawakiri --help` to list all commands. Individual stages are useful for inspection
and debugging, but they share metadata in ClickHouse and must be executed in pipeline
order. The complete order is documented in the README.
