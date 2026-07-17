from enum import Enum
from pathlib import PurePosixPath
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class AnalysisJobState(str, Enum):
    DRAFT = "draft"
    PREPARING = "preparing"
    UPLOADING = "uploading"
    UPLOADED = "uploaded"
    DETECTING = "detecting"
    AWAITING_TARGET = "awaitingTarget"
    QUEUED = "queued"
    ANALYZING = "analyzing"
    AWAITING_CONFIRMATION = "awaitingConfirmation"
    RESULT_READY = "resultReady"
    IMPORTING = "importing"
    COMPLETED = "completed"
    FAILED_RECOVERABLE = "failedRecoverable"
    FAILED_TERMINAL = "failedTerminal"
    CANCELLING = "cancelling"
    DELETED = "deleted"


class AppearanceInterval(BaseModel):
    model_config = ConfigDict(frozen=True, populate_by_name=True)

    start_seconds: float = Field(alias="startSeconds", ge=0, allow_inf_nan=False)
    end_seconds: float = Field(alias="endSeconds", gt=0, allow_inf_nan=False)

    @model_validator(mode="after")
    def end_must_follow_start(self) -> "AppearanceInterval":
        if self.end_seconds <= self.start_seconds:
            raise ValueError("endSeconds must be greater than startSeconds.")
        return self


class NormalizedBoxSummary(BaseModel):
    model_config = ConfigDict(frozen=True, populate_by_name=True)

    x: float = Field(ge=0, le=1, allow_inf_nan=False)
    y: float = Field(ge=0, le=1, allow_inf_nan=False)
    width: float = Field(gt=0, le=1, allow_inf_nan=False)
    height: float = Field(gt=0, le=1, allow_inf_nan=False)

    @model_validator(mode="after")
    def box_must_remain_normalized(self) -> "NormalizedBoxSummary":
        if self.x + self.width > 1 or self.y + self.height > 1:
            raise ValueError("Normalized box must remain within 0...1.")
        return self


class DancerCandidateResponse(BaseModel):
    model_config = ConfigDict(frozen=True, populate_by_name=True)

    candidate_id: str = Field(alias="candidateId", min_length=1, max_length=128)
    representative_image_paths: tuple[str, str, str] = Field(
        alias="representativeImagePaths"
    )
    appearance_intervals: tuple[AppearanceInterval, ...] = Field(
        alias="appearanceIntervals",
        min_length=1,
    )
    box_summary: NormalizedBoxSummary = Field(alias="boxSummary")
    confidence: float = Field(ge=0, le=1, allow_inf_nan=False)

    @field_validator("representative_image_paths")
    @classmethod
    def image_paths_must_be_relative(cls, paths: tuple[str, str, str]) -> tuple[str, str, str]:
        return tuple(_relative_content_path(path) for path in paths)  # type: ignore[return-value]


class SelectTargetRequest(BaseModel):
    model_config = ConfigDict(frozen=True, populate_by_name=True)

    candidate_id: str = Field(alias="candidateId", min_length=1, max_length=128)


class AnalysisResultResponse(BaseModel):
    model_config = ConfigDict(frozen=True, populate_by_name=True)

    schema_version: Literal[1] = Field(alias="schemaVersion")
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    byte_count: int = Field(alias="byteCount", gt=0)
    content_path: str = Field(alias="contentPath", min_length=1)

    @field_validator("content_path")
    @classmethod
    def content_path_must_be_relative(cls, path: str) -> str:
        return _relative_content_path(path)


class AnalysisErrorDetail(BaseModel):
    model_config = ConfigDict(frozen=True, populate_by_name=True)

    code: str = Field(min_length=1, max_length=128)
    message: str = Field(min_length=1, max_length=512)
    retryable: bool


def _relative_content_path(path: str) -> str:
    candidate = PurePosixPath(path)
    if (
        not path
        or candidate.is_absolute()
        or "\\" in path
        or any(part in {"", ".", ".."} for part in candidate.parts)
    ):
        raise ValueError("Content paths must be relative, normalized POSIX paths.")
    return path
