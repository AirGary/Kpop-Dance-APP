from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from api.app.schemas.analysis import AnalysisJobState


class CreateJobRequest(BaseModel):
    model_config = ConfigDict(frozen=True, populate_by_name=True)

    project_id: UUID = Field(alias="projectId")
    source_fingerprint: str = Field(
        alias="sourceFingerprint",
        min_length=8,
        max_length=128,
        pattern=r"^[A-Za-z0-9:_-]+$",
    )
    duration_seconds: float = Field(alias="durationSeconds", gt=0, le=360)
    byte_count: int = Field(alias="byteCount", gt=0, le=2_147_483_648)
    mime_type: Literal["video/mp4", "video/quicktime"] = Field(alias="mimeType")


class JobResponse(BaseModel):
    model_config = ConfigDict(frozen=True, populate_by_name=True)

    id: UUID
    project_id: UUID = Field(alias="projectId")
    state: AnalysisJobState = AnalysisJobState.DRAFT
    progress: float = Field(default=0, ge=0, le=1)
    error_code: str | None = Field(default=None, alias="errorCode")
    created_at: datetime = Field(alias="createdAt")
    updated_at: datetime = Field(alias="updatedAt")
