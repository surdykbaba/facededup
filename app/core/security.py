import secrets

from fastapi import HTTPException, Security, status
from fastapi.security import APIKeyHeader

from app.config import get_settings

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


async def verify_api_key(
    api_key: str | None = Security(api_key_header),
) -> str:
    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing API key",
        )
    settings = get_settings()
    valid_keys = settings.api_key_list
    if not any(secrets.compare_digest(api_key, k) for k in valid_keys):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid API key",
        )
    return api_key
