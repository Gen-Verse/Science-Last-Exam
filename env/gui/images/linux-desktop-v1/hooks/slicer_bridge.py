#!/usr/bin/env python3
"""Guest-loopback readiness helper for a Slicer desktop process.

This is not the authenticated Science GUI bridge and exposes no model action
endpoint. It only owns the Slicer child and reports readiness to the bridge.
"""
from __future__ import annotations

import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import secrets
import signal
import subprocess
import tempfile
import time


class State:
    def __init__(self, command: list[str], delay: float = 0):
        self.command = command
        self.delay = delay
        self.started_at = 0.0
        self.process: subprocess.Popen | None = None
        self.folder = tempfile.TemporaryDirectory(prefix="slicer-readiness-")
        self.receipt = Path(self.folder.name) / "ready.json"
        self.nonce = secrets.token_hex(24)

    def start(self) -> None:
        if any(arg in self.command for arg in ("--python-script", "--python-code", "--disable-python", "--no-main-window")):
            raise ValueError("Slicer readiness requires the managed GUI startup script")
        env = dict(os.environ, SCIENCE_SLICER_READY_FILE=str(self.receipt),
                   SCIENCE_SLICER_READY_NONCE=self.nonce)
        self.receipt.unlink(missing_ok=True)
        self.process = subprocess.Popen(
            [*self.command, "--python-script", str(Path(__file__).with_name("slicer_ready.py"))],
            env=env, start_new_session=True)
        self.started_at = time.monotonic()

    def readiness(self) -> dict:
        code = self.process.poll() if self.process else None
        status = {'ready': False, 'process_started': self.process is not None,
                  'process_alive': self.process is not None and code is None, 'return_code': code}
        if not status['process_alive']:
            return status
        try:
            value = json.loads(self.receipt.read_text())
            age = time.monotonic() - value["monotonic"]
            status.update(heartbeat_age_seconds=age, heartbeat_current=value['nonce'] == self.nonce,
                          **{k: value.get(k) for k in ('main_window_visible', 'views_initialized', 'splash_visible', 'modal_active', 'consecutive_ready_ticks')})
            status['ready'] = bool(value["nonce"] == self.nonce and value["ready"] is True
                                   and value["consecutive_ready_ticks"] >= 2 and 0 <= age < 3)
        except (OSError, ValueError, KeyError, TypeError):
            status['heartbeat_available'] = False
        return status

    def ready(self) -> bool:
        return self.readiness()['ready']

    def stop(self, *_args) -> None:
        if self.process and self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=15)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait()
        self.folder.cleanup()


def make_server(state: State, version: str, port: int) -> ThreadingHTTPServer:
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_args):
            pass

        def do_GET(self):
            if self.path == "/version":
                body = version.encode("ascii")
                self.send_response(200)
            elif self.path == "/ready":
                status = state.readiness()
                body = b"ready" if status['ready'] else json.dumps(status).encode()
                self.send_response(200 if status['ready'] else 503)
            else:
                body = b"not ready"
                self.send_response(503)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_POST(self):
            if self.path != "/dump" or not state.ready():
                self.send_response(404)
                self.end_headers()
                return
            payload = json.dumps({"application": "slicer", "pid": state.process.pid}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

    return ThreadingHTTPServer(("127.0.0.1", port), Handler)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--slicer", nargs="+", required=True)
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--version", default="1.0")
    parser.add_argument("--ready-delay", type=float, default=0,
                        help="Deprecated compatibility option; readiness never follows a fixed delay")
    args = parser.parse_args()
    state = State(args.slicer, max(0.0, args.ready_delay))
    state.start()
    server = make_server(state, args.version, args.port)
    def handle_signal(_signum, _frame):
        state.stop()
        raise SystemExit(0)
    signal.signal(signal.SIGTERM, handle_signal)
    signal.signal(signal.SIGINT, handle_signal)
    try:
        server.serve_forever()
    finally:
        server.server_close()
        state.stop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
