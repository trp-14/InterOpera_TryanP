"""Load + validate firm config YAML (BUILD_PLAN.md Step 4).

This module only loads and validates — it doesn't touch the audit log
itself. Whoever calls it with a real run (Step 5's `run` command) is
responsible for recording the `config_loaded` audit event, the same way
`main.py`'s `cmd_ingest` — not `graph/builder.py` — records `graph_built`.
"""
from __future__ import annotations

import hashlib
from pathlib import Path

import yaml
from pydantic import ValidationError

from src.config.models import FirmConfig


class ConfigError(Exception):
    """Raised when a config file fails schema validation."""


def load_config(path: str | Path) -> FirmConfig:
    path = Path(path)
    raw_data = yaml.safe_load(path.read_text(encoding="utf-8"))

    try:
        return FirmConfig.model_validate(raw_data)
    except ValidationError as exc:
        raise ConfigError(f"invalid config at {path}:\n{exc}") from exc


def config_content_hash(path: str | Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


if __name__ == "__main__":
    root = Path(__file__).resolve().parents[2]
    for name in ("firm_a.yaml", "firm_b.yaml"):
        cfg = load_config(root / "config" / name)
        print(f"{name}: label={cfg.label!r} utilization.format={cfg.presentation.utilization.format!r} "
              f"figures={list(cfg.figures)}")
