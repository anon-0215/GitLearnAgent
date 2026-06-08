import hashlib
import tempfile
import unittest
from pathlib import Path

from app.config import EmbeddingSettings
from app.database import Database
from app.services.embedding_service import CODE_CHUNK_TEXT_FORMAT_VERSION, EmbeddingService
from app.services.semantic_retriever import SemanticRetriever


MODEL_NAME = "fake-model"
MODEL_REVISION = ""


def _settings():
    return EmbeddingSettings(
        enabled=True,
        model_name_or_path=MODEL_NAME,
        device="cpu",
        batch_size=4,
        max_length=128,
        normalize=True,
        cache_dir=Path("embedding-cache"),
        query_prefix="",
        document_prefix="",
    )


class QueryBackend:
    def __init__(self):
        self.load_calls = 0
        self.encode_calls = 0

    def load_model(self, model_name_or_path, device, cache_dir, max_length):
        self.load_calls += 1

    def encode(self, texts, batch_size, normalize):
        self.encode_calls += 1
        vectors = []
        for text in texts:
            if "用户身份" in text or "auth" in text.lower():
                vectors.append([1.0, 0.0, 0.0])
            elif "upload" in text.lower():
                vectors.append([0.0, 1.0, 0.0])
            else:
                vectors.append([0.0, 0.0, 1.0])
        return vectors

    def get_embedding_dimension(self):
        return 3

    def unload_model(self):
        pass


def _project_id(db: Database) -> str:
    return db.create_project(
        {
            "repo_url": "https://github.com/demo/sample",
            "owner": "demo",
            "repo": "sample",
            "default_branch": "main",
        }
    )


def _chunk(path, name, content=None, chunk_type="function", start_line=1):
    source = content or f"def {name}():\n    return '{name}'\n"
    return {
        "repository_revision": "abc123",
        "language": "python",
        "path": path,
        "chunk_type": chunk_type,
        "symbol_name": name.split(".")[-1],
        "qualified_name": name,
        "parent_symbol": name.rsplit(".", 1)[0] if "." in name else "",
        "start_line": start_line,
        "end_line": start_line + len(source.splitlines()) - 1,
        "content": source,
        "content_hash": hashlib.sha256(source.encode("utf-8")).hexdigest(),
    }


def _record(chunk, vector):
    return {
        "code_chunk_id": chunk["id"],
        "content_hash": chunk["content_hash"],
        "model_name": MODEL_NAME,
        "model_revision": MODEL_REVISION,
        "text_format_version": CODE_CHUNK_TEXT_FORMAT_VERSION,
        "embedding_dimension": len(vector),
        "embedding_dtype": "float32",
        "normalized": True,
        "vector": vector,
    }


def _service(backend=None):
    fake_backend = backend or QueryBackend()
    return EmbeddingService(
        _settings(),
        backend_factory=lambda: fake_backend,
        cuda_available=lambda: False,
    )


class SemanticRetrieverTests(unittest.TestCase):
    def test_top_k_sorting_uses_semantic_score(self):
        with tempfile.TemporaryDirectory() as directory:
            db = Database(Path(directory) / "topk.sqlite")
            project_id = _project_id(db)
            db.save_code_chunks_for_project(
                project_id,
                [
                    _chunk("auth.py", "authenticate_user"),
                    _chunk("upload.py", "upload_file"),
                    _chunk("db.py", "init_db"),
                ],
            )
            chunks = {chunk["qualified_name"]: chunk for chunk in db.get_code_chunks(project_id)}
            db.upsert_code_chunk_embeddings(
                [
                    _record(chunks["authenticate_user"], [1.0, 0.0, 0.0]),
                    _record(chunks["upload_file"], [0.0, 1.0, 0.0]),
                    _record(chunks["init_db"], [0.0, 0.0, 1.0]),
                ]
            )

            outcome = SemanticRetriever(db, _service()).search(project_id, "auth", top_k=2)

            self.assertEqual(outcome.status, "ok")
            self.assertEqual([item.qualified_name for item in outcome.results], ["authenticate_user", "init_db"])

    def test_equal_scores_have_stable_sort_order(self):
        with tempfile.TemporaryDirectory() as directory:
            db = Database(Path(directory) / "stable.sqlite")
            project_id = _project_id(db)
            db.save_code_chunks_for_project(
                project_id,
                [
                    _chunk("b.py", "b", start_line=1),
                    _chunk("a.py", "late", start_line=10),
                    _chunk("a.py", "early", start_line=1),
                ],
            )
            chunks = db.get_code_chunks(project_id)
            db.upsert_code_chunk_embeddings([_record(chunk, [1.0, 0.0, 0.0]) for chunk in chunks])

            outcome = SemanticRetriever(db, _service()).search(project_id, "auth", top_k=3)

            self.assertEqual(
                [(item.path, item.qualified_name) for item in outcome.results],
                [("a.py", "early"), ("a.py", "late"), ("b.py", "b")],
            )

    def test_path_filter_limits_candidates(self):
        with tempfile.TemporaryDirectory() as directory:
            db = Database(Path(directory) / "path.sqlite")
            project_id = _project_id(db)
            db.save_code_chunks_for_project(
                project_id,
                [_chunk("auth.py", "authenticate_user"), _chunk("upload.py", "upload_file")],
            )
            chunks = {chunk["qualified_name"]: chunk for chunk in db.get_code_chunks(project_id)}
            db.upsert_code_chunk_embeddings(
                [
                    _record(chunks["authenticate_user"], [1.0, 0.0, 0.0]),
                    _record(chunks["upload_file"], [0.0, 1.0, 0.0]),
                ]
            )

            outcome = SemanticRetriever(db, _service()).search(
                project_id,
                "auth",
                path="upload.py",
            )

            self.assertEqual([item.path for item in outcome.results], ["upload.py"])

    def test_chunk_type_filter_limits_candidates(self):
        with tempfile.TemporaryDirectory() as directory:
            db = Database(Path(directory) / "type.sqlite")
            project_id = _project_id(db)
            db.save_code_chunks_for_project(
                project_id,
                [
                    _chunk("auth.py", "AuthService.authenticate", chunk_type="method"),
                    _chunk("auth.py", "helper", chunk_type="function", start_line=5),
                ],
            )
            chunks = db.get_code_chunks(project_id)
            db.upsert_code_chunk_embeddings([_record(chunk, [1.0, 0.0, 0.0]) for chunk in chunks])

            outcome = SemanticRetriever(db, _service()).search(
                project_id,
                "auth",
                chunk_type="method",
            )

            self.assertEqual([item.chunk_type for item in outcome.results], ["method"])

    def test_empty_query_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            db = Database(Path(directory) / "empty.sqlite")
            project_id = _project_id(db)

            with self.assertRaises(ValueError):
                SemanticRetriever(db, _service()).search(project_id, "   ")

    def test_no_cache_returns_clear_status_without_encoding_query(self):
        with tempfile.TemporaryDirectory() as directory:
            db = Database(Path(directory) / "none.sqlite")
            project_id = _project_id(db)
            db.save_code_chunks_for_project(project_id, [_chunk("auth.py", "authenticate_user")])
            backend = QueryBackend()

            outcome = SemanticRetriever(db, _service(backend)).search(project_id, "auth")

            self.assertEqual(outcome.status, "no_embeddings")
            self.assertEqual(outcome.results, [])
            self.assertEqual(backend.encode_calls, 0)

    def test_dimension_mismatch_is_reported(self):
        with tempfile.TemporaryDirectory() as directory:
            db = Database(Path(directory) / "dimension.sqlite")
            project_id = _project_id(db)
            db.save_code_chunks_for_project(
                project_id,
                [_chunk("auth.py", "authenticate_user"), _chunk("upload.py", "upload_file")],
            )
            chunks = {chunk["qualified_name"]: chunk for chunk in db.get_code_chunks(project_id)}
            db.upsert_code_chunk_embeddings(
                [
                    _record(chunks["authenticate_user"], [1.0, 0.0, 0.0]),
                    _record(chunks["upload_file"], [0.0, 1.0]),
                ]
            )

            with self.assertRaises(ValueError):
                SemanticRetriever(db, _service()).search(project_id, "auth")

    def test_top_k_is_bounded(self):
        with tempfile.TemporaryDirectory() as directory:
            db = Database(Path(directory) / "bounds.sqlite")
            project_id = _project_id(db)
            db.save_code_chunks_for_project(
                project_id,
                [_chunk("a.py", "a"), _chunk("b.py", "b"), _chunk("c.py", "c")],
            )
            chunks = db.get_code_chunks(project_id)
            db.upsert_code_chunk_embeddings([_record(chunk, [1.0, 0.0, 0.0]) for chunk in chunks])
            retriever = SemanticRetriever(db, _service())

            self.assertEqual(len(retriever.search(project_id, "auth", top_k=0).results), 1)
            self.assertEqual(len(retriever.search(project_id, "auth", top_k=999).results), 3)

    def test_result_contains_complete_source_location(self):
        with tempfile.TemporaryDirectory() as directory:
            db = Database(Path(directory) / "source.sqlite")
            project_id = _project_id(db)
            content = "def authenticate_user(password):\n    return verify_password(password)\n"
            db.save_code_chunks_for_project(
                project_id,
                [_chunk("auth.py", "authenticate_user", content=content, start_line=20)],
            )
            chunk = db.get_code_chunks(project_id)[0]
            db.upsert_code_chunk_embeddings([_record(chunk, [1.0, 0.0, 0.0])])

            result = SemanticRetriever(db, _service()).search(project_id, "auth").results[0]

            self.assertEqual(result.code_chunk_id, chunk["id"])
            self.assertEqual(result.path, "auth.py")
            self.assertEqual(result.start_line, 20)
            self.assertEqual(result.end_line, 21)
            self.assertEqual(result.content, content)
            self.assertEqual(result.content_hash, chunk["content_hash"])
            self.assertEqual(result.model_name, MODEL_NAME)

    def test_retriever_has_no_llm_dependency(self):
        with tempfile.TemporaryDirectory() as directory:
            db = Database(Path(directory) / "no-llm.sqlite")
            retriever = SemanticRetriever(db, _service())

            self.assertFalse(hasattr(retriever, "llm"))

    def test_chinese_query_retrieves_english_authentication_chunk(self):
        with tempfile.TemporaryDirectory() as directory:
            db = Database(Path(directory) / "zh.sqlite")
            project_id = _project_id(db)
            db.save_code_chunks_for_project(
                project_id,
                [
                    _chunk("auth.py", "authenticate_user", "def authenticate_user():\n    verify_password()\n"),
                    _chunk("upload.py", "upload_file", "def upload_file():\n    save_file()\n"),
                    _chunk("db.py", "init_database", "def init_database():\n    create_tables()\n"),
                ],
            )
            chunks = {chunk["qualified_name"]: chunk for chunk in db.get_code_chunks(project_id)}
            db.upsert_code_chunk_embeddings(
                [
                    _record(chunks["authenticate_user"], [1.0, 0.0, 0.0]),
                    _record(chunks["upload_file"], [0.0, 1.0, 0.0]),
                    _record(chunks["init_database"], [0.0, 0.0, 1.0]),
                ]
            )

            outcome = SemanticRetriever(db, _service()).search(
                project_id,
                "用户身份是如何验证的？",
            )

            self.assertEqual(outcome.results[0].qualified_name, "authenticate_user")


if __name__ == "__main__":
    unittest.main()
