import asyncio
from pathlib import Path
from uuid import uuid4

from api.app.adapters.analysis.local_analysis_runner import LocalAnalysisRunner


def test_runner_keeps_virtualenv_entrypoint_symlink(tmp_path):
    entrypoint = tmp_path / "venv" / "bin" / "python"
    entrypoint.parent.mkdir(parents=True)
    entrypoint.symlink_to("python3.11")

    runner = LocalAnalysisRunner(
        tmp_path,
        tmp_path / "worker",
        tmp_path / "models",
        entrypoint,
    )

    assert runner._python_path == entrypoint.absolute()


def test_runner_passes_dense_candidate_and_sparse_target_strides(tmp_path, monkeypatch):
    entrypoint = tmp_path / "venv" / "bin" / "python"
    entrypoint.parent.mkdir(parents=True)
    entrypoint.symlink_to("python3.11")
    runner = LocalAnalysisRunner(
        tmp_path,
        tmp_path / "worker",
        tmp_path / "models",
        entrypoint,
        frame_stride=30,
        candidate_frame_stride=6,
    )
    commands: list[tuple[str, ...]] = []

    class Process:
        returncode = 0

        async def communicate(self):
            return b'{"candidates": []}', b""

    async def create_process(*command, **_kwargs):
        commands.append(command)
        return Process()

    monkeypatch.setattr(asyncio, "create_subprocess_exec", create_process)

    asyncio.run(runner._run("detect", "owner", uuid4()))
    asyncio.run(runner._run("target", "owner", uuid4(), "candidate-1"))

    assert all("--frame-stride" in command for command in commands)
    assert all("--candidate-frame-stride" in command for command in commands)
    assert all(command[command.index("--frame-stride") + 1] == "30" for command in commands)
    assert all(command[command.index("--candidate-frame-stride") + 1] == "6" for command in commands)
