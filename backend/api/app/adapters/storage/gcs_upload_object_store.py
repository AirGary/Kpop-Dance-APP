import asyncio
import hashlib
from typing import Protocol
from uuid import UUID

from google.api_core.exceptions import NotFound

from api.app.schemas.uploads import CreateUploadRequest


class _Bucket(Protocol):
    def blob(self, name: str): ...


class GCSUploadObjectStore:
    def __init__(self, bucket: _Bucket) -> None:
        self._bucket = bucket

    @classmethod
    def from_bucket_name(cls, bucket_name: str) -> "GCSUploadObjectStore":
        from google.cloud import storage

        return cls(storage.Client().bucket(bucket_name))

    async def create_resumable_session(
        self,
        owner_id: str,
        upload_id: UUID,
        request: CreateUploadRequest,
    ) -> str:
        blob = self._blob(owner_id, upload_id)
        blob.metadata = {"expectedSha256": request.sha256}
        return await asyncio.to_thread(
            blob.create_resumable_upload_session,
            content_type=request.mime_type,
            size=request.byte_count,
            checksum="crc32c",
            if_generation_match=0,
        )

    async def size(self, owner_id: str, upload_id: UUID) -> int:
        blob = self._blob(owner_id, upload_id)

        def read_size() -> int:
            try:
                blob.reload()
            except NotFound:
                return 0
            return int(blob.size or 0)

        return await asyncio.to_thread(read_size)

    async def delete(self, owner_id: str, upload_id: UUID) -> None:
        blob = self._blob(owner_id, upload_id)

        def remove_object() -> None:
            try:
                blob.delete()
            except NotFound:
                return

        await asyncio.to_thread(remove_object)

    def _blob(self, owner_id: str, upload_id: UUID):
        owner_hash = hashlib.sha256(owner_id.encode()).hexdigest()
        return self._bucket.blob(
            f"sources/{owner_hash}/uploads/{upload_id}/source.mp4"
        )
