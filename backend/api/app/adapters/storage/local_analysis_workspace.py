import asyncio
from contextlib import contextmanager
import fcntl
import os
import re
import shutil
import tempfile
from collections.abc import Iterator
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

    async def promote_upload(
        self,
        owner_id: str,
        job_id: UUID,
        upload_id: UUID,
    ) -> Path:
        source = self._upload_path(owner_id, upload_id)
        destination = self._job_directory(owner_id, job_id) / "source.mp4"
        return await asyncio.to_thread(self._promote, source, destination)

    def _promote(self, source: Path, destination: Path) -> Path:
        source = source.resolve(strict=True)
        destination.parent.mkdir(parents=True, exist_ok=True)
        with self._publication_lock(destination):
            if destination.exists():
                return destination
            try:
                os.link(source, destination)
            except FileExistsError:
                return destination
            except OSError:
                if destination.exists():
                    return destination
                return self._copy_and_publish(source, destination)
            self._fsync_directory(destination.parent)
            return destination

    @staticmethod
    def _copy_and_publish(source: Path, destination: Path) -> Path:
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{destination.name}.",
            suffix=".tmp",
            dir=destination.parent,
        )
        temporary = Path(temporary_name)
        try:
            with source.open("rb") as input_handle, os.fdopen(descriptor, "wb") as output_handle:
                shutil.copyfileobj(input_handle, output_handle)
                output_handle.flush()
                os.fsync(output_handle.fileno())
            os.replace(temporary, destination)
            LocalAnalysisWorkspace._fsync_directory(destination.parent)
            return destination
        finally:
            temporary.unlink(missing_ok=True)

    @staticmethod
    @contextmanager
    def _publication_lock(destination: Path) -> Iterator[None]:
        lock_path = destination.parent / f".{destination.name}.lock"
        with lock_path.open("a+b") as handle:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)

    @staticmethod
    def _fsync_directory(directory: Path) -> None:
        descriptor = os.open(directory, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)

    def _upload_path(self, owner_id: str, upload_id: UUID) -> Path:
        if not _SAFE_OWNER_ID.fullmatch(owner_id):
            raise UnsafeAnalysisWorkspacePathError(
                "Owner ID is not a safe path component."
            )
        source = (
            self._root / owner_id / "uploads" / str(upload_id) / "source.mp4"
        ).resolve(strict=False)
        if not source.is_relative_to(self._root):
            raise UnsafeAnalysisWorkspacePathError(
                "Upload source is outside the storage root."
            )
        return source

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
