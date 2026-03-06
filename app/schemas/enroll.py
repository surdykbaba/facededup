from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class EnrollResponse(BaseModel):
    id: UUID
    name: str | None
    external_id: str | None
    face_info: dict
    liveness_info: dict | None = None
    liveness_mode: str | None = None
    duplicate_info: dict | None = None
    created_at: datetime

    model_config = {"from_attributes": True}
