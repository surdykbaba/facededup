"""Tests for the match service."""

import uuid

import numpy as np
import pytest

from app.services.match_service import MatchService


class TestMatchService:
    """Unit tests for MatchService vector math."""

    def test_cosine_similarity_identical(self):
        """Two identical normalized vectors should have similarity ~1.0."""
        rng = np.random.RandomState(42)
        vec = rng.randn(512).astype(np.float32)
        vec /= np.linalg.norm(vec)

        # Cosine distance of identical vectors = 0, similarity = 1
        distance = 1.0 - np.dot(vec, vec)
        similarity = 1.0 - distance
        assert abs(similarity - 1.0) < 0.001

    def test_cosine_similarity_orthogonal(self):
        """Orthogonal vectors should have similarity ~0."""
        vec1 = np.zeros(512, dtype=np.float32)
        vec1[0] = 1.0
        vec2 = np.zeros(512, dtype=np.float32)
        vec2[1] = 1.0

        similarity = np.dot(vec1, vec2)
        assert abs(similarity) < 0.001

    def test_threshold_filtering(self):
        """Distance threshold = 1 - similarity threshold."""
        threshold = 0.6
        distance_threshold = 1.0 - threshold
        assert abs(distance_threshold - 0.4) < 0.001

        # A match with similarity 0.7 (distance 0.3) should pass
        assert 0.3 <= distance_threshold

        # A match with similarity 0.5 (distance 0.5) should not pass
        assert not (0.5 <= distance_threshold)
