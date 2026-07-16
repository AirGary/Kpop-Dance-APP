from uuid import uuid4

import pytest

from api.app.adapters.storage.gcs_object_store import GCSObjectStore


class FakeBlob:
    def __init__(self, name: str) -> None:
        self.name = name
        self.deleted = False

    def delete(self) -> None:
        self.deleted = True


class FakeBucket:
    def __init__(self) -> None:
        self.prefix: str | None = None
        self.blobs = [FakeBlob("result-a"), FakeBlob("result-b")]

    def list_blobs(self, *, prefix: str):
        self.prefix = prefix
        return self.blobs


@pytest.mark.asyncio
async def test_gcs_result_cleanup_uses_hashed_owner_prefix() -> None:
    bucket = FakeBucket()
    store = GCSObjectStore(bucket)
    job_id = uuid4()

    await store.delete_job_objects("firebase-user@example.com", job_id)

    assert bucket.prefix is not None
    assert "firebase-user@example.com" not in bucket.prefix
    assert str(job_id) in bucket.prefix
    assert all(blob.deleted for blob in bucket.blobs)
