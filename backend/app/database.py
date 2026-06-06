from __future__ import annotations

import json
import os
import sqlite3
import tempfile
import uuid
from pathlib import Path
from typing import Any


DEFAULT_DB_PATH = Path(__file__).resolve().parents[1] / "data" / "gitlearn.sqlite"


SCHEMA = """
CREATE TABLE IF NOT EXISTS projects (
    id TEXT PRIMARY KEY,
    repo_url TEXT NOT NULL,
    owner TEXT NOT NULL,
    repo TEXT NOT NULL,
    default_branch TEXT NOT NULL,
    status TEXT NOT NULL,
    primary_language TEXT DEFAULT '',
    frameworks_json TEXT DEFAULT '[]',
    analysis_json TEXT DEFAULT '{}',
    error_message TEXT DEFAULT '',
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS repo_files (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id TEXT NOT NULL,
    path TEXT NOT NULL,
    extension TEXT DEFAULT '',
    language TEXT DEFAULT '',
    size INTEGER DEFAULT 0,
    content TEXT DEFAULT '',
    summary TEXT DEFAULT '',
    importance REAL DEFAULT 0,
    is_core INTEGER DEFAULT 0,
    imports_json TEXT DEFAULT '[]',
    exports_json TEXT DEFAULT '[]',
    symbols_json TEXT DEFAULT '[]',
    FOREIGN KEY(project_id) REFERENCES projects(id)
);

CREATE TABLE IF NOT EXISTS modules (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id TEXT NOT NULL,
    name TEXT NOT NULL,
    responsibility TEXT DEFAULT '',
    files_json TEXT DEFAULT '[]',
    depends_on_json TEXT DEFAULT '[]',
    FOREIGN KEY(project_id) REFERENCES projects(id)
);

CREATE TABLE IF NOT EXISTS learning_steps (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id TEXT NOT NULL,
    step_order INTEGER NOT NULL,
    title TEXT NOT NULL,
    goal TEXT DEFAULT '',
    files_json TEXT DEFAULT '[]',
    tasks_json TEXT DEFAULT '[]',
    quiz_json TEXT DEFAULT '[]',
    FOREIGN KEY(project_id) REFERENCES projects(id)
);

CREATE TABLE IF NOT EXISTS chat_answers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id TEXT NOT NULL,
    question TEXT NOT NULL,
    answer TEXT NOT NULL,
    citations_json TEXT DEFAULT '[]',
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(project_id) REFERENCES projects(id)
);
"""


class Database:
    def __init__(self, path: Path | str | None = None) -> None:
        explicit_path = path or os.getenv("GITLEARN_DB")
        self.path = Path(explicit_path) if explicit_path else DEFAULT_DB_PATH
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self._init_schema()
        except (PermissionError, sqlite3.OperationalError):
            if explicit_path:
                raise
            self.path = Path(tempfile.gettempdir()) / "gitlearnagent.sqlite"
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self._init_schema()

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_schema(self) -> None:
        with self.connect() as conn:
            conn.executescript(SCHEMA)

    def create_project(self, snapshot: dict[str, Any]) -> str:
        project_id = str(uuid.uuid4())
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO projects (id, repo_url, owner, repo, default_branch, status)
                VALUES (?, ?, ?, ?, ?, 'analyzing')
                """,
                (
                    project_id,
                    snapshot["repo_url"],
                    snapshot["owner"],
                    snapshot["repo"],
                    snapshot["default_branch"],
                ),
            )
        return project_id

    def mark_failed(self, project_id: str, message: str) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                UPDATE projects
                SET status = 'failed', error_message = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (message[:2000], project_id),
            )

    def save_analysis(
        self,
        project_id: str,
        analysis: dict[str, Any],
        files: list[dict[str, Any]],
        learning_steps: list[dict[str, Any]],
    ) -> None:
        with self.connect() as conn:
            conn.execute("DELETE FROM repo_files WHERE project_id = ?", (project_id,))
            conn.execute("DELETE FROM modules WHERE project_id = ?", (project_id,))
            conn.execute("DELETE FROM learning_steps WHERE project_id = ?", (project_id,))

            for file in files:
                conn.execute(
                    """
                    INSERT INTO repo_files (
                        project_id, path, extension, language, size, content, summary,
                        importance, is_core, imports_json, exports_json, symbols_json
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        project_id,
                        file["path"],
                        file.get("extension", ""),
                        file.get("language", ""),
                        int(file.get("size", 0)),
                        file.get("content", ""),
                        file.get("summary", ""),
                        float(file.get("importance", 0)),
                        1 if file.get("is_core") else 0,
                        json.dumps(file.get("imports", []), ensure_ascii=False),
                        json.dumps(file.get("exports", []), ensure_ascii=False),
                        json.dumps(file.get("symbols", []), ensure_ascii=False),
                    ),
                )

            for module in analysis.get("modules", []):
                conn.execute(
                    """
                    INSERT INTO modules (project_id, name, responsibility, files_json, depends_on_json)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        project_id,
                        module["name"],
                        module.get("responsibility", ""),
                        json.dumps(module.get("files", []), ensure_ascii=False),
                        json.dumps(module.get("depends_on", []), ensure_ascii=False),
                    ),
                )

            for index, step in enumerate(learning_steps, start=1):
                conn.execute(
                    """
                    INSERT INTO learning_steps (
                        project_id, step_order, title, goal, files_json, tasks_json, quiz_json
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        project_id,
                        index,
                        step["title"],
                        step.get("goal", ""),
                        json.dumps(step.get("files", []), ensure_ascii=False),
                        json.dumps(step.get("tasks", []), ensure_ascii=False),
                        json.dumps(step.get("quiz", []), ensure_ascii=False),
                    ),
                )

            conn.execute(
                """
                UPDATE projects
                SET status = 'done',
                    primary_language = ?,
                    frameworks_json = ?,
                    analysis_json = ?,
                    error_message = '',
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (
                    analysis.get("primary_language", ""),
                    json.dumps(analysis.get("frameworks", []), ensure_ascii=False),
                    json.dumps(analysis, ensure_ascii=False),
                    project_id,
                ),
            )

    def get_project(self, project_id: str) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
        if not row:
            return None
        return self._project_from_row(row)

    def get_bundle(self, project_id: str) -> dict[str, Any] | None:
        project = self.get_project(project_id)
        if not project:
            return None

        with self.connect() as conn:
            file_rows = conn.execute(
                "SELECT * FROM repo_files WHERE project_id = ? ORDER BY importance DESC, path",
                (project_id,),
            ).fetchall()
            module_rows = conn.execute(
                "SELECT * FROM modules WHERE project_id = ? ORDER BY name",
                (project_id,),
            ).fetchall()
            step_rows = conn.execute(
                "SELECT * FROM learning_steps WHERE project_id = ? ORDER BY step_order",
                (project_id,),
            ).fetchall()
            chat_rows = conn.execute(
                "SELECT * FROM chat_answers WHERE project_id = ? ORDER BY id DESC LIMIT 20",
                (project_id,),
            ).fetchall()

        return {
            "project": project,
            "files": [self._file_from_row(row) for row in file_rows],
            "modules": [self._module_from_row(row) for row in module_rows],
            "learning_steps": [self._step_from_row(row) for row in step_rows],
            "chat_answers": [self._chat_from_row(row) for row in chat_rows],
            "analysis": project.get("analysis", {}),
        }

    def save_chat_answer(
        self,
        project_id: str,
        question: str,
        answer: str,
        citations: list[dict[str, Any]],
    ) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO chat_answers (project_id, question, answer, citations_json)
                VALUES (?, ?, ?, ?)
                """,
                (project_id, question, answer, json.dumps(citations, ensure_ascii=False)),
            )

    @staticmethod
    def _json(value: str, fallback: Any) -> Any:
        try:
            return json.loads(value or "")
        except json.JSONDecodeError:
            return fallback

    def _project_from_row(self, row: sqlite3.Row) -> dict[str, Any]:
        return {
            "id": row["id"],
            "repo_url": row["repo_url"],
            "owner": row["owner"],
            "repo": row["repo"],
            "default_branch": row["default_branch"],
            "status": row["status"],
            "primary_language": row["primary_language"],
            "frameworks": self._json(row["frameworks_json"], []),
            "analysis": self._json(row["analysis_json"], {}),
            "error_message": row["error_message"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }

    def _file_from_row(self, row: sqlite3.Row) -> dict[str, Any]:
        return {
            "path": row["path"],
            "extension": row["extension"],
            "language": row["language"],
            "size": row["size"],
            "content": row["content"],
            "summary": row["summary"],
            "importance": row["importance"],
            "is_core": bool(row["is_core"]),
            "imports": self._json(row["imports_json"], []),
            "exports": self._json(row["exports_json"], []),
            "symbols": self._json(row["symbols_json"], []),
        }

    def _module_from_row(self, row: sqlite3.Row) -> dict[str, Any]:
        return {
            "name": row["name"],
            "responsibility": row["responsibility"],
            "files": self._json(row["files_json"], []),
            "depends_on": self._json(row["depends_on_json"], []),
        }

    def _step_from_row(self, row: sqlite3.Row) -> dict[str, Any]:
        return {
            "order": row["step_order"],
            "title": row["title"],
            "goal": row["goal"],
            "files": self._json(row["files_json"], []),
            "tasks": self._json(row["tasks_json"], []),
            "quiz": self._json(row["quiz_json"], []),
        }

    def _chat_from_row(self, row: sqlite3.Row) -> dict[str, Any]:
        return {
            "question": row["question"],
            "answer": row["answer"],
            "citations": self._json(row["citations_json"], []),
            "created_at": row["created_at"],
        }
