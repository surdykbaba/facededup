from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    # App
    APP_NAME: str = "FaceDedup API"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = False
    LOG_LEVEL: str = "INFO"
    API_V1_PREFIX: str = "/api/v1"

    # Database
    DATABASE_URL: str = "postgresql+asyncpg://facededup:changeme@postgres:5432/facededup"
    DB_POOL_SIZE: int = 5
    DB_MAX_OVERFLOW: int = 10

    # Redis
    REDIS_URL: str = "redis://redis:6379/0"

    # Security
    API_KEYS: str = ""  # Comma-separated

    @property
    def api_key_list(self) -> list[str]:
        return [k.strip() for k in self.API_KEYS.split(",") if k.strip()]

    # Rate limiting
    RATE_LIMIT_REQUESTS: int = 60
    RATE_LIMIT_WINDOW_SECONDS: int = 60

    # Face detection
    FACE_MODEL_NAME: str = "buffalo_l"
    FACE_DET_SIZE: str = "640,640"
    SIMILARITY_THRESHOLD: float = 0.6

    @property
    def det_size_tuple(self) -> tuple[int, int]:
        parts = self.FACE_DET_SIZE.split(",")
        return (int(parts[0]), int(parts[1]))

    # Storage
    IMAGE_STORAGE_PATH: str = "/data/images"
    MAX_IMAGE_SIZE_MB: int = 10

    # Server
    WORKERS: int = 2


@lru_cache
def get_settings() -> Settings:
    return Settings()
