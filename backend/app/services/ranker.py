from __future__ import annotations

from pathlib import PurePosixPath


DEPENDENCY_FILES = {
    "package.json",
    "pyproject.toml",
    "requirements.txt",
    "poetry.lock",
    "pnpm-lock.yaml",
    "yarn.lock",
}

ENTRY_NAMES = {
    "app.py",
    "main.py",
    "server.py",
    "manage.py",
    "index.js",
    "index.ts",
    "main.js",
    "main.ts",
    "main.jsx",
    "main.tsx",
    "app.jsx",
    "app.tsx",
}


def score_file(path: str, content: str, imports: list[str], symbols: list[str]) -> float:
    normalized = path.replace("\\", "/")
    name = PurePosixPath(normalized).name
    parts = PurePosixPath(normalized).parts
    score = 0.0

    if name.lower().startswith("readme"):
        score += 100
    if name in DEPENDENCY_FILES:
        score += 82
    if name.lower() in ENTRY_NAMES:
        score += 76
    if "src" in parts or "app" in parts:
        score += 18
    if "test" in normalized.lower() or "spec" in normalized.lower():
        score -= 8
    if "config" in name.lower() or name.startswith("vite.config"):
        score += 32
    if "__main__" in content or "if __name__" in content:
        score += 28
    if "FastAPI(" in content or "createRoot(" in content or "ReactDOM" in content:
        score += 35

    score += min(len(imports), 12) * 2.2
    score += min(len(symbols), 12) * 1.5
    score += min(len(content), 8000) / 8000
    return round(score, 2)


def mark_core_files(files: list[dict], limit: int = 14) -> list[dict]:
    ranked = sorted(files, key=lambda item: item.get("importance", 0), reverse=True)
    core_paths = {item["path"] for item in ranked[:limit] if item.get("importance", 0) > 12}
    for file in files:
        file["is_core"] = file["path"] in core_paths
    return files

