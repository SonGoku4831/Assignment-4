#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
PYTHON="${PYTHON:-/workspace/assignment4-env/venv/bin/python}"
if [[ ! -x "$PYTHON" ]]; then PYTHON="$PWD/.venv/bin/python"; fi
export HF_HOME="${HF_HOME:-$PWD/.cache/huggingface}"
export HF_HUB_DISABLE_XET=1
export STREAMLIT_BROWSER_GATHER_USAGE_STATS=false
mkdir -p artifacts
docker compose up -d
# Start only if no compatible worker is already listening. Never stop unrelated processes.
if ! curl -fsS http://127.0.0.1:8001/health >/dev/null 2>&1; then
    "$PYTHON" backend.py >artifacts/backend.log 2>&1 &
    worker_pid=$!
    printf "%s\n" "$worker_pid" > artifacts/backend.pid
    trap 'kill "$worker_pid" 2>/dev/null || true' EXIT
    for attempt in $(seq 1 30); do
        if curl -fsS http://127.0.0.1:8001/health >/dev/null 2>&1; then break; fi
        if ! kill -0 "$worker_pid" 2>/dev/null; then cat artifacts/backend.log; exit 1; fi
        sleep 1
    done
fi
"$PYTHON" -m streamlit run app.py --server.address 127.0.0.1 --server.port 8501 --server.headless true --server.maxUploadSize 50
