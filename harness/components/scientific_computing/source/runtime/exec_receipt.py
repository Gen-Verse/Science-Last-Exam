"""Work around this Docker gateway returning before attached exec completes.

Wait for an exit receipt and transfer output through docker cp. This leaves
container isolation and task/scorer code unchanged.
"""
import asyncio
import shlex
import tempfile
import time
import uuid
from pathlib import Path

from harbor.environments.base import ExecResult


async def execute(environment, command, *, service, cwd, env, timeout_sec, user):
    remote = '/tmp/sle-exec-' + uuid.uuid4().hex
    seconds = timeout_sec or 600
    # Bound the process inside the container: the gateway can return before
    # attached exec completes. A tool timeout must produce a known exit status,
    # rather than leaving a command running and aborting the entire agent.
    bounded = 'timeout --signal=TERM --kill-after=5s ' + str(seconds) + 's bash -c ' + shlex.quote(command)
    shell = ('mkdir -p ' + remote + '; ' + bounded
             + ' >' + remote + '/stdout 2>' + remote + '/stderr; '
             + 'result=$?; printf "%s" "$result" >' + remote + '/status')
    args = ['exec', '-T']
    if cwd:
        args += ['-w', cwd]
    if env:
        for key, value in env.items():
            args += ['-e', key + '=' + value]
    if user is not None:
        args += ['-u', str(user)]
    args += [service, 'bash', '-c', shell]
    deadline = time.monotonic() + seconds + 15
    await environment._run_docker_compose_command(args, check=True, timeout_sec=seconds + 10)
    with tempfile.TemporaryDirectory(prefix='sle-exec-receipt-') as temporary:
        local = Path(temporary)
        while True:
            try:
                await environment._platform.download_file(remote + '/status', local / 'status', service=service)
                status = (local / 'status').read_text().strip()
                if status:
                    break
            except RuntimeError:
                pass
            if time.monotonic() >= deadline:
                raise TimeoutError('Docker exec did not complete before its deadline')
            await asyncio.sleep(0.2)
        for name in ['stdout', 'stderr']:
            await environment._platform.download_file(remote + '/' + name, local / name, service=service)
        result = ExecResult(stdout=(local / 'stdout').read_text(errors='replace'),
                            stderr=(local / 'stderr').read_text(errors='replace'), return_code=int(status))
    await environment._run_docker_compose_command(['exec', '-T', service, 'rm', '-rf', remote], check=False)
    return result
