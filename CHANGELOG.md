# Changelog

All notable changes to Kawakiri are documented in this file.

The project follows [Semantic Versioning](https://semver.org/) once a release is tagged.

## [Unreleased]

### Added

- Cross-platform installation scripts for Linux, macOS, and Windows.
- Reproducible CSV example and external CLI integration example.
- Documentation for support, security, governance, and reproducibility.
- Source-level key and join inference before logical reconstruction.
- Functional grouping, logical fact/dimension materialization, model coverage, and Mermaid reporting.

### Changed

- Extended the pipeline to distinguish source and logical inference scopes.
- Strengthened primary-key, grain, aggregation-stability, and model-certification checks.
- Converted the project README to reStructuredText and expanded installation guidance.

### Fixed

- CSV encoding detection for common Unicode encodings, Windows-1252, and Latin-1.
- Packaging, continuous integration, and JOSS paper build configuration.

[Unreleased]: https://github.com/houda897/projet-kawakiri/commits/main
