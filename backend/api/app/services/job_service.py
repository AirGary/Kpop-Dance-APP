from datetime import datetime, timezone
from hashlib import sha256
import json
from uuid import UUID, uuid4

from api.app.ports.job_repository import (
    IdempotencyConflictError,
    JobNotFoundError,
    JobRecord,
    JobRepository,
)
from api.app.schemas.errors import APIError
from api.app.schemas.jobs import CreateJobRequest, JobResponse


class JobService:
    def __init__(self, repository: JobRepository) -> None:
        self._repository = repository

    async def create_job(
        self,
        owner_id: str,
        idempotency_key: str,
        request: CreateJobRequest,
    ) -> tuple[JobResponse, bool]:
        now = datetime.now(timezone.utc)
        response = JobResponse(
            id=uuid4(),
            project_id=request.project_id,
            created_at=now,
            updated_at=now,
        )
        record = JobRecord(
            owner_id=owner_id,
            idempotency_key=idempotency_key,
            request_hash=self._request_hash(request),
            response=response,
        )

        try:
            stored, created = await self._repository.create(record)
        except IdempotencyConflictError as error:
            raise APIError(
                409,
                "idempotency_conflict",
                "Idempotency key was already used for a different request.",
            ) from error
        return stored.response, created

    async def get_job(self, owner_id: str, job_id: UUID) -> JobResponse:
        try:
            record = await self._repository.get_for_owner(job_id, owner_id)
        except JobNotFoundError as error:
            raise APIError(404, "job_not_found", "Job was not found.") from error
        return record.response

    @staticmethod
    def _request_hash(request: CreateJobRequest) -> str:
        canonical = json.dumps(
            request.model_dump(mode="json", by_alias=True),
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
        return sha256(canonical).hexdigest()
