# Security Policy

## Supported versions

Kawakiri is currently alpha software. Security fixes are applied to the latest code on
the default branch and to the most recent tagged release when one exists.

## Reporting a vulnerability

Do not publish credentials, private datasets, connection strings, or exploit details in
a public issue.

Use GitHub's private vulnerability reporting feature for the repository when it is
available. Otherwise, open a public issue containing only a request for a private
security contact and no sensitive technical details.

Please include, through the private channel:

- the affected Kawakiri version or commit;
- the operating system and Python version;
- a description of the impact;
- minimal reproduction steps using non-sensitive data;
- any proposed mitigation, when available.

Maintainers will acknowledge valid reports, investigate their impact, and coordinate a
fix and disclosure. Response times are best effort while the project remains in alpha.

## Data and credential safety

Kawakiri connects to ClickHouse and processes user-provided datasets. Never commit
`.env` files, database passwords, private CSV files, generated reports containing
sensitive metadata, or local database files. Use a least-privileged ClickHouse account
for evaluation environments.
