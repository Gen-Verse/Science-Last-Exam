"""Install a locally downloaded, checksum-verified FreeCAD AppImage in a guest."""
import argparse
import hashlib
from pathlib import Path
import shlex
import shutil
import subprocess
import tempfile


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--appimage", type=Path, required=True)
    p.add_argument("--sha256", required=True, help="SHA-256 from the publisher's release checksum")
    p.add_argument("--prefix", type=Path, required=True)
    p.add_argument("--bin-dir", type=Path, default=Path.home() / ".local/bin")
    p.add_argument("--launcher-name", required=True, choices=["freecad-1.1", "freecad-0.21"],
                   help="Versioned launcher; both versions can coexist in one guest")
    a = p.parse_args()
    if not a.appimage.is_file() or a.prefix.exists() or (a.bin_dir / a.launcher_name).exists():
        p.error("Supply an existing AppImage and unused installation/wrapper paths")
    with a.appimage.open("rb") as stream:
        digest = hashlib.file_digest(stream, "sha256").hexdigest() if hasattr(hashlib, "file_digest") else None
    if digest is None:  # Ubuntu 22.04 guest Python 3.10
        h = hashlib.sha256()
        with a.appimage.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""): h.update(chunk)
        digest = h.hexdigest()
    if digest != a.sha256.lower():
        p.error("Checksum mismatch; refusing to execute installer")
    a.prefix = a.prefix.resolve()
    a.prefix.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=a.prefix.parent) as directory:
        staging = Path(directory)
        installer = staging / "installer.AppImage"
        shutil.copyfile(a.appimage, installer)
        installer.chmod(0o700)
        subprocess.run([str(installer), "--appimage-extract"], cwd=staging, check=True)
        extracted = staging / "squashfs-root"
        if not (extracted / "AppRun").exists():
            raise RuntimeError("Installer did not produce AppRun")
        extracted.rename(a.prefix)
    a.bin_dir.mkdir(parents=True, exist_ok=True)
    wrapper = a.bin_dir / a.launcher_name
    wrapper.write_text("#!/bin/sh\nunset QT_PLUGIN_PATH QML2_IMPORT_PATH LD_LIBRARY_PATH PYTHONPATH PYTHONHOME\n" +
                       'export XDG_CONFIG_HOME="$HOME/.config/scientific-software-operation/' + a.launcher_name + '"\n' +
                       'export XDG_DATA_HOME="$HOME/.local/share/scientific-software-operation/' + a.launcher_name + '"\n' +
                       'export XDG_CACHE_HOME="$HOME/.cache/scientific-software-operation/' + a.launcher_name + '"\n' +
                       'export FREECAD_USER_HOME="$XDG_CONFIG_HOME/FreeCAD"\n' +
                       'export FREECAD_USER_DATA="$XDG_DATA_HOME/FreeCAD"\n' +
                       'export FREECAD_USER_TEMP="$XDG_CACHE_HOME/FreeCAD"\n' +
                       'mkdir -p "$FREECAD_USER_HOME" "$FREECAD_USER_DATA" "$FREECAD_USER_TEMP"\nexec ' +
                       shlex.quote(str(a.prefix / "AppRun")) + ' "$@"\n')
    wrapper.chmod(0o755)
    print("Installed FreeCAD launcher:", wrapper)
    print("Add this bin directory to the desktop PATH. Application version and GUI behavior still need checking.")


if __name__ == "__main__":
    main()
