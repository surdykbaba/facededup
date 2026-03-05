from pydantic import BaseModel, Field


class CompareResponse(BaseModel):
    similarity: float = Field(ge=0.0, le=1.0)
    match: bool
    threshold: float
    face_a_info: dict
    face_b_info: dict
