from pathlib import Path
import re
import shutil
from uuid import UUID

from api.app.ports.object_store import UnsafeObjectPathError


_SAFE_OWNER_ID = re.compile(r"^[A-Za-z0-9_-]{1,68}$")


class LocalObjectStore:
    def __init__(self, root: Path) -> None:
        self._root = root.resolve()

    async def delete_job_objects(self, owner_id: str, job_id: UUID) -> None:
        if not _SAFE_OWNER_ID.fullmatch(owner_id):
            raise UnsafeObjectPathError("Owner ID is not a safe path component.")

        target = (self._root / owner_id / str(job_id)).resolve(strict=False)
        if not target.is_relative_to(self._root) or target == self._root:
            raise UnsafeObjectPathError("Object path is outside the storage root.")

        if target.exists():
            shutil.rmtree(target)
