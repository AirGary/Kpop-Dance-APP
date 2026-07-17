import asyncio
import json
import os
import re
import tempfile
from pathlib import Path
from uuid import UUID

from api.app.ports.job_repository import (
    IdempotencyConflictError,
    JobNotFoundError,
    JobRecord,
    JobStateConflictError,
)
from api.app.schemas.analysis import AnalysisJobState
from api.app.schemas.jobs import JobResponse


_SAFE_OWNER_ID = re.compile(r"^[A-Za-z0-9_-]{1,128}$")


class FileJobRepository:
    """Small durable JobRepository for the local-ai demo environment."""

    def __init__(self, root: Path) -> None:
        self._root = root.resolve()
        self._lock = asyncio.Lock()

    async def create(self, record: JobRecord) -> tuple[JobRecord, bool]:
        async with self._lock:
            path = self._path(record.owner_id, record.response.id)
            existing = self._read_optional(path)
            if existing is not None:
                if existing.idempotency_key != record.idempotency_key or existing.request_hash != record.request_hash:
                    raise IdempotencyConflictError
                return existing, False
            self._write(path, _record_json(record))
            return record, True

    async def get_for_owner(self, job_id: UUID, owner_id: str) -> JobRecord:
        async with self._lock:
            record = self._find(job_id)
            if record is None or record.owner_id != owner_id:
                raise JobNotFoundError
            return record

    async def delete_for_owner(self, job_id: UUID, owner_id: str) -> None:
        async with self._lock:
            record = self._find(job_id)
            if record is None or record.owner_id != owner_id:
                raise JobNotFoundError
            self._path(owner_id, job_id).unlink(missing_ok=True)

    async def update_response(
        self,
        expected_state: AnalysisJobState,
        response,
    ) -> JobRecord:
        async with self._lock:
            record = self._find(response.id)
            if record is None:
                raise JobNotFoundError
            if record.response.state is not expected_state:
                raise JobStateConflictError
            updated = JobRecord(
                owner_id=record.owner_id,
                idempotency_key=record.idempotency_key,
                request_hash=record.request_hash,
                response=response,
            )
            self._write(self._path(record.owner_id, response.id), _record_json(updated))
            return updated

    async def find_by_idempotency_key(self, owner_id: str, idempotency_key: str):
        async with self._lock:
            for path in self._owner_directory(owner_id).glob("*.json"):
                record = self._read_optional(path)
                if record is not None and record.idempotency_key == idempotency_key:
                    return record
            return None

    def _find(self, job_id: UUID) -> JobRecord | None:
        for owner_directory in self._root.iterdir() if self._root.exists() else ():
            if not owner_directory.is_dir() or not _SAFE_OWNER_ID.fullmatch(owner_directory.name):
                continue
            record = self._read_optional(owner_directory / "jobs" / f"{job_id}.json")
            if record is not None:
                return record
        return None

    def _path(self, owner_id: str, job_id: UUID) -> Path:
        if not _SAFE_OWNER_ID.fullmatch(owner_id):
            raise ValueError("Owner ID is not a safe path component.")
        path = (self._root / owner_id / "jobs" / f"{job_id}.json").resolve(strict=False)
        if not path.is_relative_to(self._root):
            raise ValueError("Job path is outside the storage root.")
        return path

    def _owner_directory(self, owner_id: str) -> Path:
        return self._path(owner_id, UUID(int=0)).parent

    @staticmethod
    def _read_optional(path: Path) -> JobRecord | None:
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return None
        return JobRecord(
            owner_id=value["ownerId"],
            idempotency_key=value["idempotencyKey"],
            request_hash=value["requestHash"],
            response=JobResponse.model_validate(value["response"]),
        )

    @staticmethod
    def _write(path: Path, value: dict) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
        temporary = Path(temporary_name)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                json.dump(value, handle, separators=(",", ":"), sort_keys=True)
                handle.flush()
                os.fsync(handle.fileno())
            temporary.replace(path)
        finally:
            temporary.unlink(missing_ok=True)


def _record_json(record: JobRecord) -> dict:
    return {
        "ownerId": record.owner_id,
        "idempotencyKey": record.idempotency_key,
        "requestHash": record.request_hash,
        "response": record.response.model_dump(mode="json", by_alias=True),
    }
