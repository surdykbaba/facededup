"""Tests for the /enroll endpoint."""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import numpy as np
import pytest

from app.services.face_service import FaceService
from tests.conftest import create_mock_face_analyzer, create_test_image


class TestFaceService:
    """Unit tests for FaceService."""

    def test_detect_and_embed_success(self):
        analyzer = create_mock_face_analyzer()
        svc = FaceService(analyzer)
        image_bytes = create_test_image()

        embedding, face_info = svc.detect_and_embed(image_bytes)

        assert embedding.shape == (512,)
        assert "bbox" in face_info
        assert "det_score" in face_info
        assert face_info["det_score"] > 0.9

    def test_detect_and_embed_no_face(self):
        analyzer = MagicMock()
        analyzer.get.return_value = []  # No faces detected
        svc = FaceService(analyzer)

        from app.core.exceptions import NoFaceDetectedError

        with pytest.raises(NoFaceDetectedError):
            svc.detect_and_embed(create_test_image())

    def test_detect_and_embed_multiple_faces(self):
        analyzer = MagicMock()
        face1 = MagicMock()
        face2 = MagicMock()
        analyzer.get.return_value = [face1, face2]
        svc = FaceService(analyzer)

        from app.core.exceptions import MultipleFacesError

        with pytest.raises(MultipleFacesError):
            svc.detect_and_embed(create_test_image())

    def test_detect_and_embed_invalid_image(self):
        analyzer = create_mock_face_analyzer()
        svc = FaceService(analyzer)

        from app.core.exceptions import InvalidImageError

        with pytest.raises(InvalidImageError):
            svc.detect_and_embed(b"not an image")


class TestImageValidation:
    """Tests for image validation."""

    def test_validate_jpeg(self):
        from app.services.image_service import validate_image

        image = create_test_image()
        fmt = validate_image(image, max_size_mb=10)
        assert fmt == "jpeg"

    def test_validate_too_large(self):
        from app.core.exceptions import ImageTooLargeError
        from app.services.image_service import validate_image

        # Create a "large" image (simulate with low threshold)
        image = create_test_image()
        with pytest.raises(ImageTooLargeError):
            validate_image(image, max_size_mb=0)  # 0 MB limit

    def test_validate_invalid_format(self):
        from app.core.exceptions import InvalidImageError
        from app.services.image_service import validate_image

        with pytest.raises(InvalidImageError):
            validate_image(b"not an image format at all", max_size_mb=10)

    def test_validate_too_small(self):
        from app.core.exceptions import InvalidImageError
        from app.services.image_service import validate_image

        with pytest.raises(InvalidImageError):
            validate_image(b"ab", max_size_mb=10)
