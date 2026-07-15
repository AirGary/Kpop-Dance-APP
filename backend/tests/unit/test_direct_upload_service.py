import hashlib
import asyncio
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

    async def create_resumable_session(self, owner_id, upload_id, request) -> str:
        await asyncio.sleep(0)
        self.created.append((owner_id, upload_id))
        return f"https://storage.example/{upload_id}?secret=session-{len(self.created)}"

    async def size(self, owner_id, upload_id) -> int:
        return len(self.content)

    async def delete(self, owner_id, upload_id) -> None:
        return None


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
