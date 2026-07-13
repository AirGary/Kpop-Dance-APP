from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

from api.app.schemas.jobs import JobResponse


@dataclass(frozen=True, slots=True)
class JobRecord:
    owner_id: str
    idempotency_key: str
    request_hash: str
    response: JobResponse


class JobNotFoundError(Exception):
    pass


class IdempotencyConflictError(Exception):
    pass


class JobRepository(Protocol):
    async def create(self, record: JobRecord) -> tuple[JobRecord, bool]: ...

    async def get_for_owner(self, job_id: UUID, owner_id: str) -> JobRecord: ...

    async def find_by_idempotency_key(
        self,
        owner_id: str,
        idempotency_key: str,
    ) -> JobRecord | None: ...
