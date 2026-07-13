from collections.abc import AsyncIterator
from typing import Protocol
from uuid import UUID


class UnsafeUploadPathError(Exception):
    pass


class UploadObjectOffsetError(Exception):
    def __init__(self, actual_offset: int) -> None:
        super().__init__(f"Upload object offset is {actual_offset}.")
        self.actual_offset = actual_offset


class UploadObjectStore(Protocol):
    async def size(self, owner_id: str, upload_id: UUID) -> int: ...

    async def append(
        self,
        owner_id: str,
        upload_id: UUID,
        offset: int,
        chunks: AsyncIterator[bytes],
    ) -> int: ...

    async def matches(
        self,
        owner_id: str,
        upload_id: UUID,
        offset: int,
        chunks: AsyncIterator[bytes],
    ) -> bool: ...

    async def sha256(self, owner_id: str, upload_id: UUID) -> str: ...

    async def delete(self, owner_id: str, upload_id: UUID) -> None: ...
