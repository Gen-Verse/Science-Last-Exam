"""Install the official KiCad 10.0.2 AppImage and its bundled grading interpreter."""
import argparse
import hashlib
from pathlib import Path
import shlex
import shutil
import subprocess
import tempfile


def install_launchers(prefix, bin_dir):
    prefix, bin_dir = Path(prefix).resolve(), Path(bin_dir)
    python = prefix / 'bin/python3.11'
    for relative in ['AppRun', 'bin/kicad', 'bin/kicad-cli', 'bin/pcbnew', 'bin/eeschema', 'bin/python3.11']:
        if not (prefix / relative).is_file():
            raise ValueError('Missing KiCad runtime component: ' + relative)
    names = {'kicad': ['kicad'], 'kicad-cli': ['kicad-cli'], 'pcbnew': ['pcbnew'], 'eeschema': ['eeschema'],
             'kicad-python': None}
    if any((bin_dir / name).exists() for name in names):
        raise ValueError('KiCad launcher already exists; inspect the installation')
    # The bundled Python has its own pcbnew binding and shared-library launcher.
    version = subprocess.run([str(python), '-c', 'import pcbnew; print(pcbnew.GetBuildVersion())'],
                             check=True, capture_output=True, text=True, timeout=120).stdout.strip()
    if version != '10.0.2':
        raise ValueError('Expected KiCad 10.0.2, got ' + version)
    cli_version = subprocess.run([str(prefix / 'bin/kicad-cli'), 'version'],
                                 check=True, capture_output=True, text=True, timeout=30).stdout.strip()
    if cli_version != version:
        raise ValueError('KiCad CLI and pcbnew bindings must both be 10.0.2')
    bin_dir.mkdir(parents=True, exist_ok=True)
    for name, arguments in names.items():
        command = [str(python)] if arguments is None else [str(prefix / 'AppRun'), *arguments]
        wrapper = bin_dir / name
        wrapper.write_text('#!/bin/sh\nunset LD_LIBRARY_PATH PYTHONHOME PYTHONPATH QT_PLUGIN_PATH\nexec ' +
                           shlex.join(command) + ' "$@"\n')
        wrapper.chmod(0o755)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--appimage', type=Path, required=True, help='Extract the official download tar on the host first')
    parser.add_argument('--sha256', required=True, help='Record the local digest; use a publisher checksum if available')
    parser.add_argument('--prefix', type=Path, required=True)
    parser.add_argument('--bin-dir', type=Path, default=Path.home() / '.local/bin')
    args = parser.parse_args()
    if not args.appimage.is_file() or args.prefix.exists():
        parser.error('Supply a local AppImage and an unused installation directory')
    digest = hashlib.sha256()
    with args.appimage.open('rb') as stream:
        for data in iter(lambda: stream.read(1024 * 1024), b''): digest.update(data)
    if digest.hexdigest() != args.sha256.lower():
        parser.error('Checksum mismatch; refusing to execute installer')
    args.prefix = args.prefix.resolve()
    args.prefix.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=args.prefix.parent) as directory:
        stage = Path(directory)
        installer = stage / 'installer.AppImage'
        shutil.copyfile(args.appimage, installer)
        installer.chmod(0o700)
        subprocess.run([str(installer), '--appimage-extract'], cwd=stage, check=True)
        extracted = stage / 'squashfs-root'
        if extracted.is_symlink(): extracted = extracted.resolve()
        if not extracted.is_relative_to(stage) or not (extracted / 'AppRun').is_file():
            raise ValueError('AppImage did not produce a local application directory')
        extracted.rename(args.prefix)
    install_launchers(args.prefix, args.bin_dir)
    print('Installed KiCad 10.0.2 GUI launchers and kicad-python; GUI validation still required.')


if __name__ == '__main__':
    main()
