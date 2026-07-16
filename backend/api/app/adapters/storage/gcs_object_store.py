import asyncio
import hashlib
from typing import Protocol
from uuid import UUID


class _Bucket(Protocol):
    def list_blobs(self, *, prefix: str): ...


class GCSObjectStore:
    def __init__(self, bucket: _Bucket) -> None:
        self._bucket = bucket

    @classmethod
    def from_bucket_name(cls, bucket_name: str) -> "GCSObjectStore":
        from google.cloud import storage

        return cls(storage.Client().bucket(bucket_name))

    async def delete_job_objects(self, owner_id: str, job_id: UUID) -> None:
        owner_hash = hashlib.sha256(owner_id.encode()).hexdigest()
        prefix = f"results/{owner_hash}/jobs/{job_id}/"

        def delete_objects() -> None:
            for blob in self._bucket.list_blobs(prefix=prefix):
                blob.delete()

        await asyncio.to_thread(delete_objects)
