"""Verify a new deployment freeze without starting a VM or calling a model."""
import hashlib
from pathlib import Path
from harness.paths import COMPONENT, environment_root, image_root


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def verify_freeze(freeze, repo, runtime_config, model_config, task):
    if freeze.get('all_prerequisites_verified') is not True:
        raise RuntimeError('Research readiness prerequisites are incomplete')
    if freeze.get('task') != task:
        raise RuntimeError('Freeze does not bind the selected task')
    deployment = freeze.get('deployment', {})
    for key, path in (('runtime_config_sha256', runtime_config), ('model_config_sha256', model_config)):
        if deployment.get(key) != sha256(path):
            raise RuntimeError('Missing or mismatched frozen deployment: ' + key)
    repo = Path(repo).resolve()
    files = freeze.get('repository_files', {})
    required = set()
    for folder in ('harness', 'model', 'task/' + task):
        for path in (repo / folder).rglob('*'):
            if path.is_file() and '__pycache__' not in path.parts and (
                    path.suffix == '.py' or folder.startswith('task/')):
                required.add(path.relative_to(repo).as_posix())
    required.update(p.relative_to(repo).as_posix() for p in (repo/'harness/desktop_compat/native').rglob('*') if p.is_file())
    required.update({'env/copasi/install.py',
                     'harness/desktop_compat/sdk/manifest.json', 'harness/desktop_compat/sdk/compatibility.patch',
                     'harness/images/linux-desktop-v1/guest.json', 'harness/images/linux-desktop-v1/image.json',
                     'env/vm/scripts/start-desktop-controller.py'})
    if not required.issubset(files):
        raise RuntimeError('Freeze omits required code, task or deployment files')
    for name, expected in files.items():
        path = (repo / name).resolve()
        allowed = repo
        if repo == COMPONENT and name.startswith(('env/', 'harness/images/')):
            path = ((environment_root()/name.removeprefix('env/')) if name.startswith('env/') else (image_root()/name.removeprefix('harness/images/'))).resolve()
            allowed = environment_root().resolve()
        if not path.is_relative_to(allowed) or not path.is_file() or sha256(path) != expected:
            raise RuntimeError('Frozen repository file changed: ' + name)
    freeze_id = freeze.get('freeze_id', '')
    if len(freeze_id) != 64 or any(c not in '0123456789abcdef' for c in freeze_id):
        raise RuntimeError('Require a hexadecimal SHA256 freeze_id')
