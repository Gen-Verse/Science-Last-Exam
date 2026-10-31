#!/usr/bin/env python3
"""A completed defective run is required before a floor can be scored."""
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

problem, case, run, cap = sys.argv[1:]
started = time.monotonic()
process = subprocess.Popen([sys.executable, str(Path(__file__).with_name("rowtool.py")),
                            "run", problem, case, run, "1"], start_new_session=True)
status = "completed"
try:
    code = process.wait(timeout=float(cap))
except subprocess.TimeoutExpired:
    status = "measurement_failed"
    os.killpg(process.pid, signal.SIGTERM)
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        os.killpg(process.pid, signal.SIGKILL)
        process.wait()
    code = 124
record = dict(status=status if code == 0 else "measurement_failed", exit=code,
              wall_seconds=round(time.monotonic() - started, 3), cap_seconds=float(cap))
Path(run, "straw-status.json").write_text(json.dumps(record, indent=2) + "\n")
print("straw measurement:", json.dumps(record), flush=True)
sys.exit(0 if code == 0 else 1)
