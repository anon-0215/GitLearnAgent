from __future__ import annotations

from pathlib import PurePosixPath
from typing import Any

from app.services.llm_client import LLMClient


def build_learning_path(
    project: dict[str, Any],
    analysis: dict[str, Any],
    llm: LLMClient | None = None,
) -> list[dict[str, Any]]:
    core_files = [file["path"] for file in analysis.get("files", []) if file.get("is_core")]
    readme_files = [path for path in core_files if PurePosixPath(path).name.lower().startswith("readme")]
    config_files = [
        path
        for path in core_files
        if PurePosixPath(path).name in {"package.json", "pyproject.toml", "requirements.txt"}
    ]
    entry_files = [
        file["path"]
        for file in analysis.get("files", [])
        if PurePosixPath(file["path"]).name.lower()
        in {"main.py", "app.py", "server.py", "index.js", "main.tsx", "app.tsx"}
    ][:5]
    module_files = []
    for module in analysis.get("modules", [])[:4]:
        module_files.extend(module.get("files", [])[:2])

    steps = [
        {
            "title": "1. 建立项目全局印象",
            "goal": "先弄清项目解决什么问题、主要技术栈是什么、目录大致如何分工。",
            "files": readme_files or core_files[:3],
            "tasks": [
                "用自己的话写下这个项目的用途。",
                "标记 README 中的安装、启动和示例用法。",
            ],
            "quiz": [
                {"question": "这个项目主要使用哪种语言？", "answer": analysis.get("primary_language", "Unknown")},
                {"question": "系统识别到了哪些框架？", "answer": "、".join(analysis.get("frameworks", [])) or "未识别"},
            ],
        },
        {
            "title": "2. 理解依赖和启动方式",
            "goal": "知道项目如何安装、运行和测试，避免一开始就迷失在源码细节里。",
            "files": config_files or core_files[:4],
            "tasks": [
                "找出项目的依赖管理文件。",
                "记录至少一个启动或测试命令。",
            ],
            "quiz": [
                {
                    "question": "项目可能的启动命令是什么？",
                    "answer": "；".join(analysis.get("start_commands", [])) or "需要结合 README 或配置文件判断",
                }
            ],
        },
        {
            "title": "3. 顺着入口文件追主流程",
            "goal": "从入口文件开始，看请求、页面或命令是如何进入核心逻辑的。",
            "files": entry_files or core_files[:5],
            "tasks": [
                "找到程序最先执行的文件或前端挂载入口。",
                "画出入口文件调用的第一个核心模块。",
            ],
            "quiz": [
                {
                    "question": "你认为哪个文件最像入口文件？",
                    "answer": "、".join(entry_files) or "根据核心文件列表继续判断",
                }
            ],
        },
        {
            "title": "4. 分模块阅读核心代码",
            "goal": "按模块而不是按文件数量阅读，优先理解职责边界。",
            "files": list(dict.fromkeys(module_files))[:8] or core_files[:8],
            "tasks": [
                "为每个核心模块写一句职责说明。",
                "找出模块之间是否存在调用或导入关系。",
            ],
            "quiz": [
                {
                    "question": "当前系统拆出了哪些模块？",
                    "answer": "、".join(module["name"] for module in analysis.get("modules", [])) or "暂无模块",
                }
            ],
        },
        {
            "title": "5. 完成一个小修改任务",
            "goal": "用最小改动验证自己是否真的理解项目结构。",
            "files": core_files[:6],
            "tasks": [
                "选择一个核心文件，给关键函数或组件补一条说明性注释。",
                "尝试修改一个页面文案、命令输出或配置项，并说明影响范围。",
            ],
            "quiz": [
                {
                    "question": "如果要新增一个很小的功能，你会先改哪个模块？为什么？",
                    "answer": "应结合模块职责和引用文件回答。",
                }
            ],
        },
    ]

    if llm and llm.available:
        enhanced_goal = _ask_llm_for_overview(project, analysis, llm)
        if enhanced_goal:
            steps[0]["goal"] = enhanced_goal
    return steps


def _ask_llm_for_overview(
    project: dict[str, Any],
    analysis: dict[str, Any],
    llm: LLMClient,
) -> str | None:
    prompt = (
        "请用一句适合大一学生的话概括这个开源项目的学习入口。"
        "不要编造功能，只能依据以下结构化分析：\n"
        f"仓库：{project.get('repo')}\n"
        f"语言：{analysis.get('primary_language')}\n"
        f"框架：{analysis.get('frameworks')}\n"
        f"模块：{[module['name'] for module in analysis.get('modules', [])]}"
    )
    return llm.chat(
        [
            {"role": "system", "content": "你是面向编程初学者的开源项目导读助手。"},
            {"role": "user", "content": prompt},
        ],
        temperature=0.2,
    )

