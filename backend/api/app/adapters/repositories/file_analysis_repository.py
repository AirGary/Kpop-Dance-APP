import asyncio
import json
import os
import re
import tempfile
from pathlib import Path
from uuid import UUID

from api.app.ports.analysis_repository import (
    AnalysisNotFoundError,
    UnsafeAnalysisPathError,
)
from api.app.schemas.analysis import AnalysisResultResponse, DancerCandidateResponse
from api.app.schemas.jobs import JobResponse


_SAFE_OWNER_ID = re.compile(r"^[A-Za-z0-9_-]{1,128}$")


class FileAnalysisRepository:
    def __init__(self, root: Path) -> None:
        self._root = root.resolve()

    async def load(self, owner_id: str, job_id: UUID) -> JobResponse:
        return await asyncio.to_thread(self._read_state, owner_id, job_id)

    async def list_states(self) -> list[tuple[str, JobResponse]]:
        return await asyncio.to_thread(self._list_states)

    async def update(
        self,
        owner_id: str,
        job_id: UUID,
        response: JobResponse,
    ) -> JobResponse:
        if response.id != job_id:
            raise ValueError("Job response ID must match the workspace job ID.")
        await asyncio.to_thread(
            self._write_json,
            self._analysis_directory(owner_id, job_id) / "analysis-state.json",
            response.model_dump(mode="json", by_alias=True),
        )
        return response

    async def candidates(
        self,
        owner_id: str,
        job_id: UUID,
    ) -> list[DancerCandidateResponse]:
        return await asyncio.to_thread(self._read_candidates, owner_id, job_id)

    async def set_candidates(
        self,
        owner_id: str,
        job_id: UUID,
        candidates: list[DancerCandidateResponse],
    ) -> None:
        await asyncio.to_thread(self._require_state, owner_id, job_id)
        await asyncio.to_thread(
            self._write_json,
            self._analysis_directory(owner_id, job_id) / "candidates.json",
            [candidate.model_dump(mode="json", by_alias=True) for candidate in candidates],
        )

    async def set_target_selection(
        self,
        owner_id: str,
        job_id: UUID,
        candidate_id: str,
        idempotency_key: str,
    ) -> None:
        await asyncio.to_thread(self._require_state, owner_id, job_id)
        await asyncio.to_thread(
            self._write_json,
            self._analysis_directory(owner_id, job_id) / "target-selection.json",
            {"candidateId": candidate_id, "idempotencyKey": idempotency_key},
        )

    async def target_selection(
        self,
        owner_id: str,
        job_id: UUID,
    ) -> tuple[str, str] | None:
        return await asyncio.to_thread(self._read_target_selection, owner_id, job_id)

    async def result(self, owner_id: str, job_id: UUID) -> AnalysisResultResponse:
        return await asyncio.to_thread(self._read_result, owner_id, job_id)

    async def set_result(
        self,
        owner_id: str,
        job_id: UUID,
        result: AnalysisResultResponse,
    ) -> None:
        await asyncio.to_thread(self._require_state, owner_id, job_id)
        await asyncio.to_thread(
            self._write_json,
            self._analysis_directory(owner_id, job_id) / "result-metadata.json",
            result.model_dump(mode="json", by_alias=True),
        )

    def _read_state(self, owner_id: str, job_id: UUID) -> JobResponse:
        return JobResponse.model_validate(self._read_json(self._state_path(owner_id, job_id)))

    def _list_states(self) -> list[tuple[str, JobResponse]]:
        states: list[tuple[str, JobResponse]] = []
        if not self._root.exists():
            return states
        for path in self._root.glob("*/*/analysis/analysis-state.json"):
            owner_id = path.parents[2].name
            try:
                states.append((owner_id, JobResponse.model_validate(json.loads(path.read_text(encoding="utf-8")))))
            except (OSError, ValueError, TypeError):
                continue
        return states

    def _read_candidates(
        self,
        owner_id: str,
        job_id: UUID,
    ) -> list[DancerCandidateResponse]:
        self._require_state(owner_id, job_id)
        path = self._analysis_directory(owner_id, job_id) / "candidates.json"
        try:
            return [DancerCandidateResponse.model_validate(item) for item in self._read_json(path)]
        except AnalysisNotFoundError:
            return []

    def _read_target_selection(self, owner_id: str, job_id: UUID) -> tuple[str, str] | None:
        try:
            value = self._read_json(self._analysis_directory(owner_id, job_id) / "target-selection.json")
        except AnalysisNotFoundError:
            return None
        return str(value["candidateId"]), str(value["idempotencyKey"])

    def _read_result(self, owner_id: str, job_id: UUID) -> AnalysisResultResponse:
        self._require_state(owner_id, job_id)
        return AnalysisResultResponse.model_validate(
            self._read_json(self._analysis_directory(owner_id, job_id) / "result-metadata.json")
        )

    def _require_state(self, owner_id: str, job_id: UUID) -> None:
        self._read_json(self._state_path(owner_id, job_id))

    def _read_json(self, path: Path):
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError as error:
            raise AnalysisNotFoundError from error

    @staticmethod
    def _write_json(path: Path, value: object) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{path.name}.",
            suffix=".tmp",
            dir=path.parent,
        )
        temporary = Path(temporary_name)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                json.dump(value, handle, separators=(",", ":"), sort_keys=True)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, path)
            FileAnalysisRepository._fsync_directory(path.parent)
        except Exception:
            temporary.unlink(missing_ok=True)
            raise

    @staticmethod
    def _fsync_directory(directory: Path) -> None:
        descriptor = os.open(directory, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)

    def _state_path(self, owner_id: str, job_id: UUID) -> Path:
        return self._analysis_directory(owner_id, job_id) / "analysis-state.json"

    def _analysis_directory(self, owner_id: str, job_id: UUID) -> Path:
        if not _SAFE_OWNER_ID.fullmatch(owner_id):
            raise UnsafeAnalysisPathError("Owner ID is not a safe path component.")
        directory = (self._root / owner_id / str(job_id) / "analysis").resolve(
            strict=False
        )
        if not directory.is_relative_to(self._root):
            raise UnsafeAnalysisPathError("Analysis path is outside the storage root.")
        return directory
