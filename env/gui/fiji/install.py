"""Install a locally supplied, fully hashed Fiji bundle; never run the updater."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import tarfile
import tempfile

COMPONENTS = {
    "ImageJ": "1.54p", "StarDist": "0.3.0", "CSBDeep": "0.6.0",
    "ImageJ TensorFlow": "1.1.9", "TensorFlow": "1.12.0",
    "TrackMate": "8.1.6", "Bio-Formats": "8.5.0", "MorphoLibJ": "1.6.5",
}


def checksum(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def verify(folder):
    folder = Path(folder).resolve()
    manifest = json.loads((folder / "scientific-software-operation-manifest.json").read_text())
    if manifest["components"] != COMPONENTS:
        raise ValueError("Fiji component versions differ from the declared task environment")
    files = manifest["files"]
    if not isinstance(files, dict) or not files:
        raise ValueError("Bundle manifest must hash every installed file")
    actual = {str(p.relative_to(folder)) for p in folder.rglob("*")
              if p.is_file() and p.relative_to(folder).as_posix() != "scientific-software-operation-manifest.json"}
    if actual != set(files):
        raise ValueError("Bundle file inventory differs from its manifest")
    for relative, digest in files.items():
        path = folder / relative
        if path.is_symlink() or not path.resolve().is_relative_to(folder) or checksum(path) != digest:
            raise ValueError("Fiji bundle checksum mismatch: " + relative)
    for key in ("launcher", "stardist_he_model"):
        if manifest.get(key) not in files:
            raise ValueError("Bundle must include a hashed launcher and offline H&E model")
    return manifest


def install(archive, expected_sha256, destination, launcher):
    archive, destination, launcher = Path(archive), Path(destination), Path(launcher)
    if len(expected_sha256) != 64 or checksum(archive) != expected_sha256:
        raise ValueError("Fiji installation archive SHA-256 mismatch")
    if destination.exists() or launcher.exists():
        raise ValueError("Refuse to replace an existing application installation")
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=destination.parent) as temporary:
        work = Path(temporary)
        with tarfile.open(archive) as bundle:
            for member in bundle:
                target = (work / member.name).resolve()
                if not target.is_relative_to(work.resolve()) or not (member.isfile() or member.isdir()):
                    raise ValueError("Bundle must contain regular files/directories only")
            bundle.extractall(work, filter="data")
        verify(work)
        shutil.copytree(work, destination)
    runtime = destination.parent / "fiji-launch.py"
    shutil.copy2(Path(__file__).with_name("launch.py"), runtime)
    shutil.copy2(Path(__file__), destination.parent / "fiji-install.py")
    launcher.parent.mkdir(parents=True, exist_ok=True)
    import shlex
    launcher.write_text("#!/bin/sh\nexec python3 " + shlex.quote(str(runtime)) +
                        " --root " + shlex.quote(str(destination)) + ' "$@"\n')
    launcher.chmod(0o755)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--archive", type=Path, required=True)
    p.add_argument("--sha256", required=True)
    p.add_argument("--destination", type=Path, required=True)
    p.add_argument("--launcher", type=Path, required=True)
    a = p.parse_args()
    install(a.archive, a.sha256, a.destination, a.launcher)
