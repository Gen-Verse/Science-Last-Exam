"""Environment recipes live in env/gui; staged guests keep a self-contained bundle."""
from pathlib import Path
COMPONENT=Path(__file__).resolve().parents[1]

def environment_root():
    staged=COMPONENT/'env'
    return staged if staged.is_dir() else COMPONENT.parents[2]/'env/gui'

def image_root():
    staged=COMPONENT/'harness/images'
    return staged if staged.is_dir() else environment_root()/'images'
