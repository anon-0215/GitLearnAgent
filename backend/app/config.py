from __future__ import annotations

import os
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = Path(__file__).resolve().parents[1]


def load_environment() -> None:
    """Load simple KEY=VALUE pairs from project .env files.

    Existing process environment values win over .env values, so users can still
    override settings from the command line when they want to.
    """
    for env_path in (PROJECT_ROOT / ".env", BACKEND_ROOT / ".env"):
        if env_path.exists():
            _load_env_file(env_path)


def get_env_value(key: str, default: str = "") -> str:
    for env_path in (BACKEND_ROOT / ".env", PROJECT_ROOT / ".env"):
        if not env_path.exists():
            continue
        values = _read_env_file(env_path)
        if key in values:
            return values[key]
    return os.getenv(key, default)


def _load_env_file(path: Path) -> None:
    for key, value in _read_env_file(path).items():
        os.environ.setdefault(key, value)


def _read_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if " #" in value:
            value = value.split(" #", 1)[0].strip()
        if key:
            values[key] = value
    return values
