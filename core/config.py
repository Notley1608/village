import os
from typing import Any, Dict

import yaml

DEFAULT_PATH = os.path.join(os.path.dirname(__file__), "..", "config.yaml")


def load_config(path: str = DEFAULT_PATH) -> Dict[str, Any]:
    with open(path, "r") as f:
        return yaml.safe_load(f)


def residents(cfg: Dict[str, Any]) -> list:
    return cfg["residents"]


def resident_by_name(cfg: Dict[str, Any], name: str) -> Dict[str, Any]:
    for r in cfg["residents"]:
        if r["name"] == name:
            return r
    raise KeyError(name)