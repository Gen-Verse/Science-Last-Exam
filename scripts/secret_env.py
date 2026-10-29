"""Read secret/.env (KEY=value per line) into the environment. Variables already set in the shell win."""
import os
from pathlib import Path


def load_secret_env(root):
    path = Path(root) / 'secret/.env'
    if not path.is_file():
        return []
    loaded = []
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        key, sep, value = line.removeprefix('export ').partition('=')
        key, value = key.strip(), value.strip().strip('"\'')
        if sep and key and value and key not in os.environ:
            os.environ[key] = value
            loaded.append(key)
    return loaded
