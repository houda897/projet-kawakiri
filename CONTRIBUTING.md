# Contributing to Kawakiri

Thank you for contributing to Kawakiri. The project is research-oriented, so
contributions should keep the code simple, reproducible, and easy to explain.

## Development Setup

Follow the installation and configuration instructions in the `README.rst`, then install
the optional development dependencies:

```bash
./install.sh --dev
```

On Windows, use `install.bat --dev`. Manual installation with
`python -m pip install -e ".[dev]"` remains supported.

Do not commit `.env`, generated reports, local datasets, or cache files.

## Branch Naming

Use short, explicit branch names:

```text
feat/<feature-name>
fix/<bug-name>
docs/<documentation-change>
chore/<maintenance-change>
refactor/<refactor-name>
```

Examples:

```text
feat/final-certification-flow
docs/update-project-documentation
chore/code-quality-cleanup
```

## Code Style

Before opening a pull request, run:

```bash
ruff check code tests examples
ruff format --check code tests examples
pytest -q
```

To apply formatting:

```bash
ruff format code tests examples
```

The project favors:

- explicit imports instead of `import *`;
- small engine classes with one clear responsibility;
- ClickHouse metadata tables for reusable pipeline results;
- simple code over unnecessary abstraction;
- loggers instead of `print()` in project code.

## Pipeline Checks

For a full local run, provide your own folder of CSV files:

```bash
kawakiri run-all path/to/csv-folder --report report.json
```

If SQL views are not needed:

```bash
kawakiri run-all path/to/csv-folder --report report.json --skip-sql-views
```

## Pull Requests

Each pull request should include:

- a short summary of the change;
- the tests or commands that were run;
- any known limitation or follow-up.

User-visible changes should also be added to the `Unreleased` section of
`CHANGELOG.md`.

Keep pull requests focused. Documentation, validation logic, SQL generation, and
packaging changes should ideally be separated when they are large.

## I Want To Contribute


> **Legal Notice** : When contributing to this project, you must agree that you have authored 100% of the content, that you have the necessary rights to the content and that the content you contribute may be provided under the project licence.


### Reporting Bugs

#### Before Submitting a Bug Report

A good bug report shouldn't leave others needing to chase you up for more information. Therefore, we ask you to investigate carefully, collect information and describe the issue in detail in your report. Please complete the following steps in advance to help us fix any potential bug as fast as possible.

- Make sure that you are using the latest version.
- Determine if your bug is really a bug and not an error on your side e.g. using incompatible environment components/versions (Make sure that you have read the [documentation](docs)).
- To see if other users have experienced (and potentially already solved) the same issue you are having, check if there is not already a bug report existing for your bug or error in the [bug tracker](https://github.com/houda897/projet-kawakiri/issues).
- Also make sure to search the internet (including Stack Overflow) to see if users outside of the GitHub community have discussed the issue.
- Collect information about the bug:
    - Stack trace (Traceback)
    - OS, Platform and Version (Windows, Linux, macOS, x86, ARM)
    - Version of the interpreter, compiler, SDK, runtime environment, package manager, depending on what seems relevant.
    - Possibly your input and the output
    - Can you reliably reproduce the issue? And can you also reproduce it with older versions?

#### How Do I Submit a Good Bug Report?

> You must never report security related issues, vulnerabilities or bugs including sensitive information to the issue tracker, or elsewhere in public. Instead sensitive bugs must be sent by email to [mmartin.nevot@gmail.com](mmartin.nevot@gmail.com).


We use GitHub issues to track bugs and errors. If you run into an issue with the project:

- Open an Issue. (Since we can't be sure at this point whether it is a bug or not, we ask you not to talk about a bug yet and not to label the issue.)
- Explain the behavior you would expect and the actual behavior.
- Please provide as much context as possible and describe the *reproduction* steps that someone else can follow to recreate the issue on their own. This usually includes your code. For good bug reports you should isolate the problem and create a reduced test case.
- Provide the information you collected in the previous section.

Once it's filled:

- The project team will label the issue accordingly.
- A team member will try to reproduce the issue with your provided steps. If there are no reproduction steps or no obvious way to reproduce the issue, the team will ask you for those steps and mark the issue as `needs-repro`. Bugs with the `needs-repro` tag will not be addressed until they are reproduced.
-  If the team is able to reproduce the issue, it will be marked `needs-fix`, as well as possibly other tags (such as `critical`), and the issue will be left to be implemented by someone.

### Suggesting Enhancements

This section guides you through submitting an enhancement suggestion for Kawakiri: automated dimensional schema inference via rule-based data profiling. Following these guidelines will help maintainers and the community to understand your suggestion and find related suggestions.

#### Before Submitting an Enhancement

- Make sure that you are using the latest version.
- Read the [documentation](docs) carefully and find out if the functionality is already covered, maybe by an individual configuration.
- Perform a [search](https://github.com/houda897/projet-kawakiri/issues) to see if the enhancement has already been suggested. If it has, add a comment to the existing issue instead of opening a new one.
- Find out whether your idea fits with the scope and aims of the project. It's up to you to make a strong case to convince the project's developers of the merits of this feature. Keep in mind that we want features that will be useful to the majority of our users and not just a small subset. If you're just targeting a minority of users, consider writing an add-on/plugin library.

#### How Do I Submit a Good Enhancement Suggestion?

Enhancement suggestions are tracked as [GitHub issues](https://github.com/houda897/projet-kawakiri/issues).

- Use a clear and descriptive title for the issue to identify the suggestion.
- Provide a step-by-step description of the suggested enhancement in as many details as possible.
- Describe the current behavior and explain which behavior you expected to see instead and why. At this point you can also tell which alternatives do not work for you.
- You may want to include screenshots or screen recordings which help you demonstrate the steps or point out the part which the suggestion is related to. You can use [LICEcap](https://www.cockos.com/licecap/) to record GIFs on macOS and Windows, and the built-in [screen recorder in GNOME](https://help.gnome.org/gnome-help/screen-shot-record.html) or SimpleScreenRecorder on Linux.
- Explain why this enhancement would be useful to Kawakiri: automated dimensional schema inference via rule-based data profiling. You may also want to point out the other projects that solved it better and which could serve as inspiration.
