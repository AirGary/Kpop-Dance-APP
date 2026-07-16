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
    upload_url: str | None = None
    state: str = "active"
    completion_claim_id: str | None = None
    completion_claim_expires_at: datetime | None = None


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

    async def find_completed(
        self,
        owner_id: str,
        job_id: UUID,
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
        claim_id: str,
    ) -> UploadSession | None: ...

    async def claim_completion(
        self,
        upload_id: UUID,
        owner_id: str,
        instant: datetime,
        claim_id: str,
    ) -> UploadSession | None: ...

    async def release_completion(self, upload_id: UUID, claim_id: str) -> None: ...

    async def claim_expired(
        self,
        upload_id: UUID,
        instant: datetime,
    ) -> UploadSession | None: ...

    async def claim_deletion(
        self,
        upload_id: UUID,
        owner_id: str,
    ) -> UploadSession | None: ...

    async def delete(self, upload_id: UUID) -> None: ...

    async def expired_before(self, instant: datetime) -> list[UploadSession]: ...
