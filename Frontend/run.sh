#!/usr/bin/env bash
# One-command setup + run (macOS / Linux). Requires Python 3.10 on PATH as python3.10.
set -euo pipefail
cd "$(dirname "$0")"

PYTHON="${PYTHON:-python3.10}"
if ! command -v "$PYTHON" &>/dev/null; then
  echo "Python 3.10 not found. Install it or set PYTHON=... and retry."
  echo "  macOS (no admin): curl -LsSf https://astral.sh/uv/install.sh | sh && uv python install 3.10"
  exit 1
fi

if [[ ! -d .venv ]]; then
  echo "Creating virtual environment..."
  "$PYTHON" -m venv .venv
fi

# shellcheck disable=SC1091
source .venv/bin/activate
python -m pip install --upgrade pip -q
pip install -r requirements.txt -q

echo ""
python calibration_9point.py "$@"
