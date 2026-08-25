"""Lastar config.yaml og .env."""

import os
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent


def _load_dotenv():
    """Minimal .env-lesar. Unngår ein ekstra avhengigheit."""
    path = ROOT / ".env"
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        # Miljøvariablar frå GitHub Actions har forrang over .env.
        if key and key not in os.environ:
            os.environ[key] = value


def load_config():
    _load_dotenv()
    with open(ROOT / "config.yaml", "r", encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def env(name, default=""):
    return os.environ.get(name, default) or default
