# Governance

Kawakiri is developed as an open research-software project. Its current governance is
maintainer-led and may evolve as the contributor community grows.

## Roles

### Maintainers

Maintainers review pull requests, protect architectural consistency, coordinate
releases, and decide whether changes satisfy the project's scientific and engineering
principles.

### Contributors

Contributors may propose code, tests, documentation, datasets, benchmarks, or research
use cases through issues and pull requests. Contributors must follow the
[Code of Conduct](CODE_OF_CONDUCT.md) and [contribution guide](CONTRIBUTING.md).

## Decision process

Routine changes are accepted through reviewed pull requests. Changes affecting public
interfaces, mathematical validation rules, metadata schemas, or model-certification
semantics should include:

- a written problem statement;
- the evidence or rule supporting the change;
- tests covering expected behavior and regressions;
- documentation of limitations and compatibility impact.

Maintainers seek consensus in public discussion. When consensus is not possible, the
maintainers make the final decision and record the reasoning in the issue or pull
request.

## Releases

Releases follow the repository release checklist. A release requires passing tests,
updated documentation and changelog, consistent citation metadata, and an archived
source snapshot. Scientific claims must remain reproducible from the tagged version.

## Authorship and credit

Software authorship, paper authorship, and acknowledgements follow actual
contributions. Contributor credit is recorded in Git history, `AUTHORS.rst`, release
notes, and scholarly metadata where appropriate.
