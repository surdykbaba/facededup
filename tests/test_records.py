"""Tests for the /records endpoint."""

import uuid

import pytest

from app.core.exceptions import RecordNotFoundError


class TestRecordNotFound:
    """Test record not found error."""

    def test_record_not_found_error(self):
        err = RecordNotFoundError("Record abc not found")
        assert err.status_code == 404
        assert "abc" in str(err)

    def test_default_message(self):
        err = RecordNotFoundError()
        assert err.status_code == 404
        assert "not found" in err.detail.lower()
