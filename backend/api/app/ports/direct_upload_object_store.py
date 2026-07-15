from typing import Protocol
from uuid import UUID

from api.app.schemas.uploads import CreateUploadRequest


class DirectUploadObjectStore(Protocol):
    async def create_resumable_session(
        self,
        owner_id: str,
        upload_id: UUID,
        request: CreateUploadRequest,
    ) -> str: ...

    async def size(self, owner_id: str, upload_id: UUID) -> int: ...

    async def delete(self, owner_id: str, upload_id: UUID) -> None: ...
