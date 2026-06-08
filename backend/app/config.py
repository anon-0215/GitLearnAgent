from __future__ import annotations

from dataclasses import dataclass
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


@dataclass(frozen=True)
class EmbeddingSettings:
    enabled: bool
    model_name_or_path: str
    device: str
    batch_size: int
    max_length: int
    normalize: bool
    cache_dir: Path
    query_prefix: str
    document_prefix: str


def get_embedding_settings() -> EmbeddingSettings:
    cache_dir = _env_path("EMBEDDING_CACHE_DIR", PROJECT_ROOT / "embedding_cache")
    return EmbeddingSettings(
        enabled=_env_bool("EMBEDDING_ENABLED", False),
        model_name_or_path=get_env_value("EMBEDDING_MODEL_NAME_OR_PATH", "BAAI/bge-m3").strip()
        or "BAAI/bge-m3",
        device=(get_env_value("EMBEDDING_DEVICE", "auto").strip() or "auto").lower(),
        batch_size=max(1, _env_int("EMBEDDING_BATCH_SIZE", 8)),
        max_length=max(1, _env_int("EMBEDDING_MAX_LENGTH", 8192)),
        normalize=_env_bool("EMBEDDING_NORMALIZE", True),
        cache_dir=cache_dir,
        query_prefix=get_env_value("EMBEDDING_QUERY_PREFIX", ""),
        document_prefix=get_env_value("EMBEDDING_DOCUMENT_PREFIX", ""),
    )


def _load_env_file(path: Path) -> None:
    for key, value in _read_env_file(path).items():
        os.environ.setdefault(key, value)


def _env_bool(key: str, default: bool) -> bool:
    value = get_env_value(key, str(default)).strip().lower()
    if value in {"1", "true", "yes", "on"}:
        return True
    if value in {"0", "false", "no", "off", ""}:
        return False
    return default


def _env_int(key: str, default: int) -> int:
    value = get_env_value(key, str(default)).strip()
    try:
        return int(value)
    except ValueError:
        return default


def _env_path(key: str, default: Path) -> Path:
    value = get_env_value(key, str(default)).strip()
    path = Path(value) if value else default
    if path.is_absolute():
        return path
    return PROJECT_ROOT / path


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
