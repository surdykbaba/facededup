from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class RecordResponse(BaseModel):
    id: UUID
    name: str | None
    external_id: str | None
    metadata: dict | None
    image_path: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class RecordDeleteResponse(BaseModel):
    id: UUID
    deleted: bool
