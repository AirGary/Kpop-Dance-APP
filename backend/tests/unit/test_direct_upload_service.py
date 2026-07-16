import hashlib
import asyncio
from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest

from api.app.adapters.repositories.in_memory_job_repository import InMemoryJobRepository
from api.app.adapters.repositories.in_memory_upload_repository import (
    InMemoryUploadRepository,
)
from api.app.adapters.storage.local_object_store import LocalObjectStore
from api.app.schemas.uploads import CreateUploadRequest
from api.app.services.job_service import JobService
from api.app.services.upload_service import UploadService


class FakeDirectUploadStore:
    def __init__(self, content: bytes) -> None:
        self.content = content
        self.created: list[tuple[str, object]] = []
        self.cancelled: list[str] = []

    async def create_resumable_session(self, owner_id, upload_id, request) -> str:
        await asyncio.sleep(0)
        self.created.append((owner_id, upload_id))
        return f"https://storage.example/{upload_id}?secret=session-{len(self.created)}"

    async def size(self, owner_id, upload_id) -> int:
        return len(self.content)

    async def delete(self, owner_id, upload_id) -> None:
        return None

    async def cancel_resumable_session(self, upload_url: str) -> None:
        self.cancelled.append(upload_url)


def request(content: bytes) -> CreateUploadRequest:
    return CreateUploadRequest.model_validate(
        {
            "projectId": UUID("5dc6cb17-9df3-4f99-9f32-dd51e69f4430"),
            "sourceFingerprint": "sha256:0123456789abcdef",
            "durationSeconds": 90,
            "byteCount": len(content),
            "mimeType": "video/mp4",
            "sha256": hashlib.sha256(content).hexdigest(),
        }
    )


@pytest.mark.asyncio
async def test_direct_upload_replay_returns_same_private_session(tmp_path) -> None:
    content = b"video"
    repository = InMemoryUploadRepository()
    direct = FakeDirectUploadStore(content)
    jobs = JobService(InMemoryJobRepository(), LocalObjectStore(tmp_path))
    service = UploadService.direct(repository, direct, jobs)

    first = await service.create_session("owner-a", "key", request(content))
    replay = await service.create_session("owner-a", "key", request(content))

    assert first.created is True
    assert replay.created is False
    assert first.upload_url == replay.upload_url
    assert first.upload_url.startswith("https://storage.example/")
    assert len(direct.created) == 1

    completed = await service.complete("owner-a", first.session.id, "complete")
    assert completed.created is True


@pytest.mark.asyncio
async def test_concurrent_direct_upload_replay_creates_one_session(tmp_path) -> None:
    content = b"video"
    direct = FakeDirectUploadStore(content)
    jobs = JobService(InMemoryJobRepository(), LocalObjectStore(tmp_path))
    service = UploadService.direct(InMemoryUploadRepository(), direct, jobs)

    first, second = await asyncio.gather(
        service.create_session("owner-a", "same-key", request(content)),
        service.create_session("owner-a", "same-key", request(content)),
    )

    assert first.session.id == second.session.id
    assert first.upload_url == second.upload_url
    assert len(direct.created) == 1


@pytest.mark.asyncio
async def test_cross_instance_direct_replay_returns_one_persisted_session(tmp_path) -> None:
    content = b"video"
    repository = InMemoryUploadRepository()
    direct = FakeDirectUploadStore(content)
    job_repository = InMemoryJobRepository()
    first_service = UploadService.direct(
        repository,
        direct,
        JobService(job_repository, LocalObjectStore(tmp_path)),
    )
    second_service = UploadService.direct(
        repository,
        direct,
        JobService(job_repository, LocalObjectStore(tmp_path)),
    )

    first, second = await asyncio.gather(
        first_service.create_session("owner-a", "same-key", request(content)),
        second_service.create_session("owner-a", "same-key", request(content)),
    )

    assert first.session.id == second.session.id
    assert first.upload_url == second.upload_url


@pytest.mark.asyncio
async def test_cross_instance_completion_creates_one_job(tmp_path) -> None:
    content = b"video"
    upload_repository = InMemoryUploadRepository()
    direct = FakeDirectUploadStore(content)
    job_repository = InMemoryJobRepository()
    first_service = UploadService.direct(
        upload_repository,
        direct,
        JobService(job_repository, LocalObjectStore(tmp_path)),
    )
    second_service = UploadService.direct(
        upload_repository,
        direct,
        JobService(job_repository, LocalObjectStore(tmp_path)),
    )
    created = await first_service.create_session(
        "owner-a",
        "same-upload",
        request(content),
    )

    first, second = await asyncio.gather(
        first_service.complete("owner-a", created.session.id, "first-key"),
        second_service.complete("owner-a", created.session.id, "second-key"),
    )

    assert first.job.id == second.job.id
    assert {first.created, second.created} == {True, False}


@pytest.mark.asyncio
async def test_expired_direct_upload_cancels_credential_before_deleting_metadata(
    tmp_path,
) -> None:
    content = b"video"
    now = datetime.now(UTC)
    repository = InMemoryUploadRepository()
    direct = FakeDirectUploadStore(content)
    service = UploadService.direct(
        repository,
        direct,
        JobService(InMemoryJobRepository(), LocalObjectStore(tmp_path)),
        clock=lambda: now,
    )
    created = await service.create_session("owner-a", "key", request(content))
    service._clock = lambda: now + timedelta(hours=25)

    assert await service.cleanup_expired() == 1
    assert direct.cancelled == [created.upload_url]
    assert await repository.get(created.session.id) is None


@pytest.mark.asyncio
async def test_completion_claim_prevents_cross_instance_expiry_cleanup(tmp_path) -> None:
    content = b"video"
    now = datetime.now(UTC)
    repository = InMemoryUploadRepository()
    direct = FakeDirectUploadStore(content)
    jobs = InMemoryJobRepository()
    first = UploadService.direct(
        repository,
        direct,
        JobService(jobs, LocalObjectStore(tmp_path)),
        clock=lambda: now,
    )
    second = UploadService.direct(
        repository,
        direct,
        JobService(jobs, LocalObjectStore(tmp_path)),
        clock=lambda: now + timedelta(hours=24, minutes=1),
    )
    created = await first.create_session("owner-a", "key", request(content))
    claimed = await repository.claim_completion(
        created.session.id,
        "owner-a",
        now + timedelta(hours=23, minutes=59),
        "claim-a",
    )

    assert claimed is not None
    assert await second.cleanup_expired() == 0
    assert direct.cancelled == []


@pytest.mark.asyncio
async def test_abandon_claim_cancels_session_and_allows_idempotent_recreation(
    tmp_path,
) -> None:
    content = b"video"
    repository = InMemoryUploadRepository()
    direct = FakeDirectUploadStore(content)
    service = UploadService.direct(
        repository,
        direct,
        JobService(InMemoryJobRepository(), LocalObjectStore(tmp_path)),
    )
    first = await service.create_session("owner-a", "key", request(content))

    await service.abandon("owner-a", first.session.id)
    second = await service.create_session("owner-a", "key", request(content))

    assert direct.cancelled == [first.upload_url]
    assert second.session.id != first.session.id
    assert second.upload_url != first.upload_url
