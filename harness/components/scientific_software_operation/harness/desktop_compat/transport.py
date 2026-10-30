"""Bounded transport facade for the actual upstream PythonController.

Upstream catches request failures. Potentially mutating guest commands are never
retried. Explicitly classified read-only queries may retry once, within the same
absolute deadline. The default remains potentially mutating.
"""
import time
import requests
from harness.timeouts import scaled_timeout


class IndeterminateGUI(RuntimeError):
    pass


class ControllerTransport:
    Response = requests.Response
    exceptions = requests.exceptions

    def __init__(self, event_sink=None):
        self.session = requests.Session()
        self.session.trust_env = False
        self.deadline = time.monotonic()
        self.last_error = None
        self.uncertain_execute = False
        self.read_only = False
        self.event_sink = event_sink
        self.attempts = []

    def bind(self, deadline):
        self.deadline = deadline

    def request(self, method, url, **kwargs):
        left = self.deadline - time.monotonic()
        if left <= 0:
            raise TimeoutError('No controller time remaining')
        self.last_error = None
        connect = min(scaled_timeout(2), left / 4)
        default_cap = scaled_timeout(15)
        read_cap = scaled_timeout(getattr(self, 'sealed_collection_read_cap', 15))
        read_timeout = min(read_cap, max(.001, left-connect-.5)) if read_cap > default_cap else min(default_cap, max(.001, left*3/4))
        kwargs['timeout'] = (connect, read_timeout)
        try:
            return self.session.request(method, url, **kwargs)
        except requests.RequestException as exc:
            self.last_error = {'kind': type(exc).__name__, 'message': str(exc)[:300]}
            if method == 'POST' and url.endswith('/execute') and not self.read_only:
                self.uncertain_execute = True
            raise

    def get(self, url, **kwargs):
        return self.request('GET', url, **kwargs)

    def post(self, url, **kwargs):
        return self.request('POST', url, **kwargs)

    def attach(self, env, server_port=5001):
        import desktop_env.controllers.python as upstream
        if not hasattr(self, 'original_requests'):
            self.original_requests = upstream.requests
        upstream.requests = self
        env.controller = upstream.PythonController(env.vm_ip, server_port)
        env.controller.retry_times = 1
        env.controller.retry_interval = 0
        self.controller = env.controller
        return self.controller

    def execute(self, code, deadline, *, read_only=False):
        if self.uncertain_execute:
            raise IndeterminateGUI('Previous guest command outcome is unknown; no new command dispatched')
        self.bind(deadline)
        self.read_only = read_only
        try:
            for attempt in range(1, 3 if read_only else 2):
                if time.monotonic() >= deadline:
                    raise TimeoutError('No read-only retry time remaining')
                self.last_error = None
                started = time.monotonic()
                result = self.controller.execute_python_command(code)
                record = {'read_only': read_only, 'attempt': attempt,
                          'elapsed_seconds': time.monotonic() - started,
                          'confirmed': result is not None, 'error': self.last_error,
                          'uncertain_execute': self.uncertain_execute}
                self.attempts.append(record)
                if self.event_sink:
                    self.event_sink('controller_execute_attempt', **record)
                if self.uncertain_execute:
                    raise IndeterminateGUI('Guest command execution not confirmed; refusing automatic retry')
                if result is None:
                    if read_only and self.last_error and attempt == 1:
                        continue
                    if read_only:
                        raise RuntimeError('Read-only controller query not confirmed after bounded attempts')
                    raise IndeterminateGUI('Guest command execution not confirmed; refusing automatic retry')
                if result.get('status') != 'success' or result.get('returncode') != 0:
                    raise RuntimeError('Guest command failed: ' + str(result.get('error') or result.get('message'))[:500])
                return result
        finally:
            self.read_only = False

    def close(self):
        import desktop_env.controllers.python as upstream
        upstream.requests = self.original_requests
        self.session.close()
