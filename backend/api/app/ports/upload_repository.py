from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from uuid import UUID

from api.app.schemas.uploads import CreateUploadRequest


@dataclass(frozen=True, slots=True)
class UploadSession:
    id: UUID
    owner_id: str
    request: CreateUploadRequest
    request_digest: str
    idempotency_key: str
    token_digest: str
    offset: int
    expires_at: datetime
    completed_job_id: UUID | None = None


class UploadIdempotencyConflictError(Exception):
    pass


class UploadRepository(Protocol):
    async def create(self, session: UploadSession) -> tuple[UploadSession, bool]: ...

    async def get(self, upload_id: UUID) -> UploadSession | None: ...

    async def find_idempotent(
        self,
        owner_id: str,
        idempotency_key: str,
    ) -> UploadSession | None: ...

    async def update_offset(
        self,
        upload_id: UUID,
        expected: int,
        new: int,
    ) -> bool: ...

    async def update_token_digest(
        self,
        upload_id: UUID,
        token_digest: str,
    ) -> UploadSession: ...

    async def mark_completed(
        self,
        upload_id: UUID,
        job_id: UUID,
    ) -> UploadSession: ...

    async def delete(self, upload_id: UUID) -> None: ...

    async def expired_before(self, instant: datetime) -> list[UploadSession]: ...
