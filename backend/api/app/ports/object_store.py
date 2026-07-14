from typing import Protocol
from uuid import UUID


class UnsafeObjectPathError(ValueError):
    pass


class ObjectStore(Protocol):
    async def delete_job_objects(self, owner_id: str, job_id: UUID) -> None: ...
