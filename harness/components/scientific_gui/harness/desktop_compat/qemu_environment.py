"""Managed QEMU deployment of the existing COPASI native controller."""
import json
import os
from pathlib import Path
import signal
import secrets
import subprocess
import time
import urllib.error
from harness.environment import RemoteEnvironment, QemuEnvironment


class CopasiQemuEnvironment(RemoteEnvironment):
    def __init__(self, spec, image_root, run_dir, token, port, accelerator='tcg'):
        super().__init__(f'http://127.0.0.1:{port}', secrets.token_urlsafe(32))
        self.spec, self.image_root = spec, Path(image_root)
        self.run_dir, self.port, self.accelerator = Path(run_dir), port, accelerator
        self.process = self.log = None
        self.reset_timeout = spec.get('boot_timeout',600)+300

    def start(self, task, mode, app_commands):
        if mode != 'gui_only' or app_commands:
            raise ValueError('COPASI requires GUI-only mode with application commands disabled')
        errors = QemuEnvironment.prerequisites(self.spec, self.image_root, self.accelerator)
        if errors: raise RuntimeError('; '.join(errors))
        python = Path(os.environ.get('SCIENTIFIC_GUI_COPASI_PYTHON', '/opt/copasi-controller/bin/python'))
        sdk = Path(os.environ.get('SCIENTIFIC_GUI_CONTROLLER_SDK', '/opt/controller-sdk'))
        if not python.is_file() or not sdk.is_dir():
            raise RuntimeError('Build env/Dockerfile with the isolated COPASI runtime and pinned controller SDK')
        self.run_dir.mkdir(parents=True, exist_ok=True)
        work = self.run_dir/'controller'; work.mkdir(exist_ok=True)
        upstream_token=self.run_dir/'controller-token'
        upstream_token.write_text(secrets.token_urlsafe(32));upstream_token.chmod(0o600)
        config = {'provider':'qemu', 'runtime_root':str(work.resolve()), 'sdk_path':str(sdk.resolve()),
            'image_path':str(QemuEnvironment.image_path(self.image_root,self.spec['filename'])),
            'snapshot':'immutable-qemu-base', 'controller_port':self.port+1,
            'guest_controller_dir':'/home/user/copasi_bench/controller-server',
            'guest_apps':'/home/user/copasi_bench/apps', 'guest_se':'/home/user/copasi_bench/apps/CopasiSE-4.47.309',
            'qemu':{'accelerator':self.accelerator,'spec':self.spec,'controller_token_file':str(upstream_token.resolve())},
            'resources':{'guest_gib':4,'host_reserve_gib':1,'minimum_disk_free_gib':26}}
        path = self.run_dir/'runtime.json';path.write_text(json.dumps(config,indent=2))
        environment = dict(os.environ, COPASI_WORK_ROOT=str(work.resolve()),
            COPASI_RUNTIME_CONFIG=str(path.resolve()), GUI_BRIDGE_TOKEN=self.token)
        self.log = (self.run_dir/'controller.log').open('wb')
        self.process = subprocess.Popen([str(python),'-m','harness.desktop_compat.bridge',
            '--task-path',str(task.path),'--log-dir',str(work/'logs'),'--port',str(self.port)],
            cwd=Path(__file__).resolve().parents[2], env=environment, stdout=self.log, stderr=subprocess.STDOUT)
        deadline = time.monotonic()+60
        self.initialization_phase = 'copasi_frontend_health'
        while time.monotonic()<deadline:
            if self.process.poll() is not None: raise RuntimeError('COPASI frontend exited; inspect controller.log')
            try:
                self.request('/health')
            except (urllib.error.URLError, TimeoutError, ConnectionError):
                time.sleep(.2)
                continue
            # Reset/setup is not a frontend-health retry. Preserve its failure
            # phase and never issue a second session/reset after an uncertain IO.
            return super().start(task,mode,app_commands)
        raise TimeoutError('COPASI frontend health endpoint did not become ready')

    def close(self):
        release_error=None
        try:super().close()
        except Exception as exc:release_error=exc
        pending = self.run_dir/'controller/validation/pending_guest_action.json'
        if pending.exists():
            raise RuntimeError('Uncertain COPASI action retained for inspection; no automatic VM stop')
        if self.process and self.process.poll() is None:
            self.process.send_signal(signal.SIGINT)
            try:self.process.wait(timeout=30)
            except subprocess.TimeoutExpired:
                raise RuntimeError('COPASI frontend shutdown did not confirm; inspect controller.log')
        if self.log:self.log.close()
        (self.run_dir/'controller-token').unlink(missing_ok=True)
        if release_error:raise release_error
