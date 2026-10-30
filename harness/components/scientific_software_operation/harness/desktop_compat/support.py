import contextlib
import hashlib
import json
import shutil
import time
import uuid
from pathlib import Path

import os
ROOT = Path(os.environ['COPASI_WORK_ROOT']).resolve()
BASE = ROOT.parent


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


class Metrics:
    def __init__(self, started=None):
        self.started = time.monotonic() if started is None else started
        self.times, self.counts, self.stack = {}, {}, []

    @contextlib.contextmanager
    def measure(self, name):
        frame = [time.monotonic(), 0]
        self.stack.append(frame)
        try:
            yield
        finally:
            elapsed = time.monotonic() - frame[0]
            self.stack.pop()
            self.times[name] = self.times.get(name, 0) + max(0, elapsed - frame[1])
            if self.stack:
                self.stack[-1][1] += elapsed

    def inc(self, key, amount=1):
        self.counts[key] = self.counts.get(key, 0) + amount

    def summary(self):
        elapsed = time.monotonic() - self.started
        return {'wall_seconds': elapsed, 'exclusive_seconds': dict(self.times),
                'counts': dict(self.counts),
                'other_runner_seconds': max(0, elapsed - sum(self.times.values()))}


class Log:
    def __init__(self, run, metrics):
        self.run, self.metrics = Path(run), metrics

    def json(self, name, data):
        with self.metrics.measure('logging'):
            path = self.run / name
            path.parent.mkdir(parents=True, exist_ok=True)
            temporary = path.with_name(path.name + '.writing')
            temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
            temporary.replace(path)

    def event(self, kind, **data):
        with self.metrics.measure('logging'):
            with (self.run / 'events.jsonl').open('a', encoding='utf-8') as stream:
                stream.write(json.dumps({'utc_ns': time.time_ns(), 'monotonic': time.monotonic(),
                                         'kind': kind, **data}, ensure_ascii=False) + '\n')


