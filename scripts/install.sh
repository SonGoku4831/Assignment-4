#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
# Each cloud task already has an isolated checkout; no worktree is required.
VENV_PATH="${VENV_PATH:-$PWD/.venv}"
if [[ ! -x "$VENV_PATH/bin/python" ]]; then python3 -m venv "$VENV_PATH"; fi
"$VENV_PATH/bin/python" -m pip install --extra-index-url https://download.pytorch.org/whl/cpu -r requirements.lock.txt
"$VENV_PATH/bin/python" -m pip check
chmod -R a+rX monitoring
chmod a+r prometheus.yml
docker compose pull
"$VENV_PATH/bin/python" scripts/download_model.py
"$VENV_PATH/bin/python" scripts/generate_workload.py
