"""Install one downloaded GRASS project, preserving its maps and canonical task path."""
import argparse
from pathlib import Path, PurePosixPath
import shutil
import stat
import tarfile
import tempfile
import zipfile


def destination(root, name):
    path = PurePosixPath(name)
    if path.is_absolute() or ".." in path.parts or "\\" in name:
        raise ValueError("Unsafe archive member: " + name)
    return root.joinpath(*path.parts)


def unpack(archive, root):
    if zipfile.is_zipfile(archive):
        with zipfile.ZipFile(archive) as z:
            for member in z.infolist():
                target = destination(root, member.filename)
                if stat.S_ISLNK(member.external_attr >> 16):
                    raise ValueError("Archive symlinks are not accepted")
                if member.is_dir():
                    target.mkdir(parents=True, exist_ok=True)
                else:
                    target.parent.mkdir(parents=True, exist_ok=True)
                    with z.open(member) as source, target.open("wb") as out:
                        shutil.copyfileobj(source, out)
    else:
        with tarfile.open(archive) as tar:
            for member in tar:
                target = destination(root, member.name)
                if member.isdir():
                    target.mkdir(parents=True, exist_ok=True)
                elif member.isfile():
                    target.parent.mkdir(parents=True, exist_ok=True)
                    with tar.extractfile(member) as source, target.open("wb") as out:
                        shutil.copyfileobj(source, out)
                else:
                    raise ValueError("Only regular files and directories are accepted")


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--archive", type=Path, required=True)
    p.add_argument("--database", type=Path, default=Path("/home/user/grassdata"))
    p.add_argument("--name", required=True, choices=["natural_earth_dataset", "grassdata_piemonte_utm32n_wgs84_grass7"])
    a = p.parse_args()
    target = a.database / a.name
    if not a.archive.is_file() or target.exists():
        p.error("Supply an archive and a destination project that does not exist")
    a.database.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=a.database) as directory:
        staging = Path(directory)
        unpack(a.archive, staging)
        projects = [f.parent.parent for f in staging.rglob("PERMANENT/WIND")]
        if len(projects) != 1:
            raise ValueError("Expected exactly one GRASS project with PERMANENT/WIND")
        if not (projects[0] / "PERMANENT/PROJ_INFO").is_file():
            raise ValueError("Project has no projection information")
        for lock in projects[0].glob("*/.gislock"):
            lock.unlink()
        if projects[0] == staging:
            # Keep TemporaryDirectory's cleanup root separate from the installed data.
            target.mkdir()
            for child in list(staging.iterdir()):
                shutil.move(str(child), target / child.name)
        else:
            projects[0].rename(target)
    print("Installed", target)
    print("Use GRASS g.list to verify task layers; archive structure is not scientific validation.")


if __name__ == "__main__":
    main()
