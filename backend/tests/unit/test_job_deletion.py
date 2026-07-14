import pytest

from api.app.adapters.repositories.in_memory_job_repository import (
    InMemoryJobRepository,
)
from api.app.schemas.errors import APIError
from api.app.schemas.jobs import CreateJobRequest
from api.app.services.job_service import JobService
from tests.factories import valid_job_data


class RecordingObjectStore:
    def __init__(self, error: Exception | None = None) -> None:
        self.error = error
        self.deleted: list[tuple[str, object]] = []

    async def delete_job_objects(self, owner_id, job_id) -> None:
        if self.error:
            raise self.error
        self.deleted.append((owner_id, job_id))


def request() -> CreateJobRequest:
    return CreateJobRequest.model_validate(valid_job_data())


@pytest.mark.asyncio
async def test_storage_failure_preserves_job_record():
    repository = InMemoryJobRepository()
    store = RecordingObjectStore(OSError("disk unavailable"))
    service = JobService(repository, store)
    job, _ = await service.create_job("dev-user-a", "key", request())

    with pytest.raises(APIError) as captured:
        await service.delete_job("dev-user-a", job.id)

    assert captured.value.status_code == 503
    assert captured.value.code == "storage_unavailable"
    assert await service.get_job("dev-user-a", job.id) == job


@pytest.mark.asyncio
async def test_successful_cleanup_removes_job_record():
    repository = InMemoryJobRepository()
    store = RecordingObjectStore()
    service = JobService(repository, store)
    job, _ = await service.create_job("dev-user-a", "key", request())

    await service.delete_job("dev-user-a", job.id)

    assert store.deleted == [("dev-user-a", job.id)]
    with pytest.raises(APIError) as captured:
        await service.get_job("dev-user-a", job.id)
    assert captured.value.code == "job_not_found"
