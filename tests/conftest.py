import uuid
from io import BytesIO
from unittest.mock import MagicMock

import numpy as np
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from PIL import Image

from app.config import Settings, get_settings
from app.main import create_app


def create_test_image(width: int = 200, height: int = 200) -> bytes:
    """Create a simple JPEG test image."""
    img = Image.new("RGB", (width, height), color=(128, 128, 128))
    buf = BytesIO()
    img.save(buf, format="JPEG")
    return buf.getvalue()


def create_mock_face_analyzer():
    """Create a mock InsightFace analyzer that returns deterministic embeddings."""
    mock = MagicMock()
    fake_face = MagicMock()

    # Deterministic normalized embedding
    rng = np.random.RandomState(42)
    embedding = rng.randn(512).astype(np.float32)
    embedding /= np.linalg.norm(embedding)
    fake_face.normed_embedding = embedding
    fake_face.bbox = np.array([10.0, 20.0, 100.0, 200.0])
    fake_face.det_score = np.float32(0.99)
    fake_face.age = 30
    fake_face.gender = 1

    mock.get.return_value = [fake_face]
    return mock


@pytest.fixture
def test_settings(tmp_path):
    """Override settings for testing."""

    def _get_test_settings():
        return Settings(
            DATABASE_URL="postgresql+asyncpg://facededup:changeme@localhost:5432/facededup_test",
            REDIS_URL="redis://localhost:6379/1",
            API_KEYS="test-api-key-12345",
            IMAGE_STORAGE_PATH=str(tmp_path / "images"),
            FACE_MODEL_NAME="buffalo_l",
            DEBUG=True,
            LOG_LEVEL="DEBUG",
        )

    return _get_test_settings


@pytest.fixture
def mock_face_analyzer():
    return create_mock_face_analyzer()


@pytest.fixture
def test_image_bytes():
    return create_test_image()


@pytest.fixture
def api_key_header():
    return {"X-API-Key": "test-api-key-12345"}
