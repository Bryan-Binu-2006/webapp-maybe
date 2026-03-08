#!/usr/bin/env bash
set -euo pipefail

# Always run from the project root regardless of where script is invoked from.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

if [[ ! -d "venv" ]]; then
  echo "Error: venv directory not found at $SCRIPT_DIR/venv"
  echo "Create it first: python3 -m venv venv"
  exit 1
fi

# Activate virtual environment.
source "venv/bin/activate"

# Install/upgrade dependencies on every run.
pip install --upgrade -r requirements.txt

# Start Flask app.
python3 run.py
