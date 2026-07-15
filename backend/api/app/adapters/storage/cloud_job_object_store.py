from uuid import UUID

from api.app.ports.direct_upload_object_store import DirectUploadObjectStore
from api.app.ports.object_store import ObjectStore
from api.app.ports.upload_repository import UploadRepository


class CloudJobObjectStore:
    def __init__(
        self,
        results: ObjectStore,
        uploads: UploadRepository,
        sources: DirectUploadObjectStore,
    ) -> None:
        self._results = results
        self._uploads = uploads
        self._sources = sources

    async def delete_job_objects(self, owner_id: str, job_id: UUID) -> None:
        await self._results.delete_job_objects(owner_id, job_id)
        upload = await self._uploads.find_completed(owner_id, job_id)
        if upload is None:
            return
        await self._sources.delete(owner_id, upload.id)
        await self._uploads.delete(upload.id)
