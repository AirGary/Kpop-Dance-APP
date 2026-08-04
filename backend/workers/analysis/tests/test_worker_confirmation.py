import json
import zipfile
from argparse import Namespace
from pathlib import Path
from types import SimpleNamespace

from stage_lab_analysis.pose import PoseFrame, PoseKeypoint
from stage_lab_analysis.worker import (
    AnalysisWorker,
    TargetAnalysisAwaitingConfirmation,
    TargetAnalysisCompleted,
)
from stage_lab_analysis import worker_cli
from stage_lab_analysis.worker_cli import _target_outcome_payload


class Pose:
    def __init__(self) -> None:
        self.calls: list[float] = []

    def estimate(self, _frame, box, time_seconds: float) -> PoseFrame:
        self.calls.append(time_seconds)
        return PoseFrame(
            time_seconds,
            box,
            (PoseKeypoint("hip", 0.3, 0.5, 0.9),),
            0.9,
        )


def _clusters(analysis: Path) -> None:
    (analysis / "candidates").mkdir(parents=True)
    for name in ("candidate-1-3.jpg", "candidate-2-1.jpg"):
        (analysis / "candidates" / name).write_bytes(b"synthetic-private-crop")
    (analysis / "identity-clusters.json").write_text(json.dumps({
        "fragments": [
            {"fragmentId": 1, "startSeconds": 1, "endSeconds": 1.5},
            {"fragmentId": 2, "startSeconds": 2, "endSeconds": 2.5},
            {"fragmentId": 3, "startSeconds": 3, "endSeconds": 3.5},
        ],
        "candidateClusters": {"candidate-1": [1, 3], "candidate-2": [2]},
        "decisions": [{
            "kind": "awaiting_confirmation",
            "earlierFragmentId": 1,
            "laterFragmentId": 2,
        }],
    }), encoding="utf-8")


def _frames():
    box = SimpleNamespace(x=0.2, y=0.1, width=0.3, height=0.7)
    return {
        1: [(1.0, object(), box)],
        2: [(2.0, object(), box)],
        3: [(3.0, object(), box)],
    }


def _worker() -> AnalysisWorker:
    return AnalysisWorker(detector=SimpleNamespace(detect=lambda _frame: ()))


def test_confirmation_pauses_before_later_selected_fragment_and_same_recovers_from_checkpoint(tmp_path: Path) -> None:
    analysis = tmp_path / "analysis"
    _clusters(analysis)
    first_pose = Pose()

    first = _worker()._checkpointed_target_result(
        analysis, "candidate-1", (1, 3), _frames(), first_pose, ()
    )

    assert isinstance(first, TargetAnalysisAwaitingConfirmation)
    assert first.confirmation.candidate_cluster_id == "candidate-2"
    assert first_pose.calls == [1.0]
    assert (analysis / "target-checkpoints" / "1.json").is_file()
    assert not (analysis / "target-checkpoints" / "3.json").exists()

    (analysis / "identity-decision.json").write_text(json.dumps({"decisions": [{
        "confirmationId": first.confirmation.confirmation_id,
        "decision": "same",
        "idempotencyKey": "same-key",
    }]}), encoding="utf-8")
    resumed_pose = Pose()
    completed = _worker()._checkpointed_target_result(
        analysis, "candidate-1", (1, 3), _frames(), resumed_pose, ()
    )

    assert isinstance(completed, TargetAnalysisCompleted)
    assert [frame.time_seconds for frame in completed.result.pose_frames] == [1.0, 2.0, 3.0]
    assert resumed_pose.calls == [2.0, 3.0]


def test_different_excludes_confirmation_interval_and_cli_writes_unchanged_package_members(tmp_path: Path) -> None:
    analysis = tmp_path / "analysis"
    _clusters(analysis)
    awaiting = _worker()._checkpointed_target_result(
        analysis, "candidate-1", (1, 3), _frames(), Pose(), ()
    )
    assert isinstance(awaiting, TargetAnalysisAwaitingConfirmation)
    (analysis / "identity-decision.json").write_text(json.dumps({"decisions": [{
        "confirmationId": awaiting.confirmation.confirmation_id,
        "decision": "different",
        "idempotencyKey": "different-key",
    }]}), encoding="utf-8")

    completed = _worker()._checkpointed_target_result(
        analysis, "candidate-1", (1, 3), _frames(), Pose(), ()
    )

    assert isinstance(completed, TargetAnalysisCompleted)
    assert [frame.time_seconds for frame in completed.result.pose_frames] == [1.0, 3.0]
    payload = _target_outcome_payload(completed, analysis / "proxy.mp4")
    assert payload["outcome"] == "completed"
    with zipfile.ZipFile(analysis / "result-v1.zip") as archive:
        assert tuple(sorted(archive.namelist())) == (
            "confidence.json", "manifest.json", "pose-track.json", "spotlight-track.json", "timeline.json"
        )


def test_worker_cli_main_keeps_diagnostics_out_of_awaiting_and_completed_json(monkeypatch, tmp_path: Path, capsys) -> None:
    workspace = tmp_path / "workspace"
    model_root = tmp_path / "models"
    outputs = iter([
        {"outcome": "awaitingConfirmation", "confirmation": {"confirmationId": "confirm", "previousImagePath": "analysis/a.jpg", "candidateImagePath": "analysis/b.jpg", "previousInterval": {"startSeconds": 1, "endSeconds": 2}, "candidateInterval": {"startSeconds": 2, "endSeconds": 3}, "candidateClusterId": "candidate-2"}},
        {"outcome": "completed", "result": {"schemaVersion": 1, "sha256": "a" * 64, "byteCount": 1, "contentPath": "analysis/result-v1.zip"}},
    ])
    monkeypatch.setattr(worker_cli, "_arguments", lambda: Namespace(operation="target", workspace=workspace, model_root=model_root, candidate_id="candidate-1", frame_stride=6))
    monkeypatch.setattr(worker_cli, "create_proxy", lambda _source, _proxy: print("worker diagnostic"))
    monkeypatch.setattr(worker_cli, "RTMDetPersonDetector", lambda **_kwargs: object())
    monkeypatch.setattr(worker_cli, "AnalysisWorker", lambda **_kwargs: object())
    monkeypatch.setattr(worker_cli, "_target_response", lambda *_args: next(outputs))

    worker_cli.main()
    first = capsys.readouterr()
    worker_cli.main()
    second = capsys.readouterr()

    assert json.loads(first.out)["outcome"] == "awaitingConfirmation"
    assert json.loads(second.out)["outcome"] == "completed"
    assert "worker diagnostic" not in first.out + second.out
