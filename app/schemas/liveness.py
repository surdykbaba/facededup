from pydantic import BaseModel, Field


class LivenessCheck(BaseModel):
    score: float
    passed: bool
    detail: str
    mandatory: bool = False


class LivenessResponse(BaseModel):
    is_live: bool
    liveness_score: float = Field(ge=0.0, le=1.0)
    checks_passed: int
    checks_total: int
    mandatory_checks_passed: int
    mandatory_checks_total: int
    checks: dict[str, LivenessCheck]
    face_info: dict
