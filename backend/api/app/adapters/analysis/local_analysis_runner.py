import asyncio
import json
import os
import sys
from pathlib import Path
from uuid import UUID

from api.app.ports.analysis_runner import AnalysisRunner
from api.app.schemas.analysis import AnalysisResultResponse, DancerCandidateResponse


class LocalAnalysisRunner(AnalysisRunner):
    def __init__(self, workspace_root: Path, worker_root: Path, model_root: Path, python_path: Path) -> None:
        self._workspace_root = workspace_root.resolve()
        self._worker_root = worker_root.resolve()
        self._model_root = model_root.resolve()
        # Keep the virtualenv launcher symlink so sys.prefix remains the local AI environment.
        self._python_path = python_path.absolute()
        self._processes: set[asyncio.subprocess.Process] = set()

    async def detect_candidates(self, owner_id: str, job_id: UUID) -> list[DancerCandidateResponse]:
        payload = await self._run("detect", owner_id, job_id)
        return [DancerCandidateResponse.model_validate(item) for item in payload["candidates"]]

    async def analyze_target(self, owner_id: str, job_id: UUID, candidate_id: str) -> AnalysisResultResponse:
        payload = await self._run("target", owner_id, job_id, candidate_id)
        return AnalysisResultResponse.model_validate(payload["result"])

    async def shutdown(self) -> None:
        processes = list(self._processes)
        for process in processes:
            if process.returncode is None:
                process.terminate()
        if processes:
            await asyncio.gather(*(process.wait() for process in processes), return_exceptions=True)

    async def _run(self, operation: str, owner_id: str, job_id: UUID, candidate_id: str | None = None) -> dict:
        workspace = self._workspace_root / owner_id / str(job_id)
        command = [
            str(self._python_path),
            "-m",
            "stage_lab_analysis.worker_cli",
            operation,
            "--workspace",
            str(workspace),
            "--model-root",
            str(self._model_root),
        ]
        if candidate_id is not None:
            command.extend(["--candidate-id", candidate_id])
        environment = os.environ.copy()
        environment["PYTHONPATH"] = str(self._worker_root)
        process = await asyncio.create_subprocess_exec(
            *command,
            cwd=self._worker_root,
            env=environment,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        self._processes.add(process)
        try:
            stdout, stderr = await process.communicate()
        finally:
            self._processes.discard(process)
        if process.returncode != 0:
            diagnostic = stderr[-2048:].decode("utf-8", errors="replace")
            raise RuntimeError(f"local analysis worker failed: {diagnostic}")
        try:
            return json.loads(stdout)
        except json.JSONDecodeError as error:
            raise RuntimeError("local analysis worker returned invalid status") from error
