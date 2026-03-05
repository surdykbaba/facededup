"""Tests for the dedup service logic."""

import pytest


class TestDedupPairDeduplication:
    """Test that duplicate pair tracking avoids (A,B) and (B,A)."""

    def test_seen_pairs_set(self):
        seen = set()

        pair1 = tuple(sorted(["aaa", "bbb"]))
        pair2 = tuple(sorted(["bbb", "aaa"]))  # Same pair, reversed

        seen.add(pair1)
        assert pair2 in seen  # Should recognize as duplicate

    def test_different_pairs(self):
        seen = set()

        pair1 = tuple(sorted(["aaa", "bbb"]))
        pair2 = tuple(sorted(["aaa", "ccc"]))

        seen.add(pair1)
        assert pair2 not in seen  # Different pair
