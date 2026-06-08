import math
import struct
import unittest
from pathlib import Path

from app.config import EmbeddingSettings
from app.services.embedding_service import (
    CODE_CHUNK_TEXT_FORMAT_VERSION,
    EmbeddingConfigurationError,
    EmbeddingEncodeError,
    EmbeddingService,
    build_code_chunk_document_text,
)


def _settings(**overrides):
    values = {
        "enabled": True,
        "model_name_or_path": "fake-model",
        "device": "auto",
        "batch_size": 2,
        "max_length": 128,
        "normalize": True,
        "cache_dir": Path("embedding-cache"),
        "query_prefix": "",
        "document_prefix": "",
    }
    values.update(overrides)
    return EmbeddingSettings(**values)


class FakeEmbeddingBackend:
    def __init__(self, vector_fn=None, fail=False):
        self.vector_fn = vector_fn or (lambda text: [3.0, 4.0])
        self.fail = fail
        self.load_calls = 0
        self.encode_calls = []
        self.loaded_device = None

    def load_model(self, model_name_or_path, device, cache_dir, max_length):
        self.load_calls += 1
        self.loaded_device = device
        self.loaded_model = model_name_or_path
        self.loaded_cache_dir = cache_dir
        self.loaded_max_length = max_length

    def encode(self, texts, batch_size, normalize):
        self.encode_calls.append((list(texts), batch_size, normalize))
        if self.fail:
            raise RuntimeError("backend exploded")
        return [self.vector_fn(text) for text in texts]

    def get_embedding_dimension(self):
        return 2

    def unload_model(self):
        self.loaded_device = None


class EmbeddingServiceTests(unittest.TestCase):
    def test_model_is_loaded_lazily(self):
        backend = FakeEmbeddingBackend()
        service = EmbeddingService(
            _settings(),
            backend_factory=lambda: backend,
            cuda_available=lambda: False,
        )

        self.assertEqual(backend.load_calls, 0)
        self.assertEqual(service.encode_documents([]), [])
        self.assertEqual(backend.load_calls, 0)

        service.encode_documents(["hello"])
        self.assertEqual(backend.load_calls, 1)

    def test_auto_device_prefers_cuda_when_available(self):
        backend = FakeEmbeddingBackend()
        service = EmbeddingService(
            _settings(device="auto"),
            backend_factory=lambda: backend,
            cuda_available=lambda: True,
        )

        service.load_model()

        self.assertEqual(backend.loaded_device, "cuda")

    def test_forced_cpu_uses_cpu_even_when_cuda_is_available(self):
        backend = FakeEmbeddingBackend()
        service = EmbeddingService(
            _settings(device="cpu"),
            backend_factory=lambda: backend,
            cuda_available=lambda: True,
        )

        service.load_model()

        self.assertEqual(backend.loaded_device, "cpu")

    def test_forced_cuda_fails_clearly_when_cuda_is_unavailable(self):
        backend = FakeEmbeddingBackend()
        service = EmbeddingService(
            _settings(device="cuda"),
            backend_factory=lambda: backend,
            cuda_available=lambda: False,
        )

        with self.assertRaises(EmbeddingConfigurationError) as context:
            service.load_model()

        self.assertIn("CUDA is not available", str(context.exception))
        self.assertEqual(backend.load_calls, 0)

    def test_empty_document_list_does_not_call_model(self):
        backend = FakeEmbeddingBackend()
        service = EmbeddingService(
            _settings(),
            backend_factory=lambda: backend,
            cuda_available=lambda: False,
        )

        self.assertEqual(service.encode_documents([]), [])
        self.assertEqual(backend.encode_calls, [])

    def test_batch_encoding_uses_configured_batch_size(self):
        backend = FakeEmbeddingBackend()
        service = EmbeddingService(
            _settings(batch_size=7),
            backend_factory=lambda: backend,
            cuda_available=lambda: False,
        )

        vectors = service.encode_documents(["one", "two"])

        self.assertEqual(len(vectors), 2)
        self.assertEqual(backend.encode_calls[0][1], 7)

    def test_outputs_are_float32_values(self):
        backend = FakeEmbeddingBackend(lambda text: [1.0 / 3.0, 2.0 / 3.0])
        service = EmbeddingService(
            _settings(normalize=False),
            backend_factory=lambda: backend,
            cuda_available=lambda: False,
        )

        value = service.encode_documents(["x"])[0][0]

        self.assertEqual(value, struct.unpack("<f", struct.pack("<f", value))[0])

    def test_normalized_vectors_have_unit_norm(self):
        backend = FakeEmbeddingBackend(lambda text: [3.0, 4.0])
        service = EmbeddingService(
            _settings(normalize=True),
            backend_factory=lambda: backend,
            cuda_available=lambda: False,
        )

        vector = service.encode_documents(["x"])[0]

        self.assertAlmostEqual(math.sqrt(sum(value * value for value in vector)), 1.0, places=6)

    def test_model_loads_only_once_across_requests(self):
        backend = FakeEmbeddingBackend()
        service = EmbeddingService(
            _settings(),
            backend_factory=lambda: backend,
            cuda_available=lambda: False,
        )

        service.encode_documents(["one"])
        service.encode_query("question")

        self.assertEqual(backend.load_calls, 1)

    def test_fake_backend_reports_available_without_sentence_transformers(self):
        backend = FakeEmbeddingBackend()
        service = EmbeddingService(
            _settings(),
            backend_factory=lambda: backend,
            cuda_available=lambda: False,
        )

        self.assertTrue(service.is_available())

    def test_encoding_exception_has_context(self):
        backend = FakeEmbeddingBackend(fail=True)
        service = EmbeddingService(
            _settings(),
            backend_factory=lambda: backend,
            cuda_available=lambda: False,
        )

        with self.assertRaises(EmbeddingEncodeError) as context:
            service.encode_documents(["secret source code"])

        message = str(context.exception)
        self.assertIn("failed to encode 1 documents", message)
        self.assertIn("fake-model", message)
        self.assertNotIn("secret source code", message)

    def test_code_chunk_document_text_format_is_fixed(self):
        text = build_code_chunk_document_text(
            {
                "path": "app\\services\\auth.py",
                "chunk_type": "method",
                "qualified_name": "AuthService.authenticate",
                "content": "def authenticate():\n    return True\n",
            }
        )

        self.assertEqual(
            text,
            "\n".join(
                [
                    f"format: {CODE_CHUNK_TEXT_FORMAT_VERSION}",
                    "path: app/services/auth.py",
                    "type: method",
                    "symbol: AuthService.authenticate",
                    "code:",
                    "def authenticate():\n    return True\n",
                ]
            ),
        )


if __name__ == "__main__":
    unittest.main()
