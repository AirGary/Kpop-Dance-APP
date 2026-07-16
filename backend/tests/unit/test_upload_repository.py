from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError

from api.app.adapters.repositories.in_memory_upload_repository import (
    InMemoryUploadRepository,
)
from api.app.ports.upload_repository import UploadIdempotencyConflictError, UploadSession
from api.app.schemas.uploads import CreateUploadRequest


PROJECT_ID = UUID("5dc6cb17-9df3-4f99-9f32-dd51e69f4430")


def make_request(**overrides: object) -> CreateUploadRequest:
    data: dict[str, object] = {
        "projectId": PROJECT_ID,
        "sourceFingerprint": "sha256:0123456789abcdef",
        "durationSeconds": 90,
        "byteCount": 6,
        "mimeType": "video/mp4",
        "sha256": "a" * 64,
    }
    data.update(overrides)
    return CreateUploadRequest.model_validate(data)


def make_session(
    *,
    owner_id: str = "owner-a",
    idempotency_key: str = "create-key",
    request_digest: str = "digest-a",
    offset: int = 0,
    expires_at: datetime | None = None,
) -> UploadSession:
    return UploadSession(
        id=uuid4(),
        owner_id=owner_id,
        request=make_request(),
        request_digest=request_digest,
        idempotency_key=idempotency_key,
        token_digest="token-digest",
        offset=offset,
        expires_at=expires_at or datetime.now(UTC) + timedelta(hours=24),
    )


def test_create_upload_accepts_exact_contract() -> None:
    request = make_request()

    assert request.project_id == PROJECT_ID
    assert request.mime_type == "video/mp4"
    assert request.sha256 == "a" * 64


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("sha256", "A" * 64),
        ("mimeType", "video/quicktime"),
        ("durationSeconds", 0),
        ("durationSeconds", 361),
        ("byteCount", 0),
        ("byteCount", 2_147_483_649),
    ],
)
def test_create_upload_rejects_values_outside_contract(field: str, value: object) -> None:
    with pytest.raises(ValidationError):
        make_request(**{field: value})


@pytest.mark.anyio
async def test_repository_replays_matching_idempotency_key() -> None:
    repository = InMemoryUploadRepository()
    original = make_session()

    stored, created = await repository.create(original)
    replay, replay_created = await repository.create(
        make_session(idempotency_key=original.idempotency_key)
    )

    assert created is True
    assert stored == original
    assert replay_created is False
    assert replay == original


@pytest.mark.anyio
async def test_repository_rejects_changed_idempotent_request() -> None:
    repository = InMemoryUploadRepository()
    await repository.create(make_session())

    with pytest.raises(UploadIdempotencyConflictError):
        await repository.create(make_session(request_digest="digest-b"))


@pytest.mark.anyio
async def test_repository_updates_only_expected_offset() -> None:
    repository = InMemoryUploadRepository()
    session = make_session()
    await repository.create(session)

    assert await repository.update_offset(session.id, expected=0, new=5) is True
    assert await repository.update_offset(session.id, expected=0, new=10) is False
    assert (await repository.get(session.id)).offset == 5


@pytest.mark.anyio
async def test_repository_marks_completion_and_lists_expired_sessions() -> None:
    repository = InMemoryUploadRepository()
    expired = make_session(expires_at=datetime.now(UTC) - timedelta(seconds=1))
    active = make_session(idempotency_key="active-key")
    await repository.create(expired)
    await repository.create(active)
    job_id = uuid4()

    await repository.claim_completion(
        active.id,
        "owner-a",
        datetime.now(UTC),
        "claim-a",
    )
    completed = await repository.mark_completed(active.id, job_id, "claim-a")
    found = await repository.expired_before(datetime.now(UTC))

    assert completed is not None
    assert completed.completed_job_id == job_id
    assert found == [expired]


@pytest.mark.anyio
async def test_delete_removes_session_and_idempotency_index() -> None:
    repository = InMemoryUploadRepository()
    session = make_session()
    await repository.create(session)

    await repository.delete(session.id)

    assert await repository.get(session.id) is None
    replacement, created = await repository.create(
        make_session(idempotency_key=session.idempotency_key)
    )
    assert created is True
    assert replacement.id != session.id
