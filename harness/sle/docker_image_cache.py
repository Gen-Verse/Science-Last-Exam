"""Reuse immutable Docker build inputs across Harbor trials and run directories.

Only the single-Dockerfile main-service layout is cached. Custom compose files
and unresolved dynamic base images retain Harbor's normal build behaviour.
"""
import asyncio
from contextlib import asynccontextmanager
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess

from harbor.environments.base import ExecResult


SCHEMA = 1
IMAGE_REPOSITORY = "sle-cache"


def inspect_image(reference):
    result = subprocess.run(
        ["docker", "image", "inspect", reference], capture_output=True,
        text=True, timeout=30,
    )
    if result.returncode:
        return None
    return json.loads(result.stdout)[0]


def archive_directory():
    configured = os.environ.get("SLE_DOCKER_IMAGE_ARCHIVE_DIR")
    if configured:
        return Path(configured)
    # Run snapshots share the repository archive on its data filesystem.
    for parent in Path(__file__).resolve().parents:
        if (parent / "task").is_dir() and (parent / "harness").is_dir() and (parent / "env").is_dir():
            return parent / ".local/docker-image-archives"
    return None


def restore_archived_image(spec):
    directory = archive_directory()
    receipt = directory / (spec["key"] + ".json") if directory else None
    if receipt is None or not receipt.exists():
        return None
    metadata = json.loads(receipt.read_text())
    if metadata.get("key") != spec["key"] or metadata.get("image") != spec["image"]:
        raise RuntimeError("Docker image archive key mismatch")
    name = metadata["archive"]
    if Path(name).name != name:
        raise RuntimeError("Docker image archive must be inside the archive directory")
    path = directory / name
    with path.open("rb") as stream:
        actual = hashlib.file_digest(stream, "sha256").hexdigest()
    if actual != metadata["archive_sha256"]:
        raise RuntimeError("Docker image archive checksum mismatch")
    result = subprocess.run(["docker", "image", "load", "-i", str(path)],
                            capture_output=True, text=True, timeout=3600)
    if result.returncode:
        raise RuntimeError("Docker image archive restore failed: " + result.stderr[-1000:])
    image = inspect_image(spec["image"])
    if not image or image["Id"] != metadata["image_id"]:
        raise RuntimeError("Restored Docker image identity mismatch")
    return image


def context_digest(directory):
    """Hash bytes, relative paths and permissions, never staging paths or mtimes.

    Hashing ignored files too is deliberately conservative: it can cause a
    cache miss, but cannot reuse an image after an unaccounted input changes.
    Symlinks are archived as links by Docker, so hash the link, not its target.
    """
    digest = hashlib.sha256()
    directory = Path(directory)
    for path in sorted(directory.rglob("*")):
        info = path.lstat()
        relative = path.relative_to(directory).as_posix()
        if stat.S_ISLNK(info.st_mode):
            entry = [relative, "link", os.readlink(path)]
        elif stat.S_ISDIR(info.st_mode):
            entry = [relative, "directory", stat.S_IMODE(info.st_mode)]
        elif stat.S_ISREG(info.st_mode):
            content = hashlib.sha256()
            with path.open("rb") as stream:
                for block in iter(lambda: stream.read(1024 * 1024), b""):
                    content.update(block)
            entry = [relative, "file", stat.S_IMODE(info.st_mode), content.hexdigest()]
        else:
            raise ValueError("Unsupported special file in Docker context: " + relative)
        digest.update(json.dumps(entry, separators=(",", ":")).encode() + b"\n")
    return digest.hexdigest()


def external_images(dockerfile, resolver=inspect_image):
    """Pin mutable external FROM/COPY tags to the local image actually used."""
    stages, references = set(), set()
    text = re.sub(r"\\\r?\n", " ", dockerfile)
    for line in text.splitlines():
        match = re.match(r"\s*FROM\s+(?:--platform=\S+\s+)?(\S+)(?:\s+AS\s+(\S+))?", line, re.I)
        if match:
            reference, alias = match.groups()
            if reference.lower() not in stages and reference.lower() != "scratch":
                references.add(reference)
            if alias:
                stages.add(alias.lower())
        elif re.match(r"\s*(COPY|ADD)\s", line, re.I):
            match = re.search(r"--from=(\S+)", line)
            if match and not match[1].isdigit() and match[1].lower() not in stages:
                references.add(match[1])
    resolved = {}
    for reference in sorted(references):
        if "$" in reference:
            raise ValueError("Dynamic external image reference cannot be cached: " + reference)
        if "@sha256:" in reference or reference.startswith("sha256:"):
            resolved[reference] = reference
        else:
            image = resolver(reference)
            if image is None:
                raise ValueError("External image not yet available locally: " + reference)
            resolved[reference] = image["Id"]
    return resolved


def build_spec(directory, dockerfile, build_options=None, resolver=inspect_image):
    source = Path(dockerfile).read_text()
    options = dict(build_options or {})
    # Absolute paths are staging details; their content is hashed separately.
    options.pop("context", None)
    options.pop("dockerfile", None)
    recipe = {
        "schema": SCHEMA,
        "context_sha256": context_digest(directory),
        "dockerfile_sha256": hashlib.sha256(source.encode()).hexdigest(),
        "build_options": options,
        "external_images": external_images(source, resolver),
        "platform": os.environ.get("DOCKER_DEFAULT_PLATFORM", "daemon-default"),
    }
    key = hashlib.sha256(json.dumps(recipe, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    # Do not persist build args/proxy credentials in receipts.
    return {
        "key": key, "image": IMAGE_REPOSITORY + ":" + key,
        "context_sha256": recipe["context_sha256"],
        "dockerfile_sha256": recipe["dockerfile_sha256"],
        "external_images": recipe["external_images"],
    }


@asynccontextmanager
async def image_build_lock(key):
    directory = Path(os.environ.get("SLE_DOCKER_IMAGE_CACHE_LOCK_DIR", "/tmp/sle-image-cache-locks"))
    directory.mkdir(parents=True, exist_ok=True)
    with (directory / (key + ".lock")).open("a") as lock:
        while True:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                await asyncio.sleep(0.1)
        try:
            yield
        finally:
            fcntl.flock(lock, fcntl.LOCK_UN)


class CachedDockerBuildMixin:
    async def start(self, force_build=False):
        self._cache_force_build = force_build
        self._cache_starting = True
        try:
            return await super().start(force_build=force_build)
        finally:
            lock = getattr(self, '_held_cache_build_lock', None)
            if lock is not None:
                await lock.__aexit__(None, None, None)
                self._held_cache_build_lock = None
            self._cache_starting = False

    @asynccontextmanager
    async def _build_and_start_lock(self, key):
        lock = image_build_lock(key)
        await lock.__aenter__()
        if getattr(self, '_cache_starting', False):
            # An archiver must not remove the image between build/restore and
            # compose up. The container reference protects it after start.
            self._held_cache_build_lock = lock
            yield
        else:
            try:
                yield
            finally:
                await lock.__aexit__(None, None, None)

    def _cache_compose_paths(self, paths):
        if (os.environ.get("SLE_DOCKER_IMAGE_CACHE", "1") == "0"
                or self._use_prebuilt or self._uses_compose
                or getattr(self, "_is_windows_container", False)
                or not (self.environment_dir / "Dockerfile").is_file()):
            return paths
        if not hasattr(self, "_cached_build_spec"):
            build = {"context": str(self.environment_dir), "dockerfile": str(self.environment_dir / "Dockerfile")}
            for path in paths:
                if path.suffix == ".json":
                    value = json.loads(path.read_text()).get("services", {}).get("main", {}).get("build", {})
                    if isinstance(value, dict):
                        build.update(value)
            try:
                self._cached_build_spec = build_spec(self.environment_dir, build["dockerfile"], build)
            except ValueError as exc:
                self._cached_build_spec = None
                self.logger.info("Docker image cache unavailable: %s", exc)
        spec = self._cached_build_spec
        if spec is None:
            return paths
        directory = self.trial_paths.trial_dir / "environment-build" / self.session_id
        directory.mkdir(parents=True, exist_ok=True)
        override = directory / "image-cache-compose.json"
        override.write_text(json.dumps({"services": {"main": {
            "image": spec["image"], "pull_policy": "never",
            "build": {"labels": {"io.sle.build-key": spec["key"]}},
        }}}, indent=2) + "\n")
        self._env_vars.main_image_name = spec["image"]
        return [*paths, override]

    def _image_cache_receipt(self, action, image):
        path = self.trial_paths.trial_dir / "environment-build" / self.session_id / "image-cache.json"
        path.write_text(json.dumps({
            **self._cached_build_spec, "action": action, "image_id": image["Id"],
            "force_build": getattr(self, "_cache_force_build", False),
        }, indent=2) + "\n")

    async def _run_docker_compose_command(self, command, *args, **kwargs):
        # Populate the content key from the final adapted compose inputs.
        self._docker_compose_paths
        spec = getattr(self, "_cached_build_spec", None)
        if spec is None:
            return await super()._run_docker_compose_command(command, *args, **kwargs)
        if command == ["build"]:
            async with self._build_and_start_lock(spec["key"]):
                image = await asyncio.to_thread(inspect_image, spec["image"])
                if image and not getattr(self, "_cache_force_build", False):
                    self._image_cache_receipt("reused", image)
                    self.logger.info("Reusing Docker image %s", spec["image"])
                    return ExecResult(return_code=0, stdout="Cached image: " + spec["image"], stderr="")
                if not getattr(self, "_cache_force_build", False):
                    image = await asyncio.to_thread(restore_archived_image, spec)
                    if image:
                        self._image_cache_receipt("restored", image)
                        self.logger.info("Restored archived Docker image %s", spec["image"])
                        return ExecResult(return_code=0, stdout="Restored image: " + spec["image"], stderr="")
                result = await super()._run_docker_compose_command(command, *args, **kwargs)
                image = await asyncio.to_thread(inspect_image, spec["image"])
                if image is None:
                    raise RuntimeError("Docker build did not create the expected cache image")
                self._image_cache_receipt("built", image)
                return result
        command = list(command)
        if command and command[0] == "up" and "--no-build" not in command:
            command.append("--no-build")
        if command and command[0] == "down" and "--rmi" in command:
            index = command.index("--rmi")
            del command[index:index + 2]
        return await super()._run_docker_compose_command(command, *args, **kwargs)


from harbor.environments.docker.docker import DockerEnvironment as _HarborDockerEnvironment


class CachedDockerEnvironment(CachedDockerBuildMixin, _HarborDockerEnvironment):
    """The same cache for the regular Harbor network backend."""
    @property
    def _docker_compose_paths(self):
        return self._cache_compose_paths(super()._docker_compose_paths)
