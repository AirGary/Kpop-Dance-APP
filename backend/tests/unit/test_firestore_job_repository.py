from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest

from api.app.adapters.repositories.firestore_job_repository import (
    FirestoreJobRepository,
)
from api.app.ports.job_repository import (
    IdempotencyConflictError,
    JobNotFoundError,
    JobRecord,
    JobStateConflictError,
)
from api.app.schemas.analysis import AnalysisJobState
from api.app.schemas.jobs import JobResponse
from tests.fake_firestore import FakeFirestoreGateway


def make_record(
    *,
    owner_id: str = "owner-a",
    idempotency_key: str = "job-key",
    request_hash: str = "request-a",
) -> JobRecord:
    now = datetime.now(UTC)
    return JobRecord(
        owner_id=owner_id,
        idempotency_key=idempotency_key,
        request_hash=request_hash,
        response=JobResponse(
            id=uuid4(),
            projectId=UUID("5dc6cb17-9df3-4f99-9f32-dd51e69f4430"),
            createdAt=now,
            updatedAt=now,
        ),
    )


@pytest.mark.asyncio
async def test_firestore_job_replays_matching_idempotency_key() -> None:
    repository = FirestoreJobRepository(FakeFirestoreGateway())
    original = make_record()

    stored, created = await repository.create(original)
    replay, replay_created = await repository.create(make_record())

    assert stored == original
    assert created is True
    assert replay == original
    assert replay_created is False


@pytest.mark.asyncio
async def test_firestore_job_rejects_changed_idempotent_request() -> None:
    repository = FirestoreJobRepository(FakeFirestoreGateway())
    await repository.create(make_record())

    with pytest.raises(IdempotencyConflictError):
        await repository.create(make_record(request_hash="request-b"))


@pytest.mark.asyncio
async def test_firestore_job_hides_foreign_owner_and_deletes_index() -> None:
    repository = FirestoreJobRepository(FakeFirestoreGateway())
    original = make_record()
    await repository.create(original)

    with pytest.raises(JobNotFoundError):
        await repository.get_for_owner(original.response.id, "owner-b")

    await repository.delete_for_owner(original.response.id, original.owner_id)
    assert (
        await repository.find_by_idempotency_key(
            original.owner_id,
            original.idempotency_key,
        )
        is None
    )


@pytest.mark.asyncio
async def test_firestore_job_updates_response_only_when_expected_state_matches() -> None:
    repository = FirestoreJobRepository(FakeFirestoreGateway())
    original = make_record()
    await repository.create(original)
    updated = original.response.model_copy(
        update={"state": AnalysisJobState.UPLOADED}
    )

    stored = await repository.update_response(AnalysisJobState.DRAFT, updated)

    assert stored.response == updated
    with pytest.raises(JobStateConflictError):
        await repository.update_response(AnalysisJobState.DRAFT, updated)
