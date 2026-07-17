import asyncio
from uuid import UUID

from api.app.ports.job_repository import (
    IdempotencyConflictError,
    JobNotFoundError,
    JobRecord,
    JobStateConflictError,
)
from api.app.schemas.analysis import AnalysisJobState
from api.app.schemas.jobs import JobResponse


class InMemoryJobRepository:
    def __init__(self) -> None:
        self._jobs: dict[UUID, JobRecord] = {}
        self._idempotency: dict[tuple[str, str], UUID] = {}
        self._lock = asyncio.Lock()

    async def create(self, record: JobRecord) -> tuple[JobRecord, bool]:
        key = (record.owner_id, record.idempotency_key)
        async with self._lock:
            existing_id = self._idempotency.get(key)
            if existing_id is not None:
                existing = self._jobs[existing_id]
                if existing.request_hash != record.request_hash:
                    raise IdempotencyConflictError
                return existing, False

            self._jobs[record.response.id] = record
            self._idempotency[key] = record.response.id
            return record, True

    async def get_for_owner(self, job_id: UUID, owner_id: str) -> JobRecord:
        async with self._lock:
            record = self._jobs.get(job_id)
            if record is None or record.owner_id != owner_id:
                raise JobNotFoundError
            return record

    async def delete_for_owner(self, job_id: UUID, owner_id: str) -> None:
        async with self._lock:
            record = self._jobs.get(job_id)
            if record is None or record.owner_id != owner_id:
                raise JobNotFoundError
            del self._jobs[job_id]
            self._idempotency.pop(
                (record.owner_id, record.idempotency_key),
                None,
            )

    async def update_response(
        self,
        expected_state: AnalysisJobState,
        response: JobResponse,
    ) -> JobRecord:
        async with self._lock:
            record = self._jobs.get(response.id)
            if record is None:
                raise JobNotFoundError
            if record.response.state != expected_state:
                raise JobStateConflictError
            updated = JobRecord(
                owner_id=record.owner_id,
                idempotency_key=record.idempotency_key,
                request_hash=record.request_hash,
                response=response,
            )
            self._jobs[response.id] = updated
            return updated

    async def find_by_idempotency_key(
        self,
        owner_id: str,
        idempotency_key: str,
    ) -> JobRecord | None:
        async with self._lock:
            job_id = self._idempotency.get((owner_id, idempotency_key))
            return self._jobs.get(job_id) if job_id is not None else None
