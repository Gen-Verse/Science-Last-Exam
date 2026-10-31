"""Task setup is executed by the authenticated environment adapter."""
import json
from pathlib import Path


def setup(environment):
    config = json.loads(Path(__file__).with_name("env.json").read_text())
    return environment.request("/setup", {"steps": config["setup"]})
