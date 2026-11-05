"""Reads the reference data shipped inside the package."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

DATA_DIR = Path(__file__).parent / "data"


def load_yaml(relative_path: str) -> dict[str, Any]:
    with (DATA_DIR / relative_path).open(encoding="utf-8") as handle:
        return yaml.safe_load(handle)
