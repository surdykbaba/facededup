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
    SIMILARITY_THRESHOLD: float = 0.4

    @property
    def det_size_tuple(self) -> tuple[int, int]:
        parts = self.FACE_DET_SIZE.split(",")
        return (int(parts[0]), int(parts[1]))

    # Liveness detection
    LIVENESS_ENABLED: bool = True
    LIVENESS_ENROLL_REQUIRED: bool = True
    LIVENESS_MATCH_REQUIRED: bool = True
    LIVENESS_COMPARE_REQUIRED: bool = True
    LIVENESS_OPTIONAL_TOLERANCE: int = 3  # how many optional checks can fail
    LIVENESS_DET_SCORE_MIN: float = 0.80
    LIVENESS_SHARPNESS_MIN: float = 50.0
    LIVENESS_SHARPNESS_MAX: float = 2000.0
    LIVENESS_LBP_VARIANCE_MIN: float = 300.0
    LIVENESS_COLOR_STD_MIN: float = 20.0
    LIVENESS_FACE_SIZE_RATIO_MIN: float = 0.03
    LIVENESS_FACE_SIZE_RATIO_MAX: float = 0.85
    LIVENESS_GLARE_RATIO_MAX: float = 0.05
    LIVENESS_LANDMARK_QUALITY_MIN: float = 0.65
    LIVENESS_EMBEDDING_NORM_MIN: float = 15.0
    LIVENESS_EMBEDDING_NORM_MAX: float = 35.0
    LIVENESS_SKIN_PIXEL_RATIO_MIN: float = 0.15
    LIVENESS_SKIN_SAT_MIN: int = 10
    LIVENESS_SKIN_SAT_MAX: int = 220
    LIVENESS_SKIN_SAT_STD_MIN: float = 5.0
    LIVENESS_DCT_HIGH_FREQ_MIN: float = 0.02
    LIVENESS_EDGE_DENSITY_MIN: float = 0.03
    LIVENESS_EDGE_DENSITY_MAX: float = 0.40
    LIVENESS_EDGE_UNIFORMITY_MAX: float = 0.15
    LIVENESS_NOISE_LEVEL_MIN: float = 0.8
    LIVENESS_COLOR_CORR_MIN: float = 0.50

    # Face occlusion detection (masks, sunglasses)
    LIVENESS_LOWER_FACE_SKIN_MIN: float = 0.25  # min skin ratio in lower face (catches masks)
    LIVENESS_EYE_CONTRAST_MIN: float = 15.0  # min gradient contrast in eye region (catches sunglasses)

    # ML Anti-Spoofing (Silent-Face-Anti-Spoofing)
    ANTISPOOF_ENABLED: bool = True
    ANTISPOOF_REAL_SCORE_MIN: float = 0.53

    # Multi-frame liveness detection
    MULTIFRAME_LIVENESS_ENABLED: bool = True
    MULTIFRAME_MIN_FRAMES: int = 3
    MULTIFRAME_MAX_FRAMES: int = 5
    MULTIFRAME_ENROLL_REQUIRED: bool = True
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

    # Frame uniqueness / duplicate detection
    MULTIFRAME_FRAME_HASH_ENABLED: bool = True
    MULTIFRAME_FRAME_HASH_THRESHOLD: int = 5           # pHash Hamming distance; 0=identical, <5=near-dup
    MULTIFRAME_FRAME_EMBEDDING_SIM_MAX: float = 0.998  # max cosine similarity between any two frames

    # Duplicate detection at enrollment
    ENROLL_DEDUP_ENABLED: bool = True

    # Docs page password (set via DOCS_PASSWORD env var to protect the docs page)
    DOCS_PASSWORD: str = ""

    # Storage
    IMAGE_STORAGE_PATH: str = "/data/images"
    MAX_IMAGE_SIZE_MB: int = 10

    # Server
    WORKERS: int = 2


@lru_cache
def get_settings() -> Settings:
    return Settings()
