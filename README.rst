Kawakiri
========

|Python Version| |ClickHouse| |Status| |CI| |Zenodo| |JOSS|

Kawakiri is an open-source platform that deterministically reconstructs candidate dimensional models, composed of fact and dimension tables, from heterogeneous and undocumented CSV datasets. It executes its analytical workloads in ClickHouse, a column-oriented analytical database like DuckDB. Using column-level data profiling, functional dependency discovery, key and join inference, graph topology analysis, and explicit validation rules, Kawakiri generates auditable star, snowflake, and constellation schemas.

✨ Features
-----------

-  automated dimensional modeling
-  rule-based schema inference
-  data profiling
-  functional dependency discovery
-  column-oriented data analysis
-  axiom-based model synthesis
-  database reverse engineering

🔄 What the pipeline does
---------------------------

.. code:: text

   CSV ingestion:
   -> raw column profiling and statistics
   -> identifiability scoring
   -> preliminary source keys and relationships
   -> functional column grouping
   -> logical fact/dimension materialization, with unresolved sources kept neutral
   -> logical-table profiling
   -> primary-key and join inference
   -> adjacency graph and table roles
   -> STAR / SNOWFLAKE / CONSTELLATION candidates
   -> ranking and validation
   -> certification
   -> SQL views, JSON report, and Mermaid schema

Functional groups are based on verified dependencies. A group can only be extended when its current columns determine an unassigned column. Columns without such evidence remain singletons in the grouping metadata and are not silently added to a dimension. Referenced, normalized sources are kept as coherent entities, while groups extracted from flat tables must demonstrate repeated determinant values and real compression gains.

✅ Validation rules
-------------------

Kawakiri currently checks the following:

-  key uniqueness, completeness, and normalized Shannon entropy;
-  referential integrity and orphan values;
-  graph topology, including cycles and invalid fact-to-fact edges;
-  deterministic fact granularity;
-  minimality of the fact grain and model coverage;
-  semantic separation between facts and dimensions;
-  aggregation stability across inferred joins.

🏗️ Architecture
----------------

+------------------+--------------------------------------------------------------------------------------+-------------------------------------------------------------------------------------+
| Layer            | Main classes                                                                         | Responsibility                                                                      |
+==================+======================================================================================+=====================================================================================+
| Ingestion        | ``CsvIngestionEngine``                                                               | Detect encoding, delimiter and types; import CSV rows                               |
+------------------+--------------------------------------------------------------------------------------+-------------------------------------------------------------------------------------+
| Profiling        | ``ProfileEngine``, ``compute_column_stats``                                          | Compute cardinality, null ratio, entropy and numeric statistics                     |
+------------------+--------------------------------------------------------------------------------------+-------------------------------------------------------------------------------------+
| Grouping         | ``FunctionalGroupBuilder``                                                           | Build non-overlapping functional column groups                                      |
+------------------+--------------------------------------------------------------------------------------+-------------------------------------------------------------------------------------+
| Logical modeling | ``FactDimensionBuilder``, ``LogicalTableBuilder``                                    | Classify proven groups, preserve unresolved sources, and materialize logical tables |
+------------------+--------------------------------------------------------------------------------------+-------------------------------------------------------------------------------------+
| Inference        | ``PrimaryKeyEngine``, ``JoinEngine``, ``AdjacencyMatrixEngine``, ``TableRoleEngine`` | Infer keys, joins, graph edges and roles                                            |
+------------------+--------------------------------------------------------------------------------------+-------------------------------------------------------------------------------------+
| Modeling         | ``DecisionModelCandidateBuilder``, ``ModelRanking``                                  | Build and rank dimensional-model candidates                                         |
+------------------+--------------------------------------------------------------------------------------+-------------------------------------------------------------------------------------+
| Validation       | Structural, granularity, semantic and aggregation validators                         | Apply the conformity rules                                                          |
+------------------+--------------------------------------------------------------------------------------+-------------------------------------------------------------------------------------+
| Generation       | ``SQLViewGenerator``                                                                 | Generate views for the best certified model                                         |
+------------------+--------------------------------------------------------------------------------------+-------------------------------------------------------------------------------------+
| Reporting        | ``CertificationReportExporter``                                                      | Export JSON and Mermaid results                                                     |
+------------------+--------------------------------------------------------------------------------------+-------------------------------------------------------------------------------------+

Computed evidence is stored in a dedicated ClickHouse metadata database.

📄 Supported inputs
-------------------

The current release accepts CSV files. A folder analysis expects one file per source table and derives the ClickHouse table name from each filename.

-  supported delimiters: comma, semicolon, and tab;
-  supported encodings: UTF-8, UTF-8 with BOM, UTF-16, UTF-32, Windows-1252, and Latin-1 fallback;
-  a header row is required;
-  physical column types are inferred from a sample and checked during import;
-  delimiters contained inside values must be quoted according to CSV rules.

🧰 Requirements
---------------

-  Python 3.10 or later;
-  Git, when installing from the source repository;
-  access to a ClickHouse server, running through Docker, a native installation, or a remote deployment.

📦 Installation
---------------

Clone the repository first:

.. code:: bash

   git clone https://github.com/houda897/projet-kawakiri.git
   cd projet-kawakiri

Automated installation
~~~~~~~~~~~~~~~~~~~~~~

On Linux and macOS:

.. code:: bash

   chmod +x install.sh
   ./install.sh
   source .venv/bin/activate

On Windows Command Prompt:

.. code:: bat

   install.bat
   .venv\Scripts\activate

Pass ``--dev`` to either installation script to include test, lint, coverage, and
documentation dependencies. The scripts create ``.env`` from ``.env.example`` only
when no local configuration exists.

Manual installation
~~~~~~~~~~~~~~~~~~~

Linux and macOS
^^^^^^^^^^^^^^^

.. code:: bash

   python3 -m venv .venv
   source .venv/bin/activate
   python -m pip install --upgrade pip
   python -m pip install -e .

Windows (PowerShell)
^^^^^^^^^^^^^^^^^^^^

.. code:: powershell

   py -3.10 -m venv .venv
   .\.venv\Scripts\Activate.ps1
   python -m pip install --upgrade pip
   python -m pip install -e .

Start ClickHouse
~~~~~~~~~~~~~~~~

Docker provides the same setup on Linux, macOS, and Windows:

.. code:: bash

   docker run -d --name kawakiri-clickhouse -p 11123:8123 -p 19000:9000 -e CLICKHOUSE_DB=lab_db clickhouse/clickhouse-server:25.8

On Linux and macOS, ClickHouse also provides a native installer:

.. code:: bash

   curl https://clickhouse.com/ | sh
   ./clickhouse server

The native server uses HTTP port ``8123`` by default. The Docker command above maps that port to ``11123`` on the host, which matches Kawakiri's default configuration. On Windows, Docker Desktop or ClickHouse under WSL2 is recommended. The Docker image is pinned to the ClickHouse 25.8 LTS release for reproducibility.

Create ``.env`` at the repository root. On Linux and macOS, copy and run:

.. code:: bash

   cat > .env <<'EOF'
   CH_HOST=localhost
   CH_PORT=11123
   CH_DATABASE=lab_db
   CH_USER=default
   META_DB=lab_meta
   CH_PASSWORD=
   EOF

When using the native ClickHouse server instead of the Docker command above, set
``CH_PORT=8123``. For a remote deployment, replace the host, port, user, and password
with the values supplied by its administrator.

On Windows PowerShell, copy and run:

.. code:: powershell

   @'
   CH_HOST=localhost
   CH_PORT=11123
   CH_DATABASE=lab_db
   CH_USER=default
   META_DB=lab_meta
   CH_PASSWORD=
   '@ | Set-Content .env

The data and metadata databases are created when the pipeline initializes its schemas. Confirm that ClickHouse is reachable before continuing:

.. code:: bash

   curl http://localhost:11123/ping

On Windows PowerShell, use:

.. code:: powershell

   Invoke-WebRequest http://localhost:11123/ping

🚀 Minimal working example
--------------------------

The repository contains a small multi-table example in ``code/data``. Once the installation and ClickHouse configuration above are complete, copy and run:

.. code:: bash

   kawakiri run-all code/data --report example-report.json
   ls -lh example-report.json example-report.mmd

On Windows PowerShell, use:

.. code:: powershell

   kawakiri run-all code/data --report example-report.json
   Get-Item example-report.json, example-report.mmd

The command produces:

-  ``example-report.json``: certification results and model coverage;
-  ``example-report.mmd``: Mermaid representation of the inferred model;
-  ClickHouse SQL views for the best certified model, unless ``--skip-sql-views`` is used.

This is the smallest complete execution of Kawakiri: it ingests the example CSV files, profiles their columns, reconstructs logical fact and dimension candidates, infers keys and joins, validates the candidate schemas, and exports the final artifacts.

📊 Understanding the results
--------------------------

Each candidate model receives one of three certification statuses:

-  ``VALID``: all required validation rules pass and the model can be used to generate SQL views;
-  ``WARNING``: the structure remains usable for inspection, but one or more non-blocking issues require review;
-  ``INVALID``: at least one blocking rule fails, such as an invalid grain, structural inconsistency, or unstable aggregation.

The JSON report records candidate scores, detected fact and dimension tables, validation issues, excluded tables, and model coverage. The Mermaid file provides a readable representation of tables, columns, keys, relationships, and cardinalities. Certification describes the evidence observed in the data; it does not replace validation by a domain expert.

🛠️ Ways to use Kawakiri
----------------------

Analyze your own CSV folder
~~~~~~~~~~~~~~~~~~~~~~~~~~~

Place one CSV file per source table in the same folder. Replace ``path/to/csv-folder`` with the real path, then run:

.. code:: bash

   kawakiri run-all path/to/csv-folder --report report.json

Use ``--skip-sql-views`` when you only need inference and certification artifacts:

.. code:: bash

   kawakiri run-all path/to/csv-folder --report report.json --skip-sql-views

Import one CSV file
~~~~~~~~~~~~~~~~~~~

Use this mode to import and inspect a single source before running other stages manually:

.. code:: bash

   kawakiri ingest-csv path/to/table.csv --table my_table

Run directly from the source tree
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Installation creates the ``kawakiri`` command. The same pipeline can also be started directly from the cloned repository:

.. code:: bash

   python code/main.py run-all code/data --report report.json

Call Kawakiri from another project
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Kawakiri is operated through its command-line interface. The example
``examples/external_project_main.py`` shows how another Python project can execute the
CLI and detect execution failures. A minimal ``main.py`` can be written as follows:

.. code:: python

   from pathlib import Path
   import subprocess


   def run_kawakiri(csv_folder: Path, report: Path) -> None:
       """Execute Kawakiri through its supported command-line interface."""
       report.parent.mkdir(parents=True, exist_ok=True)
       subprocess.run(
           [
               "kawakiri",
               "run-all",
               str(csv_folder),
               "--report",
               str(report),
           ],
           check=True,
       )


   def main() -> None:
       run_kawakiri(
           csv_folder=Path("data/csv"),
           report=Path("output/kawakiri-report.json"),
       )


   if __name__ == "__main__":
       main()

Save the file in the external project, place the source CSV files in ``data/csv``,
activate the environment where Kawakiri is installed, then run:

.. code:: bash

   python main.py

The complete reusable version remains available in
``examples/external_project_main.py`` and accepts paths as command-line arguments:

.. code:: bash

   python examples/external_project_main.py path/to/csv-folder --report output/model.json

See the `usage guide <docs/usage.md>`__ for integration details.

Display the available commands
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. code:: bash

   kawakiri --help

🪜 Step-by-step execution
-------------------------

.. code:: bash

   kawakiri ingest-folder path/to/csv-folder
   kawakiri profile-basic
   kawakiri score-identifiability
   kawakiri infer-source-keys
   kawakiri infer-source-joins
   kawakiri infer-functional-groups
   kawakiri build-logical-tables
   kawakiri profile-logical-tables
   kawakiri score-identifiability
   kawakiri infer-pk
   kawakiri infer-joins
   kawakiri build-adjacency
   kawakiri infer-table-roles
   kawakiri build-model-candidates
   kawakiri rank-models
   kawakiri validate-structure
   kawakiri validate-granularity
   kawakiri validate-semantic-homogeneity
   kawakiri validate-aggregation-stability
   kawakiri certify-models
   kawakiri generate-sql-views
   kawakiri export-certification-report report.json

``score-identifiability`` is intentionally run twice. The first execution evaluates columns from the raw source tables. After logical reconstruction and profiling, the second execution evaluates the columns of the materialized logical tables.

🩹 Troubleshooting
------------------

ClickHouse connection refused
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Check that the server is running, verify ``CH_HOST`` and ``CH_PORT`` in ``.env``, then call the ``/ping`` endpoint shown in the installation section. Docker uses host port ``11123`` in this guide, while a native ClickHouse server normally uses ``8123``.

Malformed CSV row
~~~~~~~~~~~~~~~~~

Verify that every row has the same number of fields as the header. Values containing the active delimiter must be enclosed in quotes. Kawakiri accepts commas, semicolons, and tabs as delimiters.

Encoding error
~~~~~~~~~~~~~~

Kawakiri detects common Unicode encodings, Windows-1252, and Latin-1. If a file still cannot be decoded consistently, convert the complete file to UTF-8 before ingestion instead of replacing individual invalid characters.

No certified model or SQL view
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Open ``report.json`` and inspect the reported validation issues. Kawakiri still exports JSON and Mermaid artifacts when no candidate is fully certified, but it does not create SQL views from an invalid model.



🧪 Development and tests
------------------------

Install the development dependencies:

.. code:: bash

   python -m pip install -e ".[dev]"

Run the unit tests:

.. code:: bash

   pytest

Run the ClickHouse integration test explicitly:

.. code:: bash

   pytest --run-integration tests/integration/test_e2e_pipeline.py

The integration test dataset can be downloaded from `Zenodo <https://zenodo.org/records/21100022>`__ using DOI ``10.5281/zenodo.21100022``.

Build the documentation with strict link and configuration checks:

.. code:: bash

   mkdocs build --strict

Preview it locally with ``mkdocs serve``.

See `CONTRIBUTING.md <CONTRIBUTING.md>`__ and the `documentation index <docs/index.md>`__ for further details.

🤝 Community and project policies
---------------------------------

-  `Contribution guide <CONTRIBUTING.md>`__
-  `Support policy <SUPPORT.md>`__
-  `Security policy <SECURITY.md>`__
-  `Governance <GOVERNANCE.md>`__
-  `Changelog <CHANGELOG.md>`__
-  `Reproducibility guide <docs/reproducibility.md>`__
-  `Release and JOSS checklist <docs/release-checklist.md>`__

🗂️ Project structure
--------------------

::
   Kawakiri/
├── code/
│   ├── config/
│   ├── core/
│   ├── data/
│   ├── generation/
│   ├── inference/
│   ├── modeling/
│   ├── profiling/
│   ├── reporting/
│   ├── semantic/
│   ├── stats/
│   ├── validation/
│   └── main.py
├── docs/
└── tests/


📚 Citation
-----------

Academic citation metadata is provided in `CITATION.cff <CITATION.cff>`__. The JOSS paper sources are available in `paper.md <paper.md>`__ and `paper.bib <paper.bib>`__.

Guidelines for contributing to the project (code, documentation, bug fixes, feature requests) are described in the [CONTRIBUTING](CONTRIBUTING.md) file.

👥 Contributors
---------------

See the `AUTHORS <AUTHORS.rst>`__ file for a complete list of contributors to the project.

⚖️ License
----------

Kawakiri is distributed under the `MIT License <LICENSE>`__.

.. |Python Version| image:: https://img.shields.io/badge/python-3.10%2B-blue.svg
.. |ClickHouse| image:: https://img.shields.io/badge/ClickHouse-required-yellow.svg
.. |Status| image:: https://img.shields.io/badge/status-alpha-orange.svg
.. |CI| image:: https://github.com/houda897/projet-kawakiri/actions/workflows/ci.yml/badge.svg
   :target: https://github.com/houda897/projet-kawakiri/actions/workflows/ci.yml
   :alt: Continuous integration status
.. |Zenodo| image:: https://img.shields.io/badge/DOI-Zenodo-red.svg
   :target: https://zenodo.org/records/21100022
   :alt: Zenodo dataset DOI
.. |JOSS| image:: https://img.shields.io/badge/JOSS-in%20preparation-lightgrey.svg
   :alt: JOSS paper in preparation
