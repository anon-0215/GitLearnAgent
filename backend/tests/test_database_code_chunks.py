import hashlib
import sqlite3
import tempfile
import unittest
from pathlib import Path

from app.database import Database, SCHEMA_VERSION


def _project_id(db: Database) -> str:
    return db.create_project(
        {
            "repo_url": "https://github.com/demo/sample",
            "owner": "demo",
            "repo": "sample",
            "default_branch": "main",
        }
    )


def _chunk(
    path: str = "src/app.py",
    qualified_name: str = "target",
    content: str = "def target():\n    return 1\n",
    chunk_type: str = "function",
    symbol_name: str = "target",
) -> dict:
    return {
        "repository_revision": "abc123",
        "language": "python",
        "path": path,
        "chunk_type": chunk_type,
        "symbol_name": symbol_name,
        "qualified_name": qualified_name,
        "parent_symbol": "",
        "start_line": 1,
        "end_line": len(content.splitlines()),
        "content": content,
        "content_hash": hashlib.sha256(content.encode("utf-8")).hexdigest(),
    }


class DatabaseCodeChunkTests(unittest.TestCase):
    def test_legacy_database_initializes_new_code_chunk_structure(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "legacy.sqlite"
            conn = sqlite3.connect(path)
            try:
                conn.executescript(
                    """
                    CREATE TABLE projects (
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
                    INSERT INTO projects (
                        id, repo_url, owner, repo, default_branch, status
                    )
                    VALUES (
                        'legacy-project', 'https://github.com/demo/legacy',
                        'demo', 'legacy', 'main', 'done'
                    );
                    """
                )
                conn.commit()
            finally:
                conn.close()

            db = Database(path)
            with db.connect() as conn:
                tables = {
                    row["name"]
                    for row in conn.execute(
                        "SELECT name FROM sqlite_master WHERE type = 'table'"
                    ).fetchall()
                }
                version = conn.execute(
                    "SELECT version FROM schema_versions WHERE key = 'database'"
                ).fetchone()["version"]

            self.assertIn("code_chunks", tables)
            self.assertIn("schema_versions", tables)
            self.assertGreaterEqual(version, 2)
            self.assertEqual(db.get_project("legacy-project")["repo"], "legacy")

    def test_schema_version_initialization_is_idempotent(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "schema.sqlite"
            db = Database(path)
            with db.connect() as conn:
                conn.execute(
                    """
                    UPDATE schema_versions
                    SET version = ?, updated_at = ?
                    WHERE key = ?
                    """,
                    (SCHEMA_VERSION, "fixed-timestamp", "database"),
                )

            reopened = Database(path)
            with reopened.connect() as conn:
                row = conn.execute(
                    "SELECT version, updated_at FROM schema_versions WHERE key = ?",
                    ("database",),
                ).fetchone()

            self.assertEqual(row["version"], SCHEMA_VERSION)
            self.assertEqual(row["updated_at"], "fixed-timestamp")

    def test_code_chunk_foreign_key_is_enabled_and_cascades(self):
        with tempfile.TemporaryDirectory() as directory:
            db = Database(Path(directory) / "foreign-key.sqlite")
            project_id = _project_id(db)
            db.save_code_chunks_for_project(project_id, [_chunk()])

            with db.connect() as conn:
                foreign_keys_enabled = conn.execute("PRAGMA foreign_keys").fetchone()[0]
                conn.execute("DELETE FROM projects WHERE id = ?", (project_id,))

            self.assertEqual(foreign_keys_enabled, 1)
            self.assertEqual(db.get_code_chunks(project_id), [])

    def test_saves_reads_and_filters_code_chunks(self):
        with tempfile.TemporaryDirectory() as directory:
            db = Database(Path(directory) / "chunks.sqlite")
            project_id = _project_id(db)
            chunks = [
                _chunk("src/app.py", "target"),
                _chunk(
                    "src/service.py",
                    "Service.run",
                    "class Service:\n    def run(self):\n        return True\n",
                    "method",
                    "run",
                ),
            ]

            db.save_code_chunks_for_project(project_id, chunks)
            all_chunks = db.get_code_chunks(project_id)
            by_path = db.get_code_chunks(project_id, path="src\\app.py")
            by_symbol = db.get_code_chunks(project_id, symbol="Service.run")
            by_type = db.get_code_chunks(project_id, chunk_type="method")

            self.assertEqual(len(all_chunks), 2)
            self.assertEqual(by_path[0]["qualified_name"], "target")
            self.assertEqual(by_symbol[0]["path"], "src/service.py")
            self.assertEqual(by_type[0]["symbol_name"], "run")

    def test_repeated_project_save_does_not_duplicate_chunks(self):
        with tempfile.TemporaryDirectory() as directory:
            db = Database(Path(directory) / "repeat.sqlite")
            project_id = _project_id(db)
            chunks = [_chunk()]

            db.save_code_chunks_for_project(project_id, chunks)
            db.save_code_chunks_for_project(project_id, chunks)

            self.assertEqual(len(db.get_code_chunks(project_id)), 1)

    def test_replaces_code_chunks_for_one_file(self):
        with tempfile.TemporaryDirectory() as directory:
            db = Database(Path(directory) / "replace.sqlite")
            project_id = _project_id(db)
            db.save_code_chunks_for_project(
                project_id,
                [
                    _chunk("src/app.py", "old_name", "def old_name():\n    return 1\n", symbol_name="old_name"),
                    _chunk("src/other.py", "other", "def other():\n    return 2\n", symbol_name="other"),
                ],
            )

            db.replace_code_chunks_for_file(
                project_id,
                "src\\app.py",
                [_chunk("src/app.py", "new_name", "def new_name():\n    return 3\n", symbol_name="new_name")],
            )

            app_chunks = db.get_code_chunks(project_id, path="src/app.py")
            other_chunks = db.get_code_chunks(project_id, path="src/other.py")
            self.assertEqual([chunk["qualified_name"] for chunk in app_chunks], ["new_name"])
            self.assertEqual([chunk["qualified_name"] for chunk in other_chunks], ["other"])

    def test_empty_file_replacement_clears_previous_chunks(self):
        with tempfile.TemporaryDirectory() as directory:
            db = Database(Path(directory) / "empty-replace.sqlite")
            project_id = _project_id(db)
            db.save_code_chunks_for_project(
                project_id,
                [
                    _chunk("src/app.py", "old_name", "def old_name():\n    return 1\n", symbol_name="old_name"),
                    _chunk("src/other.py", "other", "def other():\n    return 2\n", symbol_name="other"),
                ],
            )

            db.replace_code_chunks_for_file(project_id, "src/app.py", [])

            self.assertEqual(db.get_code_chunks(project_id, path="src/app.py"), [])
            self.assertEqual(
                [chunk["qualified_name"] for chunk in db.get_code_chunks(project_id, path="src/other.py")],
                ["other"],
            )

    def test_project_save_clears_stale_chunks_for_removed_python_files(self):
        with tempfile.TemporaryDirectory() as directory:
            db = Database(Path(directory) / "stale.sqlite")
            project_id = _project_id(db)
            db.save_code_chunks_for_project(project_id, [_chunk("src/removed.py", "removed")])

            db.save_analysis(
                project_id,
                {
                    "primary_language": "Python",
                    "frameworks": [],
                    "files": [],
                    "modules": [],
                    "overview": "updated",
                },
                [
                    {
                        "path": "README.md",
                        "extension": ".md",
                        "language": "Markdown",
                        "size": 8,
                        "content": "# Demo\n",
                        "summary": "readme",
                        "importance": 1,
                        "is_core": True,
                        "imports": [],
                        "exports": [],
                        "symbols": [],
                    }
                ],
                [],
                [],
            )

            bundle = db.get_bundle(project_id)
            self.assertEqual(db.get_code_chunks(project_id), [])
            self.assertEqual([file["path"] for file in bundle["files"]], ["README.md"])

    def test_delete_project_removes_related_code_chunks(self):
        with tempfile.TemporaryDirectory() as directory:
            db = Database(Path(directory) / "delete.sqlite")
            project_id = _project_id(db)
            db.save_code_chunks_for_project(project_id, [_chunk()])
            db.save_chat_answer(project_id, "question", "answer", [])

            db.delete_project(project_id)

            self.assertIsNone(db.get_project(project_id))
            self.assertEqual(db.get_code_chunks(project_id), [])
            self.assertIsNone(db.get_bundle(project_id))

    def test_code_chunk_save_rolls_back_on_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            db = Database(Path(directory) / "rollback.sqlite")
            project_id = _project_id(db)
            original = _chunk("src/app.py", "original", "def original():\n    return 1\n", symbol_name="original")
            replacement = _chunk("src/app.py", "replacement", "def replacement():\n    return 2\n", symbol_name="replacement")
            invalid = _chunk("src/bad.py", "bad", "def bad():\n    return 3\n", symbol_name="bad")
            invalid["start_line"] = 0
            db.save_code_chunks_for_project(project_id, [original])

            with self.assertRaises(ValueError):
                db.save_code_chunks_for_project(project_id, [replacement, invalid])

            stored = db.get_code_chunks(project_id)
            self.assertEqual(len(stored), 1)
            self.assertEqual(stored[0]["qualified_name"], "original")

    def test_existing_project_qa_and_report_data_are_unchanged(self):
        with tempfile.TemporaryDirectory() as directory:
            db = Database(Path(directory) / "compat.sqlite")
            project_id = _project_id(db)
            analysis = {
                "primary_language": "Python",
                "frameworks": ["FastAPI"],
                "files": [],
                "modules": [{"name": "app", "responsibility": "backend"}],
                "overview": "Demo overview",
            }
            files = [
                {
                    "path": "app/main.py",
                    "extension": ".py",
                    "language": "Python",
                    "size": 12,
                    "content": "print('ok')\n",
                    "summary": "entry",
                    "importance": 1,
                    "is_core": True,
                    "imports": [],
                    "exports": [],
                    "symbols": [],
                }
            ]
            steps = [{"title": "Step", "goal": "Goal", "files": [], "tasks": [], "quiz": []}]

            db.save_analysis(project_id, analysis, files, steps)
            db.save_chat_answer(project_id, "入口在哪", "看 app/main.py", [{"path": "app/main.py"}])
            bundle = db.get_bundle(project_id)

            self.assertEqual(bundle["files"][0]["path"], "app/main.py")
            self.assertEqual(bundle["modules"][0]["name"], "app")
            self.assertEqual(bundle["learning_steps"][0]["title"], "Step")
            self.assertEqual(bundle["chat_answers"][0]["question"], "入口在哪")
            self.assertEqual(bundle["code_chunks"], [])


if __name__ == "__main__":
    unittest.main()
