from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class CreateUploadRequest(BaseModel):
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
    mime_type: Literal["video/mp4"] = Field(alias="mimeType")
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class UploadSessionResponse(BaseModel):
    model_config = ConfigDict(frozen=True, populate_by_name=True)

    upload_id: UUID = Field(alias="uploadId")
    upload_url: str = Field(alias="uploadUrl")
    expires_at: datetime = Field(alias="expiresAt")
    chunk_size: int = Field(alias="chunkSize")
    offset: int = Field(ge=0)
