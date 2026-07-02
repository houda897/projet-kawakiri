# Release and JOSS checklist

## Repository checks

- [ ] Update the version in `pyproject.toml` and `CITATION.cff`.
- [ ] Move completed entries from `Unreleased` in `CHANGELOG.md` to the release version.
- [ ] Verify authors, affiliations, acknowledgements, funding, and citation metadata.
- [ ] Run formatting, lint, unit tests, and the ClickHouse integration test.
- [ ] Run `mkdocs build --strict`.
- [ ] Build the wheel and source distribution in a clean environment.
- [ ] Ask an external user to follow the installation and minimal working example.

## JOSS paper checks

- [ ] Build `paper.md` with the official Open Journals toolchain.
- [ ] Verify every required JOSS section and every citation.
- [ ] Ensure scientific claims match the tagged software behavior.
- [ ] Include reproducible benchmarks or documented research use.
- [ ] Review and confirm the AI usage disclosure.

## Release actions

- [ ] Merge the release changes into the default branch.
- [ ] Create and push an annotated version tag.
- [ ] Publish a GitHub release using the changelog.
- [ ] Archive the exact release on Zenodo and obtain a software DOI.
- [ ] Add the DOI to citation metadata, README badges, and the paper.

## External readiness

- [ ] Maintain genuine public and iterative development history.
- [ ] Use public issues, pull requests, or discussions.
- [ ] Document research impact through use, benchmarks, integrations, or publications.
- [ ] Keep the public issue tracker available to users.

Consult the current [JOSS submission requirements](https://joss.readthedocs.io/en/latest/submitting.html)
and [paper format](https://joss.readthedocs.io/en/latest/paper.html) before submission.
