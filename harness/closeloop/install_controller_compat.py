"""Install captured Docker-bridge fixes into a new, explicitly chosen venv only."""
import hashlib,importlib.metadata,json,shutil,sys
from pathlib import Path
if sys.prefix==sys.base_prefix:raise SystemExit('Activate a dedicated virtualenv first; global installation is refused.')
root=Path(__file__).resolve().parent/'harbor-compat'
manifest=json.loads((root/'manifest.json').read_text())
if importlib.metadata.version('harbor')!=manifest['harbor_version']:raise SystemExit('Requires the pinned Harbor version.')
dist=importlib.metadata.distribution('harbor')
target=Path(dist.locate_file('harbor/environments/docker'))
if not target.resolve().is_relative_to(Path(sys.prefix).resolve()):raise SystemExit('Harbor must be installed in this virtualenv.')
for name,h in manifest['files'].items():
    p=root/name
    if hashlib.sha256(p.read_bytes()).hexdigest()!=h:raise SystemExit('Compatibility source hash mismatch')
    original=target/name;backup=original.with_suffix(original.suffix+'.before-sle-compat')
    if not backup.exists():shutil.copy2(original,backup)
    shutil.copy2(p,original)
print('Installed the captured Harbor 0.24.0 Docker bridge compatibility files in',sys.prefix)
