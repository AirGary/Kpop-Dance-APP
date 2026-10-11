from __future__ import annotations

import json
import math
from pathlib import Path
from types import SimpleNamespace

import pytest

from stage_lab_analysis.detection import Detection, NormalizedBox
from stage_lab_analysis.fancam_demo import proposal_cli
from stage_lab_analysis.fancam_demo.proposal import ProposalScene, ProposalSet
from stage_lab_analysis.fancam_demo.proposal_cli import run_native_proposal
from stage_lab_analysis.reid import PersonEmbedding


def _embedding() -> PersonEmbedding:
    return PersonEmbedding((1.0, 0.0), quality=1.0)


class _Detector:
    def detect(self, frame: object) -> tuple[Detection, ...]:
        return (
            Detection(
                time_seconds=0.0,
                box=NormalizedBox(0.1, 0.1, 0.2, 0.2),
                confidence=1.0,
            ),
        )


class _Embedder:
    def embed(self, frame: object, box: NormalizedBox) -> PersonEmbedding:
        return _embedding()


def _reader(source: Path, timestamp_seconds: float) -> object:
    return object()


def test_native_proposal_writes_only_allowed_local_schema(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    destination = tmp_path / "docs" / "fancam-demo-ground-truth.proposed.local.json"
    destination.parent.mkdir()
    monkeypatch.setattr(proposal_cli, "_destination", lambda: destination)

    proposal = run_native_proposal(
        tmp_path / "private.mp4",
        tuple(float(index) for index in range(30)),
        _Detector(),
        _Embedder(),
        destination,
        reader=_reader,
    )

    payload = json.loads(destination.read_text(encoding="utf-8"))
    assert set(payload) == {"schemaVersion", "scenes"}
    assert len(proposal.scenes) == 30


def test_native_proposal_rejects_noncanonical_destination(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="canonical ignored proposal path"):
        run_native_proposal(
            tmp_path / "private.mp4",
            tuple(float(index) for index in range(30)),
            _Detector(),
            _Embedder(),
            tmp_path / "proposal.json",
            reader=_reader,
        )


def test_native_proposal_rejects_alternate_same_basename_destination(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    canonical = tmp_path / "docs" / "fancam-demo-ground-truth.proposed.local.json"
    canonical.parent.mkdir()
    alternate = tmp_path / "alternate" / "fancam-demo-ground-truth.proposed.local.json"
    alternate.parent.mkdir()
    monkeypatch.setattr(proposal_cli, "_destination", lambda: canonical)

    with pytest.raises(ValueError, match="canonical ignored proposal path"):
        run_native_proposal(
            tmp_path / "private.mp4",
            tuple(float(index) for index in range(30)),
            _Detector(),
            _Embedder(),
            alternate,
            reader=_reader,
        )


def test_native_proposal_removes_temporary_file_after_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    destination = tmp_path / "docs" / "fancam-demo-ground-truth.proposed.local.json"
    destination.parent.mkdir()
    monkeypatch.setattr(proposal_cli, "_destination", lambda: destination)

    def failing_reader(source: Path, timestamp_seconds: float) -> object:
        if math.isclose(timestamp_seconds, 1.0):
            raise RuntimeError("read failed")
        return object()

    with pytest.raises(RuntimeError, match="read failed"):
        run_native_proposal(
            tmp_path / "private.mp4",
            tuple(float(index) for index in range(30)),
            _Detector(),
            _Embedder(),
            destination,
            reader=failing_reader,
        )

    assert not destination.with_suffix(".tmp").exists()


def test_cli_prints_only_redacted_aggregate(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    proposal = ProposalSet(
        tuple(
            ProposalScene(
                float(index),
                ("candidate-01",),
                "high" if index else "review",
            )
            for index in range(30)
        )
    )
    monkeypatch.setattr(
        proposal_cli,
        "_arguments",
        lambda: SimpleNamespace(source=Path("/private/video.mp4"), timestamps=(), model_root=Path("models")),
    )
    monkeypatch.setattr(proposal_cli, "_components", lambda root: (object(), object()))
    monkeypatch.setattr(proposal_cli, "run_native_proposal", lambda *args: proposal)

    proposal_cli.main()

    assert json.loads(capsys.readouterr().out) == {
        "highCount": 29,
        "reviewCount": 1,
        "sceneCount": 30,
    }
