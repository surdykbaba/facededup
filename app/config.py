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

    # Liveness detection
    LIVENESS_ENABLED: bool = True
    LIVENESS_ENROLL_REQUIRED: bool = True
    LIVENESS_DET_SCORE_MIN: float = 0.85
    LIVENESS_SHARPNESS_MIN: float = 80.0
    LIVENESS_SHARPNESS_MAX: float = 2000.0
    LIVENESS_LBP_VARIANCE_MIN: float = 400.0
    LIVENESS_COLOR_STD_MIN: float = 20.0
    LIVENESS_FACE_SIZE_RATIO_MIN: float = 0.05
    LIVENESS_FACE_SIZE_RATIO_MAX: float = 0.80
    LIVENESS_GLARE_RATIO_MAX: float = 0.05
    LIVENESS_LANDMARK_QUALITY_MIN: float = 0.65
    LIVENESS_EMBEDDING_NORM_MIN: float = 15.0
    LIVENESS_EMBEDDING_NORM_MAX: float = 35.0
    LIVENESS_SKIN_PIXEL_RATIO_MIN: float = 0.15
    LIVENESS_SKIN_SAT_MIN: int = 15
    LIVENESS_SKIN_SAT_MAX: int = 200
    LIVENESS_DCT_HIGH_FREQ_MIN: float = 0.02
    LIVENESS_EDGE_DENSITY_MIN: float = 0.04
    LIVENESS_EDGE_DENSITY_MAX: float = 0.35

    # Multi-frame liveness detection
    MULTIFRAME_LIVENESS_ENABLED: bool = True
    MULTIFRAME_MIN_FRAMES: int = 3
    MULTIFRAME_MAX_FRAMES: int = 5
    MULTIFRAME_ENROLL_REQUIRED: bool = False
    MULTIFRAME_IDENTITY_SIM_MIN: float = 0.65
    MULTIFRAME_LANDMARK_DISP_MIN: float = 0.008
    MULTIFRAME_LANDMARK_DISP_MAX: float = 0.25
    MULTIFRAME_POSE_RANGE_MIN: float = 1.5
    MULTIFRAME_POSE_COMBINED_MIN: float = 3.0
    MULTIFRAME_POSE_ASYMMETRY_RANGE_MIN: float = 0.02
    MULTIFRAME_FLOW_MAG_MIN: float = 0.3
    MULTIFRAME_FLOW_MAG_MAX: float = 15.0
    MULTIFRAME_FLOW_DIR_STD_MIN: float = 0.3
    MULTIFRAME_BBOX_SHIFT_STD_MIN: float = 0.003
    MULTIFRAME_BBOX_SHIFT_MAX: float = 0.15

    # Storage
    IMAGE_STORAGE_PATH: str = "/data/images"
    MAX_IMAGE_SIZE_MB: int = 10

    # Server
    WORKERS: int = 2


@lru_cache
def get_settings() -> Settings:
    return Settings()
