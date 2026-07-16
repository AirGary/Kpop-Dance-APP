from dataclasses import dataclass
from uuid import UUID, uuid4

import pytest

from api.app.adapters.storage.cloud_job_object_store import CloudJobObjectStore


@dataclass(frozen=True)
class LinkedUpload:
    id: UUID


class FakeResultStore:
    def __init__(self) -> None:
        self.deleted: list[tuple[str, UUID]] = []

    async def delete_job_objects(self, owner_id: str, job_id: UUID) -> None:
        self.deleted.append((owner_id, job_id))


class FakeUploadRepository:
    def __init__(self, upload: LinkedUpload | None) -> None:
        self.upload = upload
        self.deleted: list[UUID] = []

    async def find_completed(self, owner_id: str, job_id: UUID):
        return self.upload

    async def delete(self, upload_id: UUID) -> None:
        self.deleted.append(upload_id)


class FakeSourceStore:
    def __init__(self) -> None:
        self.deleted: list[tuple[str, UUID]] = []

    async def delete(self, owner_id: str, upload_id: UUID) -> None:
        self.deleted.append((owner_id, upload_id))


@pytest.mark.asyncio
async def test_cloud_job_cleanup_deletes_results_linked_source_and_session() -> None:
    owner_id = "firebase-user"
    job_id = uuid4()
    upload = LinkedUpload(uuid4())
    results = FakeResultStore()
    uploads = FakeUploadRepository(upload)
    sources = FakeSourceStore()
    store = CloudJobObjectStore(results, uploads, sources)

    await store.delete_job_objects(owner_id, job_id)

    assert results.deleted == [(owner_id, job_id)]
    assert sources.deleted == [(owner_id, upload.id)]
    assert uploads.deleted == [upload.id]


@pytest.mark.asyncio
async def test_cloud_job_cleanup_allows_jobs_without_linked_upload() -> None:
    owner_id = "firebase-user"
    job_id = uuid4()
    results = FakeResultStore()
    uploads = FakeUploadRepository(None)
    sources = FakeSourceStore()
    store = CloudJobObjectStore(results, uploads, sources)

    await store.delete_job_objects(owner_id, job_id)

    assert results.deleted == [(owner_id, job_id)]
    assert sources.deleted == []
    assert uploads.deleted == []
