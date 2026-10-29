"""Standalone Docker command transport with explicit terminal status and output."""
import os
from pathlib import Path
import shlex
import subprocess
import tempfile
import time
import uuid


def direct_env():
    env = dict(os.environ)
    for key in ('HTTP_PROXY', 'HTTPS_PROXY', 'ALL_PROXY', 'http_proxy', 'https_proxy', 'all_proxy'):
        env.pop(key, None)
    env.update(NO_PROXY='*', no_proxy='*')
    return env


def execute(container, argv, timeout=2100):
    remote = '/tmp/closeloop-check-' + uuid.uuid4().hex
    shell = ('mkdir -p ' + remote + '; timeout --signal=TERM --kill-after=5s '
             + str(timeout) + 's ' + shlex.join(argv) + ' >' + remote + '/stdout 2>'
             + remote + '/stderr; result=$?; printf "%s" "$result" >' + remote + '/status')
    subprocess.run(['docker', 'exec', '-d', container, 'bash', '-c', shell], check=True, env=direct_env())
    deadline = time.monotonic() + timeout + 15
    with tempfile.TemporaryDirectory(prefix='closeloop-exec-') as directory:
        path = Path(directory)
        while True:
            copied = subprocess.run(['docker', 'cp', container + ':' + remote + '/status', str(path / 'status')],
                                    capture_output=True, env=direct_env())
            if copied.returncode == 0 and (path / 'status').read_text().strip():
                break
            if time.monotonic() >= deadline:
                raise TimeoutError('Container command did not produce a terminal receipt.')
            time.sleep(0.5)
        for name in ('stdout', 'stderr'):
            subprocess.run(['docker', 'cp', container + ':' + remote + '/' + name, str(path / name)],
                           check=True, capture_output=True, env=direct_env())
        return subprocess.CompletedProcess(argv, int((path / 'status').read_text()),
                                           (path / 'stdout').read_text(errors='replace'),
                                           (path / 'stderr').read_text(errors='replace'))
