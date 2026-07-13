import asyncio
import hashlib
import re
from collections.abc import AsyncIterator
from pathlib import Path
from uuid import UUID

from api.app.ports.upload_object_store import (
    UnsafeUploadPathError,
    UploadObjectOffsetError,
)


_SAFE_OWNER_ID = re.compile(r"^[A-Za-z0-9_-]{1,128}$")
_HASH_BUFFER_SIZE = 1024 * 1024


class LocalUploadObjectStore:
    def __init__(self, root: Path) -> None:
        self._root = root.resolve()

    def _object_path(self, owner_id: str, upload_id: UUID) -> Path:
        if not _SAFE_OWNER_ID.fullmatch(owner_id):
            raise UnsafeUploadPathError

        path = self._root / owner_id / "uploads" / str(upload_id) / "source.mp4"
        resolved = path.resolve()
        if not resolved.is_relative_to(self._root):
            raise UnsafeUploadPathError
        return resolved

    async def size(self, owner_id: str, upload_id: UUID) -> int:
        path = self._object_path(owner_id, upload_id)

        def file_size() -> int:
            try:
                return path.stat().st_size
            except FileNotFoundError:
                return 0

        return await asyncio.to_thread(file_size)

    async def append(
        self,
        owner_id: str,
        upload_id: UUID,
        offset: int,
        chunks: AsyncIterator[bytes],
    ) -> int:
        path = self._object_path(owner_id, upload_id)
        await asyncio.to_thread(path.parent.mkdir, parents=True, exist_ok=True)
        actual_offset = await self.size(owner_id, upload_id)
        if actual_offset != offset:
            raise UploadObjectOffsetError(actual_offset)

        mode = "r+b" if path.exists() else "wb"
        handle = await asyncio.to_thread(open, path, mode, buffering=0)
        try:
            await asyncio.to_thread(handle.seek, offset)
            written = offset
            async for chunk in chunks:
                if not chunk:
                    continue
                count = await asyncio.to_thread(handle.write, chunk)
                if count != len(chunk):
                    raise OSError("Upload object write was incomplete.")
                written += count
            return written
        finally:
            await asyncio.to_thread(handle.close)

    async def matches(
        self,
        owner_id: str,
        upload_id: UUID,
        offset: int,
        chunks: AsyncIterator[bytes],
    ) -> bool:
        path = self._object_path(owner_id, upload_id)
        if not path.exists():
            return False

        handle = await asyncio.to_thread(open, path, "rb", buffering=0)
        try:
            await asyncio.to_thread(handle.seek, offset)
            async for chunk in chunks:
                if not chunk:
                    continue
                stored = await asyncio.to_thread(handle.read, len(chunk))
                if stored != chunk:
                    return False
            return True
        finally:
            await asyncio.to_thread(handle.close)

    async def sha256(self, owner_id: str, upload_id: UUID) -> str:
        path = self._object_path(owner_id, upload_id)

        def digest_file() -> str:
            digest = hashlib.sha256()
            with path.open("rb") as handle:
                while chunk := handle.read(_HASH_BUFFER_SIZE):
                    digest.update(chunk)
            return digest.hexdigest()

        return await asyncio.to_thread(digest_file)

    async def delete(self, owner_id: str, upload_id: UUID) -> None:
        path = self._object_path(owner_id, upload_id)

        def remove_object() -> None:
            try:
                path.unlink()
            except FileNotFoundError:
                return
            try:
                path.parent.rmdir()
                path.parent.parent.rmdir()
            except OSError:
                pass

        await asyncio.to_thread(remove_object)
