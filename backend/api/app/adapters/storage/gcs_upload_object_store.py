import asyncio
import hashlib
from collections.abc import Awaitable, Callable
from typing import Any, Protocol
from uuid import UUID

from google.api_core.exceptions import NotFound

from api.app.schemas.uploads import CreateUploadRequest


class _Bucket(Protocol):
    def blob(self, name: str): ...


class GCSUploadObjectStore:
    def __init__(
        self,
        bucket: _Bucket,
        *,
        request: Callable[[str, str], Awaitable[Any]] | None = None,
    ) -> None:
        self._bucket = bucket
        self._request = request or self._send_request

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

    async def cancel_resumable_session(self, upload_url: str) -> None:
        response = await self._request("DELETE", upload_url)
        if response.status_code in {204, 400, 404, 410, 499}:
            return
        raise OSError("Cloud Storage did not cancel the resumable upload session.")

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

    @staticmethod
    async def _send_request(method: str, url: str):
        import httpx

        try:
            async with httpx.AsyncClient(timeout=15, follow_redirects=False) as client:
                return await client.request(
                    method,
                    url,
                    headers={"Content-Length": "0"},
                )
        except httpx.HTTPError as error:
            raise OSError("Cloud Storage session cancellation failed.") from error
