"""Start Fiji with verified components and a fresh Java preference home."""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import tempfile


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--root", type=Path, required=True)
    p.add_argument("--check-manifest", action="store_true")
    a = p.parse_args()
    installer = Path(__file__).with_name("fiji-install.py")
    if not installer.exists():
        installer = Path(__file__).with_name("install.py")
    spec = importlib.util.spec_from_file_location("fiji_bundle_verifier", installer)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    manifest = module.verify(a.root)
    if a.check_manifest:
        print("ImageJ " + manifest["components"]["ImageJ"] + "; manifest verified")
        return 0
    # ImageJ and Java preference roots are isolated per invocation. The immutable
    # application/model files remain in the supplied offline installation.
    with tempfile.TemporaryDirectory(prefix="scientific-fiji-") as temporary:
        private = Path(temporary)
        env = dict(os.environ)
        env["JAVA_TOOL_OPTIONS"] = (
            "-Duser.home=" + str(private) + " -Djava.util.prefs.userRoot=" +
            str(private / "java-user") + " -Djava.util.prefs.systemRoot=" +
            str(private / "java-system"))
        receipt = {"components": manifest["components"], "preferences": str(private),
                   "offline_model": manifest["stardist_he_model"]}
        (private / "launch.json").write_text(json.dumps(receipt))
        return subprocess.run([str(a.root / manifest["launcher"])],
                              cwd=a.root, env=env).returncode


if __name__ == "__main__":
    raise SystemExit(main())
