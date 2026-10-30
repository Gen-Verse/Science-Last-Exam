"""Bundle already-downloaded, verified COPASI binaries for the QEMU recipe."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tarfile
import tempfile

SCRIPT=Path(__file__).resolve()
MANIFEST_CANDIDATES=(SCRIPT.parents[3]/'harness/components/scientific_software_operation/harness/desktop_compat/native/manifest.json',
                     SCRIPT.parents[2]/'harness/desktop_compat/native/manifest.json')


def main():
    p=argparse.ArgumentParser();p.add_argument('--appimage',type=Path,required=True);p.add_argument('--appimage-sha256',required=True)
    p.add_argument('--se',type=Path,required=True);p.add_argument('--se-sha256',required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args()
    if a.output.exists():p.error('Output already exists')
    for path,expected in [(a.appimage,a.appimage_sha256),(a.se,a.se_sha256)]:
        with path.open('rb') as f:actual=hashlib.file_digest(f,'sha256').hexdigest()
        if actual!=expected.lower():p.error('Installer checksum mismatch: '+path.name)
    with tempfile.TemporaryDirectory(prefix='copasi-apps-') as directory:
        root=Path(directory);app=root/'installer.AppImage';shutil.copyfile(a.appimage,app);app.chmod(0o755)
        subprocess.run([str(app),'--appimage-extract'],cwd=root,check=True)
        manifest_path=next((path for path in MANIFEST_CANDIDATES if path.is_file()),None)
        if manifest_path is None:raise FileNotFoundError('COPASI native runtime manifest is missing')
        manifest=json.loads(manifest_path.read_text())
        for name,expected in manifest['runtime_libraries'].items():
            if hashlib.sha256((root/'squashfs-root/usr/lib'/name).read_bytes()).hexdigest()!=expected:raise RuntimeError('Native observer requires the recorded Qt libraries: '+name)
        se=root/'CopasiSE-4.47.309';shutil.copyfile(a.se,se);se.chmod(0o755)
        with a.output.open('xb') as stream,tarfile.open(fileobj=stream,mode='w:gz') as archive:
            archive.add(root/'squashfs-root',arcname='squashfs-root');archive.add(se,arcname=se.name)
    with a.output.open('rb') as f:print(json.dumps({'output':str(a.output),'sha256':hashlib.file_digest(f,'sha256').hexdigest(),'gui_verified':False}))


if __name__=='__main__':main()
