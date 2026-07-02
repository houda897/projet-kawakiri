Kawakiri
========

|Python Version| |ClickHouse| |Status| |Zenodo| |JOSS|

Kawakiri is an open-source platform that deterministically reconstructs candidate dimensional models, composed of fact and dimension tables, from heterogeneous and undocumented data sources. Using column-level data profiling, functional dependency discovery, key and join inference, graph topology analysis, and explicit validation rules, Kawakiri generates auditable star, snowflake, and constellation schemas.

Features
~~~~~~~~

-  automated dimensional modeling
-  rule-based schema inference
-  data profiling
-  functional dependency discovery
-  column-oriented data analysis
-  axiom-based model synthesis
-  database reverse engineering

What the pipeline does
----------------------

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

Validation rules
----------------

Kawakiri currently checks the following:

-  key uniqueness, completeness, and normalized Shannon entropy;
-  referential integrity and orphan values;
-  graph topology, including cycles and invalid fact-to-fact edges;
-  deterministic fact granularity;
-  minimality of the fact grain and model coverage;
-  semantic separation between facts and dimensions;
-  aggregation stability across inferred joins.

Architecture
------------

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

Requirements
------------

-  Internet connection;
-  Git installed;
-  Python 3.10 or later;
-  a reachable ClickHouse server.

Installation
------------

.. code:: bash

   python3 -m venv .venv
   source .venv/bin/activate
   pip install -e ".[dev]"

Create ``.env`` at the repository root:

.. code:: env

   CH_HOST=localhost
   CH_PORT=your_port
   CH_DATABASE=your_database
   CH_USER=your_user
   META_DB=your_metadata_database
   CH_PASSWORD=your_password

The data and metadata databases are created when the pipeline initializes its schemas.

Quick start
-----------

Place one CSV file per source table in a folder, then run:

.. code:: bash

   kawakiri run-all path/to/csv-folder --report report.json

The equivalent source-tree command is:

.. code:: bash

   python code/main.py run-all path/to/csv-folder --report report.json

When at least one candidate model passes certification, the command creates:

-  ``report.json``: certification results and model coverage;
-  ``report.mmd``: Mermaid ER representation;
-  ClickHouse SQL views for the best certified model, unless ``--skip-sql-views`` is used.

Step-by-step execution
----------------------

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

Inspect the available commands with:

.. code:: bash

   kawakiri --help

Development
-----------

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

See `CONTRIBUTING.md <CONTRIBUTING.md>`__ and the documentation site for further details.

Project Structure
-----------------

::

   Kawakiri/
   ├── code/
   │   ├── config/       Scoring thresholds and configuration
   │   ├── core/         Shared schemas, metadata and utilities
   │   ├── ingestion/    Source ingestion into ClickHouse
   │   ├── profiling/    Statistical column profiling
   │   ├── stats/        Entropy and functional dependencies
   │   ├── inference/    Group, key, join and role inference
   │   ├── modeling/     Fact, dimension and model construction
   │   ├── validation/   Mathematical and structural validation rules
   │   ├── generation/   SQL view generation
   │   ├── reporting/    JSON reports and Mermaid diagrams
   │   ├── semantic/     Complementary semantic analysis
   │   └── main.py       Command-line interface
   ├── docs/             Documentation and tutorials
   ├── tests/            Unit and integration tests
   ├── pyproject.toml    Python package configuration
   ├── paper.md          JOSS paper
   ├── LICENSE           MIT license
   └── README.rst        Project overview and usage guide

Citation
--------

Academic citation metadata is provided in `CITATION.cff <CITATION.cff>`__. The JOSS paper sources are available in `paper.md <paper.md>`__ and `paper.bib <paper.bib>`__.

Contributors
------------

See the `AUTHORS <AUTHORS.rst>`__ file for a complete list of contributors to the project.

License
-------

Kawakiri is distributed under the `MIT License <LICENSE>`__.

.. |Python Version| image:: https://img.shields.io/badge/python-3.10%2B-blue.svg
.. |ClickHouse| image:: https://img.shields.io/badge/ClickHouse-required-yellow.svg
.. |Status| image:: https://img.shields.io/badge/status-alpha-orange.svg
.. |Zenodo| image:: https://img.shields.io/badge/DOI-Zenodo-red.svg
   :target: https://zenodo.org/records/21100022
   :alt: Zenodo dataset DOI
.. |JOSS| image:: https://img.shields.io/badge/JOSS-in%20preparation-lightgrey.svg
   :alt: JOSS paper in preparation
