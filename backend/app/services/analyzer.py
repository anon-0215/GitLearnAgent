from __future__ import annotations

import ast
import json
import re
from collections import Counter, defaultdict
from pathlib import PurePosixPath
from typing import Any

from app.models import RepositorySnapshot
from app.services.ranker import mark_core_files, score_file


LANGUAGE_BY_EXT = {
    ".py": "Python",
    ".js": "JavaScript",
    ".jsx": "JavaScript",
    ".ts": "TypeScript",
    ".tsx": "TypeScript",
    ".json": "JSON",
    ".md": "Markdown",
    ".toml": "TOML",
    ".yaml": "YAML",
    ".yml": "YAML",
    ".css": "CSS",
    ".html": "HTML",
}


def analyze_snapshot(snapshot: RepositorySnapshot) -> dict[str, Any]:
    files = [_analyze_file(file.to_dict()) for file in snapshot.files]
    files = mark_core_files(files)
    frameworks = _detect_frameworks(files)
    primary_language = _primary_language(files)
    modules = _build_modules(files)
    tree = _build_tree(snapshot.repo, files)
    start_commands = _extract_start_commands(files)
    readme_excerpt = _readme_excerpt(files)

    return {
        "repo_url": snapshot.repo_url,
        "owner": snapshot.owner,
        "repo": snapshot.repo,
        "default_branch": snapshot.default_branch,
        "primary_language": primary_language,
        "frameworks": frameworks,
        "stats": {
            "file_count": len(files),
            "core_file_count": sum(1 for file in files if file.get("is_core")),
            "total_text_bytes": sum(int(file.get("size", 0)) for file in files),
        },
        "tree": tree,
        "files": _public_file_list(files),
        "modules": modules,
        "dependency_edges": _dependency_edges(modules),
        "start_commands": start_commands,
        "readme_excerpt": readme_excerpt,
        "overview": _build_overview(snapshot.repo, primary_language, frameworks, modules),
    }


def _analyze_file(file: dict[str, Any]) -> dict[str, Any]:
    path = file["path"]
    content = file.get("content", "")
    extension = PurePosixPath(path).suffix.lower()
    language = LANGUAGE_BY_EXT.get(extension, "Text")
    imports: list[str] = []
    exports: list[str] = []
    symbols: list[str] = []

    if extension == ".py":
        imports, symbols = _analyze_python(content)
    elif extension in {".js", ".jsx", ".ts", ".tsx"}:
        imports, exports, symbols = _analyze_jsts(content)

    file.update(
        {
            "extension": extension,
            "language": language,
            "imports": imports,
            "exports": exports,
            "symbols": symbols,
            "summary": _summarize_file(path, content, symbols),
        }
    )
    file["importance"] = score_file(path, content, imports, symbols)
    return file


def _analyze_python(content: str) -> tuple[list[str], list[str]]:
    imports: list[str] = []
    symbols: list[str] = []
    try:
        tree = ast.parse(content)
    except SyntaxError:
        return imports, symbols
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.extend(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                imports.append(node.module.split(".")[0])
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            symbols.append(node.name)
    return sorted(set(imports)), symbols[:40]


def _analyze_jsts(content: str) -> tuple[list[str], list[str], list[str]]:
    import_matches = re.findall(r"import\s+(?:[^'\"]+\s+from\s+)?['\"]([^'\"]+)['\"]", content)
    require_matches = re.findall(r"require\(['\"]([^'\"]+)['\"]\)", content)
    export_matches = re.findall(r"export\s+(?:default\s+)?(?:function|class|const|let|var)?\s*([A-Za-z0-9_]*)", content)
    function_matches = re.findall(r"(?:function|class)\s+([A-Za-z0-9_]+)", content)
    arrow_matches = re.findall(r"const\s+([A-Za-z0-9_]+)\s*=\s*(?:\([^)]*\)|[A-Za-z0-9_]+)\s*=>", content)
    imports = sorted(set(import_matches + require_matches))
    exports = [item for item in export_matches if item]
    symbols = (function_matches + arrow_matches + exports)[:40]
    return imports, exports, symbols


def _detect_frameworks(files: list[dict[str, Any]]) -> list[str]:
    frameworks: set[str] = set()
    package = _file_content(files, "package.json")
    if package:
        try:
            data = json.loads(package)
            deps = {**data.get("dependencies", {}), **data.get("devDependencies", {})}
            markers = {
                "react": "React",
                "vite": "Vite",
                "next": "Next.js",
                "express": "Express",
                "vue": "Vue",
                "svelte": "Svelte",
            }
            for key, label in markers.items():
                if key in deps:
                    frameworks.add(label)
        except json.JSONDecodeError:
            pass

    python_deps = "\n".join(
        file.get("content", "")
        for file in files
        if PurePosixPath(file["path"]).name in {"requirements.txt", "pyproject.toml"}
    ).lower()
    for marker, label in {
        "fastapi": "FastAPI",
        "flask": "Flask",
        "django": "Django",
        "streamlit": "Streamlit",
        "pytest": "Pytest",
    }.items():
        if marker in python_deps:
            frameworks.add(label)

    for file in files:
        content = file.get("content", "")
        if "FastAPI(" in content:
            frameworks.add("FastAPI")
        if "createRoot(" in content or "ReactDOM" in content:
            frameworks.add("React")
        if "defineConfig" in content and "vite" in content.lower():
            frameworks.add("Vite")

    return sorted(frameworks)


def _primary_language(files: list[dict[str, Any]]) -> str:
    counts = Counter(
        file.get("language", "Text")
        for file in files
        if file.get("language") not in {"Markdown", "JSON", "TOML", "YAML", "Text"}
    )
    return counts.most_common(1)[0][0] if counts else "Unknown"


def _build_modules(files: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for file in files:
        path = PurePosixPath(file["path"])
        if path.name.lower().startswith("readme") or path.suffix.lower() == ".md":
            key = "docs"
        elif path.name in {"package.json", "pyproject.toml", "requirements.txt"}:
            key = "project-config"
        elif len(path.parts) > 1:
            key = path.parts[0]
        else:
            key = "root"
        grouped[key].append(file)

    modules = []
    for name, group_files in sorted(grouped.items()):
        top_files = sorted(group_files, key=lambda item: item.get("importance", 0), reverse=True)[:8]
        modules.append(
            {
                "name": name,
                "responsibility": _module_responsibility(name, top_files),
                "files": [file["path"] for file in top_files],
                "depends_on": _module_dependencies(name, top_files, grouped.keys()),
            }
        )
    return modules


def _module_responsibility(name: str, files: list[dict[str, Any]]) -> str:
    names = "、".join(PurePosixPath(file["path"]).name for file in files[:3])
    if name == "docs":
        return f"说明文档与项目背景，建议先读 {names}。"
    if name == "project-config":
        return f"依赖、脚本和工程配置，帮助理解如何安装与启动，重点看 {names}。"
    if name in {"frontend", "src"}:
        return f"主要源码模块，包含项目入口、组件或业务逻辑，重点看 {names}。"
    if name in {"backend", "app", "server"}:
        return f"后端服务与接口逻辑，适合沿入口文件继续追踪核心流程，重点看 {names}。"
    if name in {"tests", "test"}:
        return f"测试与用例，适合用来验证你是否理解主流程，重点看 {names}。"
    return f"{name} 目录相关代码，建议从 {names} 开始建立局部理解。"


def _module_dependencies(
    name: str,
    files: list[dict[str, Any]],
    module_names: Any,
) -> list[str]:
    candidates = set(module_names)
    deps: set[str] = set()
    for file in files:
        for imported in file.get("imports", []):
            clean = imported.strip("./").split("/")[0].split(".")[0]
            if clean in candidates and clean != name:
                deps.add(clean)
    return sorted(deps)


def _dependency_edges(modules: list[dict[str, Any]]) -> list[dict[str, str]]:
    edges = []
    for module in modules:
        for dep in module.get("depends_on", []):
            edges.append({"from": module["name"], "to": dep})
    return edges


def _build_tree(repo_name: str, files: list[dict[str, Any]]) -> dict[str, Any]:
    root: dict[str, Any] = {"name": repo_name, "path": "", "type": "directory", "children": []}
    for file in sorted(files, key=lambda item: item["path"]):
        current = root
        parts = PurePosixPath(file["path"]).parts
        for index, part in enumerate(parts):
            path = "/".join(parts[: index + 1])
            is_file = index == len(parts) - 1
            children = current.setdefault("children", [])
            child = next((item for item in children if item["name"] == part), None)
            if child is None:
                child = {
                    "name": part,
                    "path": path,
                    "type": "file" if is_file else "directory",
                    "importance": file.get("importance", 0) if is_file else 0,
                    "is_core": file.get("is_core", False) if is_file else False,
                    "children": [] if not is_file else None,
                }
                children.append(child)
            current = child
    return root


def _extract_start_commands(files: list[dict[str, Any]]) -> list[str]:
    commands: list[str] = []
    package = _file_content(files, "package.json")
    if package:
        try:
            scripts = json.loads(package).get("scripts", {})
            for name in ["dev", "start", "serve", "preview", "test"]:
                if name in scripts:
                    commands.append(f"npm run {name}")
        except json.JSONDecodeError:
            pass

    for file in files:
        name = PurePosixPath(file["path"]).name.lower()
        if name.startswith("readme"):
            for line in file.get("content", "").splitlines():
                stripped = line.strip("` >")
                if re.match(r"^(npm|pnpm|yarn|python|uvicorn|streamlit|pytest)\b", stripped):
                    commands.append(stripped)

    if any(PurePosixPath(file["path"]).name == "main.py" for file in files):
        commands.append("python main.py")
    return list(dict.fromkeys(commands))[:10]


def _readme_excerpt(files: list[dict[str, Any]]) -> str:
    for file in files:
        if PurePosixPath(file["path"]).name.lower().startswith("readme"):
            content = file.get("content", "")
            return content[:1200].strip()
    return ""


def _public_file_list(files: list[dict[str, Any]]) -> list[dict[str, Any]]:
    public_files = []
    for file in files:
        public_files.append(
            {
                "path": file["path"],
                "extension": file.get("extension", ""),
                "language": file.get("language", ""),
                "size": file.get("size", 0),
                "summary": file.get("summary", ""),
                "importance": file.get("importance", 0),
                "is_core": file.get("is_core", False),
                "imports": file.get("imports", []),
                "exports": file.get("exports", []),
                "symbols": file.get("symbols", []),
            }
        )
    return public_files


def _summarize_file(path: str, content: str, symbols: list[str]) -> str:
    name = PurePosixPath(path).name
    if name.lower().startswith("readme"):
        return "项目说明文档，通常包含背景、安装方式和使用方法。"
    if name == "package.json":
        return "前端或 Node.js 工程配置，包含依赖和脚本命令。"
    if name in {"pyproject.toml", "requirements.txt"}:
        return "Python 依赖与工程配置，适合判断后端框架和运行环境。"
    if symbols:
        return f"定义了 {', '.join(symbols[:5])} 等符号。"
    first_line = next((line.strip("#/ *") for line in content.splitlines() if line.strip()), "")
    return first_line[:140] or "文本文件。"


def _file_content(files: list[dict[str, Any]], name: str) -> str:
    for file in files:
        if PurePosixPath(file["path"]).name == name:
            return file.get("content", "")
    return ""


def _build_overview(
    repo_name: str,
    primary_language: str,
    frameworks: list[str],
    modules: list[dict[str, Any]],
) -> str:
    framework_text = "、".join(frameworks) if frameworks else "未识别到明确框架"
    module_text = "、".join(module["name"] for module in modules[:6])
    return (
        f"{repo_name} 是一个以 {primary_language} 为主的开源项目，"
        f"当前识别到的技术线索包括 {framework_text}。"
        f"初学者可以先从 {module_text} 这些模块建立整体地图。"
    )

