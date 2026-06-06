from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from app.config import get_env_value, load_environment
from app.database import Database
from app.services.analyzer import analyze_snapshot
from app.services.github_client import fetch_repository
from app.services.learning_agent import build_learning_path
from app.services.llm_client import LLMClient
from app.services.qa_agent import answer_question
from app.services.report import generate_report


load_environment()

app = FastAPI(title="GitLearnAgent API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

db = Database()
llm = LLMClient()


class AnalyzeRequest(BaseModel):
    repo_url: str = Field(..., examples=["https://github.com/tiangolo/fastapi"])


class AskRequest(BaseModel):
    question: str = Field(..., min_length=1)


@app.get("/api/health")
def health() -> dict[str, Any]:
    return {
        "ok": True,
        "llm_available": llm.available,
        "github_token_configured": bool(get_env_value("GITHUB_TOKEN")),
        "database": str(Path(db.path)),
    }


@app.post("/api/projects/analyze")
def analyze_project(request: AnalyzeRequest) -> dict[str, Any]:
    try:
        snapshot = fetch_repository(request.repo_url)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    project_id = db.create_project(snapshot.to_dict())
    try:
        analysis = analyze_snapshot(snapshot)
        project = {
            "id": project_id,
            "repo": snapshot.repo,
            "repo_url": snapshot.repo_url,
        }
        learning_steps = build_learning_path(project, analysis, llm)
        enriched_files = [file.to_dict() for file in snapshot.files]
        enriched_by_path = {file["path"]: file for file in enriched_files}
        for public_file in analysis["files"]:
            enriched_by_path[public_file["path"]].update(public_file)
        db.save_analysis(project_id, analysis, list(enriched_by_path.values()), learning_steps)
    except Exception as exc:
        db.mark_failed(project_id, str(exc))
        raise HTTPException(status_code=500, detail=f"分析失败：{exc}") from exc

    return {"project_id": project_id, "status": "done"}


@app.get("/api/projects/{project_id}")
def get_project(project_id: str) -> dict[str, Any]:
    project = db.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="项目不存在")
    analysis = project.get("analysis", {})
    return {
        "project": {key: value for key, value in project.items() if key != "analysis"},
        "overview": analysis.get("overview", ""),
        "stats": analysis.get("stats", {}),
        "start_commands": analysis.get("start_commands", []),
        "core_files": [
            file for file in analysis.get("files", []) if file.get("is_core")
        ][:12],
        "modules": analysis.get("modules", []),
    }


@app.get("/api/projects/{project_id}/map")
def get_project_map(project_id: str) -> dict[str, Any]:
    bundle = _bundle_or_404(project_id)
    analysis = bundle.get("analysis", {})
    return {
        "tree": analysis.get("tree", {}),
        "modules": bundle.get("modules", []),
        "dependency_edges": analysis.get("dependency_edges", []),
        "core_files": [file for file in bundle.get("files", []) if file.get("is_core")],
    }


@app.get("/api/projects/{project_id}/learning-path")
def get_learning_path(project_id: str) -> dict[str, Any]:
    bundle = _bundle_or_404(project_id)
    return {"steps": bundle.get("learning_steps", [])}


@app.post("/api/projects/{project_id}/ask")
def ask_project(project_id: str, request: AskRequest) -> dict[str, Any]:
    bundle = _bundle_or_404(project_id)
    result = answer_question(request.question, bundle, llm)
    db.save_chat_answer(project_id, request.question, result["answer"], result["citations"])
    return result


@app.get("/api/projects/{project_id}/report")
def get_report(project_id: str) -> dict[str, str]:
    bundle = _bundle_or_404(project_id)
    return {"markdown": generate_report(bundle)}


def _bundle_or_404(project_id: str) -> dict[str, Any]:
    bundle = db.get_bundle(project_id)
    if not bundle:
        raise HTTPException(status_code=404, detail="项目不存在")
    return bundle
