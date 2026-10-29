"""Translate the container's mounted paths into the existing harness CLI."""
import os
from pathlib import Path
import sys


def arguments(argv, environ):
    args = list(argv or ["--help"])
    flags = {arg.split("=", 1)[0] for arg in args}
    if flags & {"--help", "-h"}:
        return args
    defaults = {
        "--model": environ.get("SCIENTIFIC_GUI_MODEL_CONFIG", "/config/model.json"),
        "--output": environ.get("SCIENTIFIC_GUI_OUTPUT_ROOT", "/runs"),
        "--accelerator": environ.get("SCIENTIFIC_GUI_ACCELERATOR", "tcg"),
    }
    if "--guest-url" not in flags:
        defaults["--images-root"] = environ.get("SCIENTIFIC_GUI_IMAGES_ROOT", "/images")
    for flag, value in defaults.items():
        if flag not in flags:
            args.extend([flag, value])
    return args


def main():
    for name in ("MODEL_API_KEY", "GUI_BRIDGE_TOKEN"):
        path = os.environ.get(name + "_FILE")
        if path:
            os.environ[name] = Path(path).read_text().strip()
    args = arguments(sys.argv[1:], os.environ)
    if not any(arg in {"--help", "-h", "--plan", "--list"} for arg in args):
        if len(os.environ.get("GUI_BRIDGE_TOKEN", "")) < 24:
            raise SystemExit("Set GUI_BRIDGE_TOKEN to the VM's deployment token (at least 24 characters)")
    os.execv(sys.executable, [sys.executable, "-B", "-m", "harness.run", *args])


if __name__ == "__main__":
    main()
