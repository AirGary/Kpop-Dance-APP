import hashlib
from uuid import uuid4

import pytest
from google.api_core.exceptions import NotFound

from api.app.adapters.storage.gcs_upload_object_store import GCSUploadObjectStore
from api.app.schemas.uploads import CreateUploadRequest


class FakeBlob:
    def __init__(self, name: str, content: bytes = b"video") -> None:
        self.name = name
        self.content = content
        self.size = len(content)
        self.metadata: dict[str, str] | None = None
        self.session_arguments: dict[str, object] | None = None
        self.deleted = False

    def create_resumable_upload_session(self, **kwargs) -> str:
        self.session_arguments = kwargs
        return "https://storage.example/upload-session-secret"

    def reload(self) -> None:
        return None

    def delete(self) -> None:
        self.deleted = True


class FakeBucket:
    def __init__(self) -> None:
        self.blobs: dict[str, FakeBlob] = {}

    def blob(self, name: str) -> FakeBlob:
        return self.blobs.setdefault(name, FakeBlob(name))


class DerivedNotFound(NotFound):
    pass


class MissingBlob(FakeBlob):
    def reload(self) -> None:
        raise DerivedNotFound("missing")

    def delete(self) -> None:
        raise DerivedNotFound("missing")


class MissingBucket:
    def blob(self, name: str) -> MissingBlob:
        return MissingBlob(name)


def upload_request() -> CreateUploadRequest:
    return CreateUploadRequest.model_validate(
        {
            "projectId": uuid4(),
            "sourceFingerprint": "sha256:0123456789abcdef",
            "durationSeconds": 90,
            "byteCount": 5,
            "mimeType": "video/mp4",
            "sha256": hashlib.sha256(b"video").hexdigest(),
        }
    )


@pytest.mark.asyncio
async def test_gcs_store_creates_owner_isolated_resumable_session() -> None:
    bucket = FakeBucket()
    store = GCSUploadObjectStore(bucket)
    upload_id = uuid4()

    url = await store.create_resumable_session(
        "firebase-user@example.com",
        upload_id,
        upload_request(),
    )

    assert url == "https://storage.example/upload-session-secret"
    assert len(bucket.blobs) == 1
    blob = next(iter(bucket.blobs.values()))
    assert "firebase-user@example.com" not in blob.name
    assert str(upload_id) in blob.name
    assert blob.session_arguments == {
        "content_type": "video/mp4",
        "size": 5,
        "checksum": "crc32c",
        "if_generation_match": 0,
    }
    assert blob.metadata == {"expectedSha256": upload_request().sha256}


@pytest.mark.asyncio
async def test_gcs_store_reads_size_and_deletes_object() -> None:
    bucket = FakeBucket()
    store = GCSUploadObjectStore(bucket)
    upload_id = uuid4()
    owner_id = "firebase-user"
    await store.create_resumable_session(owner_id, upload_id, upload_request())

    assert await store.size(owner_id, upload_id) == 5

    await store.delete(owner_id, upload_id)
    assert next(iter(bucket.blobs.values())).deleted is True


@pytest.mark.asyncio
async def test_gcs_store_treats_not_found_subclasses_as_missing() -> None:
    store = GCSUploadObjectStore(MissingBucket())
    upload_id = uuid4()

    assert await store.size("firebase-user", upload_id) == 0
    await store.delete("firebase-user", upload_id)
