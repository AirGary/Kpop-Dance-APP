import pytest

from api.app.adapters.repositories.in_memory_job_repository import (
    InMemoryJobRepository,
)
from api.app.schemas.errors import APIError
from api.app.schemas.jobs import CreateJobRequest
from api.app.services.job_service import JobService
from tests.factories import valid_job_data


def request(**overrides) -> CreateJobRequest:
    return CreateJobRequest.model_validate(valid_job_data(**overrides))


@pytest.fixture
def service() -> JobService:
    return JobService(InMemoryJobRepository())


@pytest.mark.asyncio
async def test_same_owner_and_key_returns_original_job(service):
    first, first_created = await service.create_job(
        "dev-user-a", "key-1", request()
    )
    second, second_created = await service.create_job(
        "dev-user-a", "key-1", request()
    )

    assert first.id == second.id
    assert first_created is True
    assert second_created is False


@pytest.mark.asyncio
async def test_same_key_with_changed_body_conflicts(service):
    await service.create_job("dev-user-a", "key-1", request())

    with pytest.raises(APIError) as captured:
        await service.create_job(
            "dev-user-a",
            "key-1",
            request(durationSeconds=120),
        )

    assert captured.value.status_code == 409
    assert captured.value.code == "idempotency_conflict"


@pytest.mark.asyncio
async def test_different_owners_can_reuse_an_idempotency_key(service):
    first, _ = await service.create_job("dev-user-a", "shared", request())
    second, _ = await service.create_job("dev-user-b", "shared", request())

    assert first.id != second.id


@pytest.mark.asyncio
async def test_owner_can_fetch_a_job(service):
    created, _ = await service.create_job("dev-user-a", "key", request())

    fetched = await service.get_job("dev-user-a", created.id)

    assert fetched == created


@pytest.mark.asyncio
async def test_foreign_owner_and_unknown_job_share_not_found_error(service):
    created, _ = await service.create_job("dev-user-a", "key", request())

    for job_id in (created.id, created.id.__class__(int=0)):
        with pytest.raises(APIError) as captured:
            await service.get_job("dev-user-b", job_id)
        assert captured.value.status_code == 404
        assert captured.value.code == "job_not_found"
