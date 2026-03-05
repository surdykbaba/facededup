from pydantic import BaseModel, Field


class LivenessCheck(BaseModel):
    score: float
    passed: bool
    detail: str


class LivenessResponse(BaseModel):
    is_live: bool
    liveness_score: float = Field(ge=0.0, le=1.0)
    checks_passed: int
    checks_total: int
    checks: dict[str, LivenessCheck]
    face_info: dict
