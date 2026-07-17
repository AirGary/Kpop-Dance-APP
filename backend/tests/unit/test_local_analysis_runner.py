from pathlib import Path

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
