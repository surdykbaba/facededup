"""Tests for security (API key authentication)."""

import pytest

from app.core.security import verify_api_key
from app.config import Settings


class TestAPIKeyValidation:
    """Tests for API key verification logic."""

    @pytest.mark.asyncio
    async def test_missing_api_key(self):
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc_info:
            await verify_api_key(api_key=None)
        assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    async def test_empty_api_key(self):
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc_info:
            await verify_api_key(api_key="")
        assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    async def test_invalid_api_key(self):
        from fastapi import HTTPException
        from unittest.mock import patch

        mock_settings = Settings(API_KEYS="valid-key-123")
        with patch("app.core.security.get_settings", return_value=mock_settings):
            with pytest.raises(HTTPException) as exc_info:
                await verify_api_key(api_key="wrong-key")
            assert exc_info.value.status_code == 403

    @pytest.mark.asyncio
    async def test_valid_api_key(self):
        from unittest.mock import patch

        mock_settings = Settings(API_KEYS="valid-key-123")
        with patch("app.core.security.get_settings", return_value=mock_settings):
            result = await verify_api_key(api_key="valid-key-123")
            assert result == "valid-key-123"

    @pytest.mark.asyncio
    async def test_multiple_api_keys(self):
        from unittest.mock import patch

        mock_settings = Settings(API_KEYS="key1,key2,key3")
        with patch("app.core.security.get_settings", return_value=mock_settings):
            result = await verify_api_key(api_key="key2")
            assert result == "key2"
