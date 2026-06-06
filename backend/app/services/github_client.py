from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from pathlib import PurePosixPath
from typing import Any

from app.models import RepoFile, RepositorySnapshot


GITHUB_API = "https://api.github.com"
MAX_FILE_BYTES = 200_000
MAX_TEXT_FILES = 260

SKIP_PARTS = {
    ".git",
    ".github",
    ".idea",
    ".mypy_cache",
    ".next",
    ".pytest_cache",
    ".ruff_cache",
    ".tox",
    ".venv",
    "__pycache__",
    "build",
    "coverage",
    "dist",
    "node_modules",
    "target",
    "vendor",
}

TEXT_EXTENSIONS = {
    ".cjs",
    ".css",
    ".env",
    ".html",
    ".ini",
    ".js",
    ".json",
    ".jsx",
    ".md",
    ".mdx",
    ".py",
    ".rs",
    ".sh",
    ".toml",
    ".ts",
    ".tsx",
    ".txt",
    ".vue",
    ".yaml",
    ".yml",
}

IMPORTANT_FILENAMES = {
    "Dockerfile",
    "Makefile",
    "README",
    "LICENSE",
    "requirements.txt",
    "package.json",
    "pyproject.toml",
    "vite.config.ts",
    "vite.config.js",
}


def parse_github_url(url: str) -> tuple[str, str]:
    cleaned = url.strip()
    match = re.match(r"^(?:https?://)?github\.com/([^/\s]+)/([^/\s#?]+)", cleaned)
    if not match:
        raise ValueError("请输入有效的 GitHub 仓库地址，例如 https://github.com/owner/repo")
    owner = match.group(1)
    repo = match.group(2).removesuffix(".git")
    if not owner or not repo:
        raise ValueError("GitHub 仓库地址缺少 owner 或 repo")
    return owner, repo


def should_skip_path(path: str) -> bool:
    parts = [part for part in PurePosixPath(path).parts if part]
    lowered = {part.lower() for part in parts}
    if lowered.intersection(SKIP_PARTS):
        return True
    return any(part.startswith(".") and part not in {".env"} for part in parts)


def is_interesting_text_file(path: str, size: int) -> bool:
    if size > MAX_FILE_BYTES or should_skip_path(path):
        return False
    name = PurePosixPath(path).name
    suffix = PurePosixPath(path).suffix.lower()
    return suffix in TEXT_EXTENSIONS or name in IMPORTANT_FILENAMES


def fetch_repository(repo_url: str) -> RepositorySnapshot:
    owner, repo = parse_github_url(repo_url)
    metadata = _fetch_json(f"{GITHUB_API}/repos/{owner}/{repo}")
    default_branch = metadata.get("default_branch") or "main"
    branch = _fetch_json(
        f"{GITHUB_API}/repos/{owner}/{repo}/branches/{urllib.parse.quote(default_branch, safe='')}"
    )
    tree_sha = branch.get("commit", {}).get("commit", {}).get("tree", {}).get("sha") or default_branch
    tree_url = f"{GITHUB_API}/repos/{owner}/{repo}/git/trees/{tree_sha}?recursive=1"
    tree = _fetch_json(tree_url)
    files: list[RepoFile] = []

    for item in tree.get("tree", []):
        if item.get("type") != "blob":
            continue
        path = item.get("path", "")
        size = int(item.get("size") or 0)
        if not is_interesting_text_file(path, size):
            continue
        content = _fetch_raw_file(owner, repo, default_branch, path)
        if content is None:
            continue
        files.append(
            RepoFile(
                path=path,
                size=size,
                content=content,
                extension=PurePosixPath(path).suffix.lower(),
            )
        )
        if len(files) >= MAX_TEXT_FILES:
            break

    if not files:
        raise RuntimeError("没有找到可分析的文本文件，仓库可能过大、为空或不是公开仓库。")

    return RepositorySnapshot(
        repo_url=f"https://github.com/{owner}/{repo}",
        owner=owner,
        repo=repo,
        default_branch=default_branch,
        files=files,
    )


def _request(url: str) -> bytes:
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "GitLearnAgent/0.1",
    }
    token = os.getenv("GITHUB_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=25) as response:
            return response.read()
    except urllib.error.HTTPError as exc:
        message = exc.read().decode("utf-8", errors="ignore")
        raise RuntimeError(f"GitHub 请求失败 {exc.code}: {message[:300]}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"无法连接 GitHub: {exc.reason}") from exc


def _fetch_json(url: str) -> dict[str, Any]:
    return json.loads(_request(url).decode("utf-8"))


def _fetch_raw_file(owner: str, repo: str, branch: str, path: str) -> str | None:
    quoted_path = urllib.parse.quote(path, safe="/")
    quoted_branch = urllib.parse.quote(branch, safe="")
    url = f"https://raw.githubusercontent.com/{owner}/{repo}/{quoted_branch}/{quoted_path}"
    try:
        data = _request(url)
    except RuntimeError:
        return None
    if b"\x00" in data[:2000]:
        return None
    return data.decode("utf-8", errors="replace")
