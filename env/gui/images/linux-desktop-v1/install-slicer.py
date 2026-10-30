"""Install the SlicerBridge helper into a prepared Slicer guest image."""
from __future__ import annotations

import argparse
from pathlib import Path
import shutil


ROOT = Path(__file__).resolve().parent


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--install-root", type=Path, default=Path("/opt/scientific-software-operation"))
    parser.add_argument("--launcher", type=Path, default=Path("/usr/local/bin/scientific-software-operation-slicer"))
    args = parser.parse_args()
    args.install_root.mkdir(parents=True, exist_ok=True)
    helper = args.install_root / "slicer_bridge.py"
    shutil.copy2(ROOT / "hooks" / "slicer_bridge.py", helper)
    shutil.copy2(ROOT / "hooks" / "slicer_ready.py", args.install_root / "slicer_ready.py")
    helper.chmod(0o755)
    args.launcher.parent.mkdir(parents=True, exist_ok=True)
    args.launcher.write_text(
        "#!/bin/sh\n"
        "set -eu\n"
        f"exec /usr/bin/python3 {helper} \"$@\"\n",
        encoding="utf-8",
    )
    args.launcher.chmod(0o755)
    print(f"installed {helper} and {args.launcher}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
