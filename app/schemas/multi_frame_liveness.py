from pydantic import BaseModel, Field


class ActiveCheck(BaseModel):
    score: float
    passed: bool
    detail: str
    mandatory: bool = True


class ActiveChecksResult(BaseModel):
    checks_passed: int
    checks_total: int
    all_passed: bool
    checks: dict[str, ActiveCheck]


class PassiveFrameResult(BaseModel):
    frame_index: int
    is_live: bool
    liveness_score: float = Field(ge=0.0, le=1.0)
    checks_passed: int
    checks_total: int


class PassiveChecksResult(BaseModel):
    all_passed: bool
    per_frame: list[PassiveFrameResult]


class MultiFrameLivenessResponse(BaseModel):
    is_live: bool
    liveness_score: float = Field(ge=0.0, le=1.0)
    mode: str = "multi_frame"
    frame_count: int
    passive_checks: PassiveChecksResult
    active_checks: ActiveChecksResult
    face_info: dict
