from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from app.database import Database
from app.services.embedding_service import CODE_CHUNK_TEXT_FORMAT_VERSION, EmbeddingService


DEFAULT_TOP_K = 5
MAX_TOP_K = 50


@dataclass(frozen=True)
class SemanticSearchResult:
    code_chunk_id: int
    path: str
    chunk_type: str
    symbol_name: str
    qualified_name: str
    start_line: int
    end_line: int
    content: str
    content_hash: str
    semantic_score: float
    model_name: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class SemanticSearchOutcome:
    status: str
    results: list[SemanticSearchResult]
    model_name: str
    total_candidates: int
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["results"] = [result.to_dict() for result in self.results]
        return data


class SemanticRetriever:
    def __init__(self, database: Database, embedding_service: EmbeddingService) -> None:
        self.database = database
        self.embedding_service = embedding_service

    def search(
        self,
        project_id: str,
        query: str,
        top_k: int = DEFAULT_TOP_K,
        path: str | None = None,
        chunk_type: str | None = None,
    ) -> SemanticSearchOutcome:
        cleaned_query = query.strip()
        if not cleaned_query:
            raise ValueError("semantic search query must not be empty")
        limit = _bounded_top_k(top_k)
        identity = self.embedding_service.get_model_identity()
        candidates = self.database.get_code_chunk_embeddings_for_project(
            project_id,
            identity.model_name,
            identity.model_revision,
            CODE_CHUNK_TEXT_FORMAT_VERSION,
            path=path,
            chunk_type=chunk_type,
        )
        if not candidates:
            return SemanticSearchOutcome(
                status="no_embeddings",
                results=[],
                model_name=identity.model_name,
                total_candidates=0,
                warnings=["No fresh embeddings are available for this project and filter."],
            )

        dimension = int(candidates[0]["embedding_dimension"])
        for candidate in candidates:
            if int(candidate["embedding_dimension"]) != dimension:
                raise ValueError(
                    f"embedding dimension mismatch in project {project_id} for "
                    f"model {identity.model_name}"
                )

        query_vector = self.embedding_service.encode_query(cleaned_query)
        if len(query_vector) != dimension:
            raise ValueError(
                f"query embedding dimension {len(query_vector)} does not match "
                f"cached dimension {dimension} for project {project_id}"
            )

        scored = [
            (
                _dot(query_vector, candidate["vector"]),
                candidate,
            )
            for candidate in candidates
        ]
        scored.sort(
            key=lambda item: (
                -item[0],
                item[1]["path"],
                int(item[1]["start_line"]),
                int(item[1]["id"]),
            )
        )
        results = [
            SemanticSearchResult(
                code_chunk_id=int(candidate["id"]),
                path=candidate["path"],
                chunk_type=candidate["chunk_type"],
                symbol_name=candidate["symbol_name"],
                qualified_name=candidate["qualified_name"],
                start_line=int(candidate["start_line"]),
                end_line=int(candidate["end_line"]),
                content=candidate["content"],
                content_hash=candidate["content_hash"],
                semantic_score=float(score),
                model_name=identity.model_name,
            )
            for score, candidate in scored[:limit]
        ]
        return SemanticSearchOutcome(
            status="ok",
            results=results,
            model_name=identity.model_name,
            total_candidates=len(candidates),
            warnings=[],
        )


def _bounded_top_k(top_k: int) -> int:
    return min(MAX_TOP_K, max(1, int(top_k)))


def _dot(left: list[float], right: list[float]) -> float:
    if len(left) != len(right):
        raise ValueError("embedding vectors must have the same dimension")
    return sum(a * b for a, b in zip(left, right))
