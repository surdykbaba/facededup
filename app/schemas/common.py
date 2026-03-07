from pydantic import BaseModel


class ErrorResponse(BaseModel):
    error: str
    detail: str


class HealthResponse(BaseModel):
    status: str
    database: str
    redis: str
    face_model: str
    gpu_enabled: bool
    anti_spoof_loaded: bool
    version: str
