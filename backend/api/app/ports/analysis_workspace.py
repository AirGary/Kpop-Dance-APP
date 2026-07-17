from pathlib import Path
from typing import Protocol
from uuid import UUID


class UnsafeAnalysisWorkspacePathError(ValueError):
    pass


class AnalysisWorkspace(Protocol):
    def analysis_directory(self, owner_id: str, job_id: UUID) -> Path: ...

    def proxy_path(self, owner_id: str, job_id: UUID) -> Path: ...

    def checkpoints_directory(self, owner_id: str, job_id: UUID) -> Path: ...

    def result_path(self, owner_id: str, job_id: UUID) -> Path: ...

    async def promote_upload(
        self,
        owner_id: str,
        job_id: UUID,
        upload_id: UUID,
    ) -> Path: ...
