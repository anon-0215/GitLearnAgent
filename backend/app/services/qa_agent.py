from __future__ import annotations

import re
from pathlib import PurePosixPath
from typing import Any

from app.services.llm_client import LLMClient


INTENT_HINTS = {
    "start": {
        "words": {"启动", "运行", "run", "start", "dev", "serve", "命令"},
        "paths": {"README.md", "package.json", "pyproject.toml", "requirements.txt", "main.py"},
    },
    "entry": {
        "words": {"入口", "entry", "main", "首先", "开始"},
        "paths": {"main.py", "app.py", "server.py", "index.js", "main.tsx", "app.tsx"},
    },
    "core": {
        "words": {"核心", "模块", "架构", "结构", "重要"},
        "paths": set(),
    },
}


def answer_question(
    question: str,
    bundle: dict[str, Any],
    llm: LLMClient | None = None,
) -> dict[str, Any]:
    files = bundle.get("files", [])
    analysis = bundle.get("analysis", {})
    selected = _retrieve(question, files)
    citations = [_citation(question, file) for file in selected[:5]]

    if llm and llm.available and citations:
        answer = _answer_with_llm(question, analysis, citations, llm)
        if answer:
            return {"answer": answer, "citations": citations}

    return {"answer": _fallback_answer(question, analysis, citations), "citations": citations}


def _retrieve(question: str, files: list[dict[str, Any]]) -> list[dict[str, Any]]:
    tokens = _tokens(question)
    intents = _detect_intents(question)
    scored = []
    for file in files:
        path = file["path"]
        content = file.get("content", "")
        score = 0.0
        lower_path = path.lower()
        lower_content = content.lower()
        for token in tokens:
            if token in lower_path:
                score += 8
            score += min(lower_content.count(token), 8)
        for intent in intents:
            hint_paths = INTENT_HINTS[intent]["paths"]
            if PurePosixPath(path).name in hint_paths:
                score += 30
        if file.get("is_core"):
            score += 5
        score += min(float(file.get("importance", 0)), 100) / 25
        if score > 0:
            scored.append((score, file))
    scored.sort(key=lambda item: item[0], reverse=True)
    if not scored:
        scored = [(float(file.get("importance", 0)), file) for file in files if file.get("is_core")]
        scored.sort(key=lambda item: item[0], reverse=True)
    return [file for _, file in scored[:6]]


def _detect_intents(question: str) -> list[str]:
    lower = question.lower()
    intents = []
    for name, hint in INTENT_HINTS.items():
        if any(word in lower for word in hint["words"]):
            intents.append(name)
    return intents


def _tokens(text: str) -> list[str]:
    return [token.lower() for token in re.findall(r"[A-Za-z0-9_\-/\.]+", text) if len(token) > 1]


def _citation(question: str, file: dict[str, Any]) -> dict[str, Any]:
    content = file.get("content", "")
    snippet = _best_snippet(question, content)
    return {
        "path": file["path"],
        "summary": file.get("summary", ""),
        "snippet": snippet,
    }


def _best_snippet(question: str, content: str) -> str:
    lines = content.splitlines()
    if not lines:
        return ""
    tokens = _tokens(question)
    best_index = 0
    best_score = -1
    for index, line in enumerate(lines):
        lower = line.lower()
        score = sum(1 for token in tokens if token in lower)
        if score > best_score:
            best_score = score
            best_index = index
    start = max(0, best_index - 2)
    end = min(len(lines), best_index + 5)
    return "\n".join(lines[start:end])[:1200]


def _fallback_answer(
    question: str,
    analysis: dict[str, Any],
    citations: list[dict[str, Any]],
) -> str:
    paths = "、".join(item["path"] for item in citations[:4]) or "当前没有可引用文件"
    intents = _detect_intents(question)
    if "start" in intents:
        commands = analysis.get("start_commands", [])
        command_text = "；".join(commands) if commands else "暂未从 README 或配置中识别出明确启动命令"
        return f"建议先看 {paths}。根据静态分析，可能的启动/测试命令是：{command_text}。"
    if "entry" in intents:
        return f"最值得优先检查的入口相关文件是 {paths}。可以从这些文件继续追踪 import、路由或组件挂载逻辑。"
    if "core" in intents:
        modules = "、".join(module["name"] for module in analysis.get("modules", [])[:8])
        return f"当前项目被拆成这些主要模块：{modules}。与问题最相关的源码引用是 {paths}。"
    return f"我在当前分析结果中找到了这些相关文件：{paths}。请优先根据右侧引用片段判断答案，避免脱离源码猜测。"


def _answer_with_llm(
    question: str,
    analysis: dict[str, Any],
    citations: list[dict[str, Any]],
    llm: LLMClient,
) -> str | None:
    source_text = "\n\n".join(
        f"[{index}] {item['path']}\n{item['snippet']}"
        for index, item in enumerate(citations, start=1)
    )
    prompt = (
        "请回答用户关于代码仓库的问题。必须遵守："
        "1. 只依据给出的源码片段和结构化分析；"
        "2. 不确定就说明未找到依据；"
        "3. 回答中点名引用的文件路径。\n\n"
        f"结构化分析：{analysis.get('overview', '')}\n\n"
        f"源码片段：\n{source_text}\n\n"
        f"用户问题：{question}"
    )
    return llm.chat(
        [
            {"role": "system", "content": "你是严谨的源码导读助手，面向编程初学者。"},
            {"role": "user", "content": prompt},
        ],
        temperature=0.1,
    )

