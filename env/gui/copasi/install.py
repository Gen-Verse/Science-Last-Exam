"""Install external COPASI controller dependencies in the selected host/guest venv.

Constraints are preserved from the upstream controller deployment. This is not
an all-transitive lock file and does not install VMware, the SDK or COPASI.
"""
import argparse
import subprocess
import sys

DEPENDENCIES = {
    "host": (
        "requests>=2.32,<3", "filelock>=3.13,<5", "Pillow>=10.4,<12",
        "lxml>=5,<7", "gymnasium==0.28.1", "numpy==1.26.4",
        "psutil>=5.9.6,<6", "tqdm>=4.65,<5", "jsonschema>=4,<5",
        "requests-toolbelt==1.0.0", "python-dotenv>=1,<2",
        "playwright>=1.40,<2", "PyDrive==1.3.1",
    ),
    "guest": (
        "PyAutoGUI==0.9.54", "pyperclip==1.9.0", "Pillow==10.4.0",
        "pywin32==308; sys_platform == 'win32'", "requests>=2.32,<3",
        "Flask>=2.3,<4", "lxml>=5,<7",
        "python3-xlib==0.15; sys_platform == 'linux'", "numpy==1.26.4",
    ),
}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("role", choices=DEPENDENCIES)
    parser.add_argument("--check", action="store_true", help="Print constraints without installing")
    args = parser.parse_args(argv)
    if args.check:
        print("\n".join(DEPENDENCIES[args.role]))
        return
    if sys.prefix == sys.base_prefix:
        parser.error("Create and activate an isolated COPASI venv before installing")
    subprocess.run([sys.executable, "-m", "pip", "install", *DEPENDENCIES[args.role]], check=True)


if __name__ == "__main__":
    main()
