#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

PYTHON_BIN="${PYTHON_BIN:-python3}"
INSTALL_TARGET="."

if [[ "${1:-}" == "--dev" ]]; then
    INSTALL_TARGET=".[dev]"
elif [[ $# -gt 0 ]]; then
    echo "Usage: ./install.sh [--dev]" >&2
    exit 2
fi

if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
    echo "Python 3.10 or later is required. Set PYTHON_BIN if needed." >&2
    exit 1
fi

"$PYTHON_BIN" - <<'PY'
import sys

if sys.version_info < (3, 10):
    raise SystemExit("Kawakiri requires Python 3.10 or later.")
PY

if [[ ! -d .venv ]]; then
    "$PYTHON_BIN" -m venv .venv
fi

VENV_PYTHON="$ROOT_DIR/.venv/bin/python"
"$VENV_PYTHON" -m pip install --upgrade pip
"$VENV_PYTHON" -m pip install -e "$INSTALL_TARGET"

if [[ ! -f .env ]]; then
    cp .env.example .env
    echo "Created .env from .env.example."
else
    echo "Keeping existing .env configuration."
fi

echo
echo "Kawakiri installation completed."
echo "Activate the environment with: source .venv/bin/activate"
echo "Then verify the CLI with: kawakiri --help"
echo "Run the bundled example with: kawakiri run-all code/data --report example-report.json"
