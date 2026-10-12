#!/usr/bin/env bash
# Runs once when the Codespace is created (and during prebuilds, if you enable them).
# Installs VeriCode in editable mode with its dev tools (pytest, coverage, ruff, mypy).
set -euo pipefail
cd "$(dirname "$0")/.."

echo "== installing vericode[dev]"
python -m pip install --quiet --upgrade pip
python -m pip install --quiet -e '.[dev]' || python -m pip install --quiet --user -e '.[dev]'
export PATH="$PATH:$HOME/.local/bin"

vericode --help >/dev/null || { echo "vericode entry point not on PATH" >&2; exit 1; }

cat <<'MSG'

VeriCode is installed. No model or API key is needed for these:
  make selftest    # full benchmark pipeline with mock models: the oracle must solve every run, noop none
  python -m pytest # the project's own test suite
  make check       # lint + types + tests with coverage gate + selftest (what CI runs)

Runs against a real model need a local Ollama server, which this small Codespace is not sized for.
MSG
