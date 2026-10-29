"""Run Harbor with the repository's opt-in Docker gateway compatibility layer."""
import os
import runpy


def main():
    if os.environ.get("SLE_NETWORK_PROFILE") == "offline-agent":
        from sle.network_profile import install
        install()
    if os.environ.get("SLE_DOCKER_STATIC_NETWORK") == "1":
        from harbor.environments.docker import docker
        from sle.docker_static import StaticNetworkDockerEnvironment
        docker.DockerEnvironment = StaticNetworkDockerEnvironment
    elif os.name == "posix" and os.environ.get("SLE_DOCKER_IMAGE_CACHE", "1") != "0":
        from harbor.environments.docker import docker
        from sle.docker_image_cache import CachedDockerEnvironment
        docker.DockerEnvironment = CachedDockerEnvironment
    if os.environ.get("SLE_DOCKER_EXEC_RECEIPT") == "1":
        from harbor.environments.docker.docker import DockerEnvironment
        from exec_receipt import execute

        # The gateway may acknowledge attached exec before the process finishes.
        # Use its exit receipt for both agent commands and separate verifiers.
        DockerEnvironment._compose_exec = execute
    runpy.run_module("harbor.cli.main", run_name="__main__")


if __name__ == "__main__":
    main()
