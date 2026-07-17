import asyncio
import os
import re
import shutil
from pathlib import Path
from uuid import UUID

from api.app.ports.analysis_workspace import UnsafeAnalysisWorkspacePathError


_SAFE_OWNER_ID = re.compile(r"^[A-Za-z0-9_-]{1,128}$")


class LocalAnalysisWorkspace:
    def __init__(self, root: Path) -> None:
        self._root = root.resolve()

    def analysis_directory(self, owner_id: str, job_id: UUID) -> Path:
        return self._job_directory(owner_id, job_id) / "analysis"

    def proxy_path(self, owner_id: str, job_id: UUID) -> Path:
        return self.analysis_directory(owner_id, job_id) / "proxy.mp4"

    def checkpoints_directory(self, owner_id: str, job_id: UUID) -> Path:
        return self.analysis_directory(owner_id, job_id) / "checkpoints"

    def result_path(self, owner_id: str, job_id: UUID) -> Path:
        return self.analysis_directory(owner_id, job_id) / "result.json"

    async def promote_upload(self, owner_id: str, job_id: UUID, source: Path) -> Path:
        destination = self._job_directory(owner_id, job_id) / "source.mp4"
        return await asyncio.to_thread(self._promote, source, destination)

    @staticmethod
    def _promote(source: Path, destination: Path) -> Path:
        source = source.resolve(strict=True)
        destination.parent.mkdir(parents=True, exist_ok=True)
        if destination.exists():
            return destination
        try:
            os.link(source, destination)
        except OSError:
            shutil.copyfile(source, destination)
        return destination

    def _job_directory(self, owner_id: str, job_id: UUID) -> Path:
        if not _SAFE_OWNER_ID.fullmatch(owner_id):
            raise UnsafeAnalysisWorkspacePathError(
                "Owner ID is not a safe path component."
            )
        directory = (self._root / owner_id / str(job_id)).resolve(strict=False)
        if not directory.is_relative_to(self._root):
            raise UnsafeAnalysisWorkspacePathError(
                "Analysis workspace is outside the storage root."
            )
        return directory
