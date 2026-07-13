import hashlib
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest

from api.app.adapters.repositories.in_memory_job_repository import InMemoryJobRepository
from api.app.adapters.repositories.in_memory_upload_repository import (
    InMemoryUploadRepository,
)
from api.app.adapters.storage.local_object_store import LocalObjectStore
from api.app.adapters.storage.local_upload_object_store import LocalUploadObjectStore
from api.app.schemas.uploads import CreateUploadRequest
from api.app.services.job_service import JobService
from api.app.services.upload_service import (
    ChecksumMismatchError,
    UploadIncompleteError,
    UploadNotFoundError,
    UploadOffsetConflictError,
    UploadRangeError,
    UploadService,
)


PROJECT_ID = UUID("5dc6cb17-9df3-4f99-9f32-dd51e69f4430")


async def chunks(*values: bytes) -> AsyncIterator[bytes]:
    for value in values:
        yield value


class MutableClock:
    def __init__(self) -> None:
        self.now = datetime(2026, 7, 13, 12, tzinfo=UTC)

    def __call__(self) -> datetime:
        return self.now


def request_for(content: bytes, **overrides: object) -> CreateUploadRequest:
    data: dict[str, object] = {
        "projectId": PROJECT_ID,
        "sourceFingerprint": "sha256:0123456789abcdef",
        "durationSeconds": 90,
        "byteCount": len(content),
        "mimeType": "video/mp4",
        "sha256": hashlib.sha256(content).hexdigest(),
    }
    data.update(overrides)
    return CreateUploadRequest.model_validate(data)


@pytest.fixture
def service_parts(tmp_path):
    upload_repository = InMemoryUploadRepository()
    upload_objects = LocalUploadObjectStore(tmp_path / "uploads")
    jobs = JobService(
        InMemoryJobRepository(),
        LocalObjectStore(tmp_path / "jobs"),
    )
    clock = MutableClock()
    service = UploadService(upload_repository, upload_objects, jobs, clock=clock)
    return service, upload_repository, upload_objects, clock


@pytest.mark.anyio
async def test_create_replay_returns_same_upload_with_rotated_token(service_parts) -> None:
    service, _, _, _ = service_parts
    request = request_for(b"abc")

    first = await service.create_session("dev-user-a", "create-key", request)
    replay = await service.create_session("dev-user-a", "create-key", request)

    assert first.session.id == replay.session.id
    assert first.created is True
    assert replay.created is False
    assert first.token != replay.token
    with pytest.raises(UploadNotFoundError):
        await service.head(first.session.id, first.token)
    assert (await service.head(replay.session.id, replay.token)).offset == 0


@pytest.mark.anyio
async def test_create_rejects_changed_idempotent_request(service_parts) -> None:
    service, _, _, _ = service_parts
    await service.create_session("dev-user-a", "key", request_for(b"abc"))

    with pytest.raises(UploadRangeError) as error:
        await service.create_session("dev-user-a", "key", request_for(b"abcd"))

    assert error.value.code == "idempotency_conflict"


@pytest.mark.anyio
async def test_head_hides_unknown_invalid_and_expired_tokens(service_parts) -> None:
    service, _, _, clock = service_parts
    created = await service.create_session("dev-user-a", "key", request_for(b"abc"))

    with pytest.raises(UploadNotFoundError):
        await service.head(created.session.id, "wrong-token")

    clock.now += timedelta(hours=24, seconds=1)
    with pytest.raises(UploadNotFoundError):
        await service.head(created.session.id, created.token)


@pytest.mark.anyio
async def test_append_requires_order_and_exact_body_length(service_parts) -> None:
    service, _, objects, _ = service_parts
    created = await service.create_session("dev-user-a", "key", request_for(b"abcdef"))

    with pytest.raises(UploadOffsetConflictError) as offset_error:
        await service.append_chunk(created.session.id, created.token, 3, 5, 6, chunks(b"def"))
    assert offset_error.value.expected_offset == 0

    with pytest.raises(UploadRangeError):
        await service.append_chunk(created.session.id, created.token, 0, 2, 6, chunks(b"ab"))
    assert await objects.size("dev-user-a", created.session.id) == 0

    partial = await service.append_chunk(
        created.session.id, created.token, 0, 2, 6, chunks(b"a", b"bc")
    )
    final = await service.append_chunk(
        created.session.id, created.token, 3, 5, 6, chunks(b"def")
    )

    assert partial.offset == 3
    assert partial.complete is False
    assert final.offset == 6
    assert final.complete is True


@pytest.mark.anyio
async def test_immediately_previous_matching_chunk_is_idempotent(service_parts) -> None:
    service, _, _, _ = service_parts
    created = await service.create_session("dev-user-a", "key", request_for(b"abcdef"))
    await service.append_chunk(created.session.id, created.token, 0, 2, 6, chunks(b"abc"))

    replay = await service.append_chunk(
        created.session.id, created.token, 0, 2, 6, chunks(b"abc")
    )

    assert replay.offset == 3
    with pytest.raises(UploadOffsetConflictError):
        await service.append_chunk(
            created.session.id, created.token, 0, 2, 6, chunks(b"abd")
        )


@pytest.mark.anyio
async def test_complete_rejects_incomplete_upload(service_parts) -> None:
    service, _, _, _ = service_parts
    created = await service.create_session("dev-user-a", "key", request_for(b"abcdef"))
    await service.append_chunk(created.session.id, created.token, 0, 2, 6, chunks(b"abc"))

    with pytest.raises(UploadIncompleteError):
        await service.complete("dev-user-a", created.session.id, "complete-key")


@pytest.mark.anyio
async def test_checksum_mismatch_deletes_invalid_object(service_parts) -> None:
    service, _, objects, _ = service_parts
    request = request_for(b"abc", sha256="0" * 64)
    created = await service.create_session("dev-user-a", "key", request)
    await service.append_chunk(created.session.id, created.token, 0, 2, 3, chunks(b"abc"))

    with pytest.raises(ChecksumMismatchError):
        await service.complete("dev-user-a", created.session.id, "complete-key")

    assert await objects.size("dev-user-a", created.session.id) == 0


@pytest.mark.anyio
async def test_complete_creates_exactly_one_job_and_hides_foreign_owner(service_parts) -> None:
    service, _, _, _ = service_parts
    created = await service.create_session("dev-user-a", "key", request_for(b"abc"))
    await service.append_chunk(created.session.id, created.token, 0, 2, 3, chunks(b"abc"))

    with pytest.raises(UploadNotFoundError):
        await service.complete("dev-user-b", created.session.id, "complete-key")

    first = await service.complete("dev-user-a", created.session.id, "complete-key")
    replay = await service.complete("dev-user-a", created.session.id, "another-key")

    assert first.job.id == replay.job.id
    assert first.created is True
    assert replay.created is False


@pytest.mark.anyio
async def test_cleanup_removes_expired_session_and_object(service_parts) -> None:
    service, repository, objects, clock = service_parts
    created = await service.create_session("dev-user-a", "key", request_for(b"abc"))
    await service.append_chunk(created.session.id, created.token, 0, 2, 3, chunks(b"abc"))
    clock.now += timedelta(hours=24, seconds=1)

    removed = await service.cleanup_expired()

    assert removed == 1
    assert await repository.get(created.session.id) is None
    assert await objects.size("dev-user-a", created.session.id) == 0
