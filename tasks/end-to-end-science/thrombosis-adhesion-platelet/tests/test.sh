#!/bin/bash
set -euo pipefail
cd /tests
unset PYTHONPATH
exec /opt/venv/bin/python -I /tests/grader.py
