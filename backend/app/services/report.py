from __future__ import annotations

from typing import Any


def generate_report(bundle: dict[str, Any]) -> str:
    project = bundle["project"]
    analysis = bundle.get("analysis", {})
    modules = bundle.get("modules", [])
    steps = bundle.get("learning_steps", [])
    core_files = [file for file in bundle.get("files", []) if file.get("is_core")]

    lines = [
        f"# {project['repo']} 开源项目学习报告",
        "",
        f"- 仓库：{project['repo_url']}",
        f"- 默认分支：{project['default_branch']}",
        f"- 主语言：{project.get('primary_language') or analysis.get('primary_language', 'Unknown')}",
        f"- 识别框架：{'、'.join(project.get('frameworks', [])) or '未识别'}",
        "",
        "## 项目概览",
        "",
        analysis.get("overview", "暂无概览。"),
        "",
        "## 核心文件",
        "",
    ]

    for file in core_files[:12]:
        lines.append(f"- `{file['path']}`：{file.get('summary', '')}")

    lines.extend(["", "## 模块地图", ""])
    for module in modules:
        files = "、".join(f"`{path}`" for path in module.get("files", [])[:5])
        lines.append(f"- **{module['name']}**：{module.get('responsibility', '')} 相关文件：{files}")

    lines.extend(["", "## 推荐学习路线", ""])
    for step in steps:
        lines.append(f"### {step['title']}")
        lines.append(step.get("goal", ""))
        if step.get("files"):
            lines.append("推荐阅读：" + "、".join(f"`{path}`" for path in step["files"]))
        if step.get("tasks"):
            lines.append("任务：" + "；".join(step["tasks"]))
        lines.append("")

    lines.extend(["## 可用于大创展示的差异化说明", ""])
    lines.extend(
        [
            "- 本系统先做确定性的静态分析，再调用大模型生成导读内容。",
            "- 问答答案必须展示源码引用，降低直接问通用 AI 时的幻觉风险。",
            "- 输出不是单次摘要，而是面向初学者的学习路径、任务和测验。",
        ]
    )
    return "\n".join(lines).strip() + "\n"

