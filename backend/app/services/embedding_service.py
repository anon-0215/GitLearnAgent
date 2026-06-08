from __future__ import annotations

import hashlib
import importlib.util
import math
from dataclasses import asdict, dataclass
from pathlib import Path
from threading import RLock
from typing import Any, Callable, Protocol, Sequence

from app.config import EmbeddingSettings, get_embedding_settings
from app.database import _as_float32


CODE_CHUNK_TEXT_FORMAT_VERSION = "code-chunk-v1"


class EmbeddingError(RuntimeError):
    pass


class EmbeddingConfigurationError(EmbeddingError):
    pass


class EmbeddingModelLoadError(EmbeddingError):
    pass


class EmbeddingEncodeError(EmbeddingError):
    pass


@dataclass(frozen=True)
class EmbeddingModelIdentity:
    model_name: str
    model_revision: str
    device: str

    def to_dict(self) -> dict[str, str]:
        return asdict(self)


class EmbeddingBackend(Protocol):
    def load_model(
        self,
        model_name_or_path: str,
        device: str,
        cache_dir: Path,
        max_length: int,
    ) -> None:
        ...

    def encode(
        self,
        texts: Sequence[str],
        batch_size: int,
        normalize: bool,
    ) -> Any:
        ...

    def get_embedding_dimension(self) -> int | None:
        ...

    def unload_model(self) -> None:
        ...


class SentenceTransformerEmbeddingBackend:
    def __init__(self) -> None:
        self._model: Any | None = None

    def load_model(
        self,
        model_name_or_path: str,
        device: str,
        cache_dir: Path,
        max_length: int,
    ) -> None:
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as exc:
            raise EmbeddingModelLoadError(
                "sentence-transformers is not installed; install backend requirements "
                "before enabling embeddings."
            ) from exc

        cache_dir.mkdir(parents=True, exist_ok=True)
        model = SentenceTransformer(
            model_name_or_path,
            device=device,
            cache_folder=str(cache_dir),
        )
        if max_length > 0 and hasattr(model, "max_seq_length"):
            model.max_seq_length = max_length
        self._model = model

    def encode(
        self,
        texts: Sequence[str],
        batch_size: int,
        normalize: bool,
    ) -> Any:
        if self._model is None:
            raise EmbeddingModelLoadError("embedding model is not loaded")
        return self._model.encode(
            list(texts),
            batch_size=batch_size,
            normalize_embeddings=normalize,
            convert_to_numpy=True,
            show_progress_bar=False,
        )

    def get_embedding_dimension(self) -> int | None:
        if self._model is None:
            return None
        dimension = self._model.get_sentence_embedding_dimension()
        return int(dimension) if dimension else None

    def unload_model(self) -> None:
        self._model = None


class EmbeddingService:
    def __init__(
        self,
        settings: EmbeddingSettings | None = None,
        backend_factory: Callable[[], EmbeddingBackend] | None = None,
        cuda_available: Callable[[], bool] | None = None,
    ) -> None:
        self.settings = settings or get_embedding_settings()
        self._backend_is_injected = backend_factory is not None
        self._backend_factory = backend_factory or SentenceTransformerEmbeddingBackend
        self._cuda_available = cuda_available or _torch_cuda_available
        self._backend: EmbeddingBackend | None = None
        self._identity: EmbeddingModelIdentity | None = None
        self._dimension: int | None = None
        self._lock = RLock()

    def load_model(self) -> None:
        with self._lock:
            if self._backend is not None:
                return
            if not self.settings.enabled:
                raise EmbeddingConfigurationError("embeddings are disabled by EMBEDDING_ENABLED")
            device = resolve_embedding_device(self.settings.device, self._cuda_available)
            identity = build_model_identity(self.settings.model_name_or_path, device)
            backend = self._backend_factory()
            try:
                backend.load_model(
                    self.settings.model_name_or_path,
                    device,
                    self.settings.cache_dir,
                    self.settings.max_length,
                )
            except EmbeddingError:
                raise
            except Exception as exc:
                raise EmbeddingModelLoadError(
                    f"failed to load embedding model {identity.model_name} on {device}"
                ) from exc
            self._backend = backend
            self._identity = identity
            self._dimension = backend.get_embedding_dimension()

    def encode_documents(self, texts: Sequence[str]) -> list[list[float]]:
        if not texts:
            return []
        prefixed = [self.settings.document_prefix + text for text in texts]
        return self._encode(prefixed, "documents")

    def encode_query(self, text: str) -> list[float]:
        query = text.strip()
        if not query:
            raise EmbeddingEncodeError("embedding query must not be empty")
        return self._encode([self.settings.query_prefix + query], "query")[0]

    def get_model_identity(self) -> EmbeddingModelIdentity:
        if self._identity is not None:
            return self._identity
        device = (
            self.settings.device
            if self.settings.device != "auto"
            else ("cuda" if self._cuda_available() else "cpu")
        )
        return build_model_identity(self.settings.model_name_or_path, device)

    def get_embedding_dimension(self) -> int | None:
        if self._dimension is None:
            self.load_model()
        return self._dimension

    def unload_model(self) -> None:
        with self._lock:
            if self._backend is not None:
                self._backend.unload_model()
            self._backend = None
            self._identity = None
            self._dimension = None

    def is_available(self) -> bool:
        if not self.settings.enabled:
            return False
        if self._backend is not None:
            return True
        if self._backend_is_injected:
            return True
        return importlib.util.find_spec("sentence_transformers") is not None

    def _encode(self, texts: Sequence[str], operation: str) -> list[list[float]]:
        with self._lock:
            self.load_model()
            assert self._backend is not None
            identity = self.get_model_identity()
            try:
                raw_vectors = self._backend.encode(
                    texts,
                    batch_size=self.settings.batch_size,
                    normalize=self.settings.normalize,
                )
            except EmbeddingError:
                raise
            except Exception as exc:
                raise EmbeddingEncodeError(
                    f"failed to encode {len(texts)} {operation} with {identity.model_name}"
                ) from exc
            vectors = coerce_embedding_batch(raw_vectors, self.settings.normalize)
            if len(vectors) != len(texts):
                raise EmbeddingEncodeError(
                    f"embedding backend returned {len(vectors)} vectors for "
                    f"{len(texts)} {operation}"
                )
            if vectors:
                dimension = len(vectors[0])
                if any(len(vector) != dimension for vector in vectors):
                    raise EmbeddingEncodeError("embedding backend returned inconsistent dimensions")
                self._dimension = dimension
            return vectors


def build_code_chunk_document_text(chunk: dict[str, Any]) -> str:
    path = str(chunk.get("path", "")).replace("\\", "/").lstrip("/")
    chunk_type = str(chunk.get("chunk_type", ""))
    symbol = str(chunk.get("qualified_name") or chunk.get("symbol_name") or "")
    content = str(chunk.get("content", ""))
    return "\n".join(
        [
            f"format: {CODE_CHUNK_TEXT_FORMAT_VERSION}",
            f"path: {path}",
            f"type: {chunk_type}",
            f"symbol: {symbol}",
            "code:",
            content,
        ]
    )


def resolve_embedding_device(
    requested_device: str,
    cuda_available: Callable[[], bool] | None = None,
) -> str:
    requested = (requested_device or "auto").lower()
    has_cuda = (cuda_available or _torch_cuda_available)()
    if requested == "auto":
        return "cuda" if has_cuda else "cpu"
    if requested == "cpu":
        return "cpu"
    if requested == "cuda" or requested.startswith("cuda:"):
        if not has_cuda:
            raise EmbeddingConfigurationError(
                f"EMBEDDING_DEVICE={requested_device} was requested, but CUDA is not available"
            )
        return requested
    raise EmbeddingConfigurationError(f"unsupported EMBEDDING_DEVICE value: {requested_device}")


def build_model_identity(model_name_or_path: str, device: str) -> EmbeddingModelIdentity:
    raw = model_name_or_path.strip() or "BAAI/bge-m3"
    path = Path(raw)
    looks_local = path.exists() or path.is_absolute() or "\\" in raw or raw.startswith(".")
    if looks_local:
        resolved = path.expanduser().resolve(strict=False)
        digest = hashlib.sha256(str(resolved).encode("utf-8")).hexdigest()[:16]
        safe_name = f"local:{resolved.name or 'embedding-model'}"
        return EmbeddingModelIdentity(safe_name, f"path-sha256:{digest}", device)
    return EmbeddingModelIdentity(raw, "", device)


def coerce_embedding_batch(raw_vectors: Any, normalize: bool) -> list[list[float]]:
    if hasattr(raw_vectors, "tolist"):
        raw_vectors = raw_vectors.tolist()
    if raw_vectors is None:
        return []
    vectors = list(raw_vectors)
    if not vectors:
        return []
    if vectors and not isinstance(vectors[0], (list, tuple)):
        vectors = [vectors]
    coerced = [_coerce_vector(vector) for vector in vectors]
    return [_normalize_vector(vector) for vector in coerced] if normalize else coerced


def _coerce_vector(vector: Sequence[float]) -> list[float]:
    values = [_as_float32(value) for value in vector]
    if not values:
        raise EmbeddingEncodeError("embedding backend returned an empty vector")
    return values


def _normalize_vector(vector: Sequence[float]) -> list[float]:
    norm = math.sqrt(sum(value * value for value in vector))
    if norm == 0:
        return [_as_float32(value) for value in vector]
    return [_as_float32(value / norm) for value in vector]


def _torch_cuda_available() -> bool:
    try:
        import torch
    except ImportError:
        return False
    return bool(torch.cuda.is_available())
