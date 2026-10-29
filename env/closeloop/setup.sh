#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/../.."
if command -v uv >/dev/null 2>&1; then
    test -d env/.venv-closeloop || uv venv --python 3.12 env/.venv-closeloop
    uv pip install --python env/.venv-closeloop/bin/python -r env/closeloop/requirements.lock
else
    test -d env/.venv-closeloop || python3.12 -m venv env/.venv-closeloop
    env/.venv-closeloop/bin/python -m pip install -r env/closeloop/requirements.lock
fi
npm ci --prefix env/closeloop/codex --no-audit --no-fund
if [[ "${1:-}" == "--bridge" ]]; then
    env/.venv-closeloop/bin/python -B harness/closeloop/install_controller_compat.py
fi
env/.venv-closeloop/bin/python -B env/closeloop/manage.py setup-docker
