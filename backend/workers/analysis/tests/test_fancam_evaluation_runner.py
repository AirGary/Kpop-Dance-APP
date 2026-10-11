from __future__ import annotations

from dataclasses import replace
import json
from io import StringIO
from math import sqrt
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest

from stage_lab_analysis.fancam_demo import evaluation_cli
from stage_lab_analysis.fancam_demo.components import ComponentCandidate, ComponentScore
from stage_lab_analysis.fancam_demo.evaluate import EvaluationResult
from stage_lab_analysis.fancam_demo.evaluation_runner import run_current_baseline
from stage_lab_analysis.fancam_demo.local_review import ReviewCancelled
from stage_lab_analysis.fancam_demo.selection import select_candidate
from stage_lab_analysis.fancam_demo.truth import GroundTruthScene, GroundTruthSet
from stage_lab_analysis.reid import PersonEmbedding


def _truth(
    visible_member_ids: tuple[str, ...] = ("member-01",),
) -> GroundTruthSet:
    return GroundTruthSet(
        tuple(
            GroundTruthScene(float(index), visible_member_ids)
            for index in range(30)
        )
    )


class _Detection:
    box = object()


class _OneUnmappedDetection:
    def __init__(self) -> None:
        self.calls = 0

    def detect(self, frame: object) -> tuple[_Detection, ...]:
        self.calls += 1
        return (_Detection(),) if self.calls == 1 else ()


class _Embedder:
    def embed(self, frame: object, box: object) -> object:
        return object()


class _EmbeddedDetection:
    def __init__(self, embedding: PersonEmbedding | None) -> None:
        self.box = embedding


class _SequenceDetector:
    def __init__(self, scenes: tuple[tuple[_EmbeddedDetection, ...], ...]) -> None:
        self._scenes = scenes

    def detect(self, frame: object) -> tuple[_EmbeddedDetection, ...]:
        return self._scenes[int(frame)] if int(frame) < len(self._scenes) else ()


class _SequenceEmbedder:
    def embed(self, frame: object, box: PersonEmbedding | None) -> PersonEmbedding | None:
        return box


class _FakeReviewer:
    def __init__(self, confirmations: dict[str, str | list[str | None]]) -> None:
        self._confirmations = confirmations
        self._known: dict[str, str] = {}
        self.calls: list[str] = []
        self.force_calls: list[bool] = []
        self.closed = False

    def review(
        self,
        frame: object,
        detection: object,
        runtime_candidate_id: str,
        *,
        force: bool = False,
    ) -> str | None:
        self.calls.append(runtime_candidate_id)
        self.force_calls.append(force)
        member_id = self._confirmations.get(runtime_candidate_id)
        if isinstance(member_id, list):
            member_id = member_id.pop(0)
        if member_id is not None:
            self._known[runtime_candidate_id] = member_id
        return member_id

    def known(self, runtime_candidate_id: str) -> str | None:
        return self._known.get(runtime_candidate_id)

    def close(self) -> None:
        self.closed = True


def _embedding(first: float, second: float) -> PersonEmbedding:
    return PersonEmbedding((first, second), quality=1.0)


def _sequence_reader(source: Path, timestamp_seconds: float) -> float:
    return timestamp_seconds


def _reader(source: Path, timestamp_seconds: float) -> object:
    return object()


def _score_with(*, id_switches: int) -> ComponentScore:
    candidate = ComponentCandidate(
        name="current-baseline",
        version="1.0",
        license_id="Apache-2.0",
        cpu_probe=lambda: True,
        run=lambda *args, **kwargs: None,
        provenance="approved-manifest",
        supply_chain_reviewed=True,
    )
    return ComponentScore(
        candidate=candidate,
        result=EvaluationResult(0.95, 0.95, id_switches, 0, 0),
        elapsed_seconds=1.0,
        labelled_minutes=1.0,
        # Synthetic evidence only, so the ID-switch gate is tested independently.
        identity_evidence_verified=True,
    )


def test_selection_rejects_nonzero_id_switches() -> None:
    assert select_candidate((_score_with(id_switches=1),)) is None


def test_runner_uses_same_run_review_for_first_runtime_candidate_and_never_serializes_it() -> None:
    reviewer = _FakeReviewer({"candidate-01": "member-01"})
    score = run_current_baseline(
        Path("private-source.mp4"),
        _truth(),
        _SequenceDetector(((_EmbeddedDetection(_embedding(1.0, 0.0)),),)),
        _SequenceEmbedder(),
        reviewer=reviewer,
        reader=_sequence_reader,
    )

    assert reviewer.calls == ["candidate-01"]
    assert score.result.confirmation_requests == 1
    assert reviewer.closed is True
    assert "candidate-01" not in json.dumps(score.to_json())


def test_runner_counts_a_stable_member_with_a_new_runtime_candidate_as_an_id_switch() -> None:
    reviewer = _FakeReviewer(
        {
            "candidate-01": "member-01",
            "candidate-02": "member-01",
        }
    )
    score = run_current_baseline(
        Path("private-source.mp4"),
        _truth(),
        _SequenceDetector(
            (
                (_EmbeddedDetection(_embedding(1.0, 0.0)),),
                (_EmbeddedDetection(None),),
            )
        ),
        _SequenceEmbedder(),
        reviewer=reviewer,
        reader=_sequence_reader,
    )

    assert score.result.id_switches == 1


def test_runner_counts_wrong_multi_person_confirmation_as_false_lock() -> None:
    reviewer = _FakeReviewer(
        {
            "candidate-01": "member-01",
            "candidate-02": "member-01",
        }
    )
    score = run_current_baseline(
        Path("private-source.mp4"),
        _truth(("member-01", "member-02")),
        _SequenceDetector(
            (
                (
                    _EmbeddedDetection(_embedding(1.0, 0.0)),
                    _EmbeddedDetection(_embedding(0.0, 1.0)),
                ),
            )
        ),
        _SequenceEmbedder(),
        reviewer=reviewer,
        reader=_sequence_reader,
    )

    assert score.result.false_locks == 1


def test_ambiguous_association_and_count_change_request_review_without_locking() -> None:
    reviewer = _FakeReviewer({})
    ambiguous = _embedding(0.99, sqrt(1.0 - 0.99**2))
    score = run_current_baseline(
        Path("private-source.mp4"),
        _truth(("member-01", "member-02")),
        _SequenceDetector(
            (
                (
                    _EmbeddedDetection(_embedding(1.0, 0.0)),
                    _EmbeddedDetection(ambiguous),
                ),
                (
                    _EmbeddedDetection(_embedding(1.0, 0.0)),
                    _EmbeddedDetection(ambiguous),
                ),
                (_EmbeddedDetection(_embedding(1.0, 0.0)),),
            )
        ),
        _SequenceEmbedder(),
        reviewer=reviewer,
        reader=_sequence_reader,
    )

    assert score.result.confirmation_requests >= 1
    assert score.result.false_locks == 0
    assert reviewer.calls == [
        "candidate-01",
        "candidate-02",
        "candidate-01",
        "candidate-01",
    ]
    assert reviewer.closed is True


def test_runner_forces_re_review_of_a_known_runtime_candidate_when_score_is_low() -> None:
    reviewer = _FakeReviewer({"candidate-01": ["member-01", None]})

    score = run_current_baseline(
        Path("private-source.mp4"),
        _truth(),
        _SequenceDetector(
            (
                (_EmbeddedDetection(_embedding(1.0, 0.0)),),
                (_EmbeddedDetection(_embedding(0.8, 0.6)),),
            )
        ),
        _SequenceEmbedder(),
        reviewer=reviewer,
        reader=_sequence_reader,
    )

    assert reviewer.calls == ["candidate-01", "candidate-01"]
    assert reviewer.force_calls == [True, True]
    assert score.result.confirmation_requests == 2
    assert reviewer.closed is True


def test_runner_counts_only_initial_review_for_confident_cached_assignments() -> None:
    reviewer = _FakeReviewer({"candidate-01": "member-01"})
    score = run_current_baseline(
        Path("private-source.mp4"),
        _truth(),
        _SequenceDetector(((_EmbeddedDetection(_embedding(1.0, 0.0)),),) * 30),
        _SequenceEmbedder(),
        reviewer=reviewer,
        reader=_sequence_reader,
    )

    assert reviewer.calls == ["candidate-01"]
    assert score.result.confirmation_requests == 1


def test_runner_all_human_correct_results_never_pass_identity_evidence_gate() -> None:
    # Space samples so that even 30 reviews satisfy the legacy per-minute gate.
    truth = GroundTruthSet(
        tuple(GroundTruthScene(float(index * 120), ("member-01",)) for index in range(30))
    )
    reviewer = _FakeReviewer({"candidate-01": "member-01"})
    detections = ((_EmbeddedDetection(_embedding(1.0, 0.0)),),) + (
        (_EmbeddedDetection(_embedding(0.8, 0.6)),),
    ) * 29
    score = run_current_baseline(
        Path("private-source.mp4"),
        truth,
        _SequenceDetector(detections),
        _SequenceEmbedder(),
        reviewer=reviewer,
        reader=lambda source, timestamp: timestamp / 120,
    )
    # Avoid reading local CPU state; keep the real runner result unchanged.
    score = replace(score, candidate=replace(score.candidate, cpu_probe=lambda: True))

    assert len(reviewer.calls) == 30
    assert score.result.detection_recall == 1.0
    assert score.result.identity_accuracy == 1.0
    assert score.result.false_locks == score.result.id_switches == 0
    assert score.result.confirmation_requests / score.labelled_minutes <= 1.0
    assert select_candidate((score,)) is None
    assert score.result.confirmation_requests == 30
    assert score.identity_evidence_verified is False
    assert score.to_json()["identityEvidenceVerified"] is False
    assert score.to_json()["metricScope"] == "member_set_consistency_only"


def test_local_review_session_close_clears_runtime_and_member_mappings() -> None:
    from stage_lab_analysis.fancam_demo.local_review import LocalReviewSession

    class _ReviewSession(LocalReviewSession):
        def _prompt(
            self,
            frame: object,
            detection: object,
            runtime_candidate_id: str,
        ) -> str | None:
            return "member-01"

    reviewer = _ReviewSession()

    assert reviewer.review(object(), object(), "candidate-01") == "member-01"
    assert reviewer.known("candidate-01") == "member-01"
    reviewer.close()
    reviewer.close()
    assert reviewer.known("candidate-01") is None


def test_local_review_session_forced_different_member_keeps_existing_mapping() -> None:
    from stage_lab_analysis.fancam_demo.local_review import LocalReviewSession

    class _ReviewSession(LocalReviewSession):
        def __init__(self) -> None:
            super().__init__()
            self.responses = iter(("member-01", "member-02"))

        def _prompt(
            self,
            frame: object,
            detection: object,
            runtime_candidate_id: str,
        ) -> str | None:
            return next(self.responses)

    reviewer = _ReviewSession()

    assert reviewer.review(object(), object(), "candidate-01") == "member-01"
    assert reviewer.review(object(), object(), "candidate-01", force=True) is None
    assert reviewer.known("candidate-01") == "member-01"


def test_local_review_session_forced_same_member_reconfirms_existing_mapping() -> None:
    from stage_lab_analysis.fancam_demo.local_review import LocalReviewSession

    class _ReviewSession(LocalReviewSession):
        def __init__(self) -> None:
            super().__init__()
            self.responses = iter(("member-01", "member-01"))

        def _prompt(
            self,
            frame: object,
            detection: object,
            runtime_candidate_id: str,
        ) -> str | None:
            return next(self.responses)

    reviewer = _ReviewSession()

    assert reviewer.review(object(), object(), "candidate-01") == "member-01"
    assert reviewer.review(object(), object(), "candidate-01", force=True) == "member-01"
    assert reviewer.known("candidate-01") == "member-01"


def test_local_review_session_forced_rejection_leaves_scene_unconfirmed_and_mapping_intact() -> None:
    from stage_lab_analysis.fancam_demo.local_review import LocalReviewSession

    class _ReviewSession(LocalReviewSession):
        def __init__(self) -> None:
            super().__init__()
            self.responses = iter(("member-01", None))

        def _prompt(
            self,
            frame: object,
            detection: object,
            runtime_candidate_id: str,
        ) -> str | None:
            return next(self.responses)

    reviewer = _ReviewSession()

    assert reviewer.review(object(), object(), "candidate-01") == "member-01"
    assert reviewer.review(object(), object(), "candidate-01", force=True) is None
    assert reviewer.known("candidate-01") == "member-01"


@pytest.mark.parametrize("failure_point", ("reader", "detector", "embedder", "reviewer"))
def test_runner_closes_local_review_mappings_when_pipeline_raises(
    failure_point: str,
) -> None:
    from stage_lab_analysis.fancam_demo.local_review import LocalReviewSession

    class _ReviewSession(LocalReviewSession):
        def _prompt(
            self,
            frame: object,
            detection: object,
            runtime_candidate_id: str,
        ) -> str | None:
            if runtime_candidate_id == "candidate-00":
                return "member-01"
            if failure_point == "reviewer":
                raise RuntimeError("reviewer failed")
            return None

    class _Detector:
        def detect(self, frame: object) -> tuple[_Detection, ...]:
            if failure_point == "detector":
                raise RuntimeError("detector failed")
            return (_Detection(),)

    class _Embedder:
        def embed(self, frame: object, box: object) -> object:
            if failure_point == "embedder":
                raise RuntimeError("embedder failed")
            return object()

    def reader(source: Path, timestamp_seconds: float) -> object:
        if failure_point == "reader":
            raise RuntimeError("reader failed")
        return object()

    reviewer = _ReviewSession()
    assert reviewer.review(object(), object(), "candidate-00") == "member-01"

    with pytest.raises(RuntimeError, match=failure_point):
        run_current_baseline(
            Path("private-source.mp4"),
            _truth(),
            _Detector(),
            _Embedder(),
            reviewer=reviewer,
            reader=reader,
        )

    assert reviewer.known("candidate-00") is None


def test_runner_treats_rejection_as_unconfirmed_safe_result_not_user_cancellation() -> None:
    reviewer = _FakeReviewer({})

    score = run_current_baseline(
        Path("private-source.mp4"),
        _truth(),
        _OneUnmappedDetection(),
        _Embedder(),
        reviewer=reviewer,
        reader=_reader,
    )

    assert score.result.confirmation_requests == 1
    assert score.result.identity_accuracy is None
    assert select_candidate((score,)) is None
    assert reviewer.closed is True


def test_cli_exits_nonzero_without_stdout_and_closes_reviewer_when_user_cancels(
    monkeypatch, capsys
) -> None:
    created_reviewers: list[object] = []

    class _CancellingReviewer:
        def __init__(self) -> None:
            self.closed = False
            created_reviewers.append(self)

        def review(
            self,
            frame: object,
            detection: object,
            runtime_candidate_id: str,
            *,
            force: bool = False,
        ) -> str | None:
            raise ReviewCancelled()

        def known(self, runtime_candidate_id: str) -> str | None:
            return None

        def close(self) -> None:
            self.closed = True

    def run(source, truth, detector, embedder, *, reviewer):
        return run_current_baseline(
            source,
            truth,
            _OneUnmappedDetection(),
            _Embedder(),
            reviewer=reviewer,
            reader=_reader,
        )

    candidate = ComponentCandidate(
        name="current-baseline",
        version="1.0",
        license_id="Apache-2.0",
        cpu_probe=lambda: True,
        run=run,
        provenance="approved-manifest",
        supply_chain_reviewed=True,
    )
    monkeypatch.setattr(
        evaluation_cli,
        "_arguments",
        lambda: SimpleNamespace(source=Path("private-source.mp4"), model_root=Path("models")),
    )
    monkeypatch.setattr(evaluation_cli, "_components", lambda root: (object(), object()))
    monkeypatch.setattr(evaluation_cli, "_truth_path", lambda: Path("canonical.local.json"))
    monkeypatch.setattr(evaluation_cli, "load_ground_truth", lambda path: _truth())
    monkeypatch.setattr(evaluation_cli, "register_current_baseline", lambda: candidate)
    monkeypatch.setattr(evaluation_cli, "LocalReviewSession", _CancellingReviewer)

    with pytest.raises(SystemExit) as exited:
        evaluation_cli.main()

    assert exited.value.code != 0
    assert capsys.readouterr().out == ""
    assert len(created_reviewers) == 1
    assert created_reviewers[0].closed is True


def test_local_review_popup_never_displays_runtime_candidate_id(
    monkeypatch,
) -> None:
    import numpy as np

    from stage_lab_analysis.fancam_demo.local_review import LocalReviewSession

    displayed_text: list[str] = []

    class _OpenCV:
        FONT_HERSHEY_SIMPLEX = 0
        LINE_AA = 0

        @staticmethod
        def putText(image, text, *args):
            displayed_text.append(text)

        @staticmethod
        def imshow(name, image):
            return None

        @staticmethod
        def waitKey(delay):
            return ord("x")

        @staticmethod
        def destroyWindow(name):
            return None

    monkeypatch.setitem(sys.modules, "cv2", _OpenCV)
    reviewer = LocalReviewSession()

    assert reviewer.review(
        np.zeros((10, 10, 3), dtype=np.uint8),
        SimpleNamespace(box=SimpleNamespace(x=0.0, y=0.0, width=1.0, height=1.0)),
        "candidate-01",
    ) is None

    assert "candidate-01" not in displayed_text


def test_local_review_unavailability_leaves_candidate_unconfirmed(monkeypatch) -> None:
    from stage_lab_analysis.fancam_demo.local_review import LocalReviewSession

    monkeypatch.setitem(sys.modules, "cv2", None)

    assert LocalReviewSession().review(object(), object(), "candidate-01") is None


def test_runner_turns_unmapped_runtime_candidate_into_confirmation() -> None:
    score = run_current_baseline(
        Path("private-source.mp4"),
        _truth(),
        _OneUnmappedDetection(),
        _Embedder(),
        reviewer=_FakeReviewer({}),
        reader=_reader,
    )

    assert score.result.confirmation_requests == 1
    assert score.result.identity_accuracy is None


def test_runner_never_serializes_runtime_candidate_ids_or_observations() -> None:
    score = run_current_baseline(
        Path("private-source.mp4"),
        _truth(),
        _OneUnmappedDetection(),
        _Embedder(),
        reviewer=_FakeReviewer({"candidate-01": "member-01"}),
        reader=_reader,
    )

    serialized = json.dumps(score.to_json())
    assert "candidate" not in serialized
    assert "member-01" not in serialized
    assert "private-source.mp4" not in serialized


def test_cli_ignores_stdin_creates_a_local_reviewer_and_prints_only_aggregate_json(
    monkeypatch, capsys
) -> None:
    created_reviewers: list[object] = []
    received: dict[str, object] = {}

    class _FakeReviewer:
        def __init__(self) -> None:
            created_reviewers.append(self)

    def run(source, truth, detector, embedder, *, reviewer):
        received["reviewer"] = reviewer
        return score

    candidate = ComponentCandidate(
        name="current-baseline",
        version="1.0",
        license_id="Apache-2.0",
        cpu_probe=lambda: True,
        run=run,
        provenance="approved-manifest",
        supply_chain_reviewed=True,
    )
    score = ComponentScore(
        candidate=candidate,
        result=EvaluationResult(0.95, 0.95, 0, 0, 1),
        elapsed_seconds=1.0,
        labelled_minutes=1.0,
    )
    monkeypatch.setattr(
        evaluation_cli,
        "_arguments",
        lambda: SimpleNamespace(source=Path("private-source.mp4"), model_root=Path("models")),
    )
    monkeypatch.setattr(evaluation_cli, "_components", lambda root: (object(), object()))
    monkeypatch.setattr(evaluation_cli, "_truth_path", lambda: Path("canonical.local.json"))
    monkeypatch.setattr(evaluation_cli, "load_ground_truth", lambda path: _truth())
    monkeypatch.setattr(evaluation_cli, "register_current_baseline", lambda: candidate)
    monkeypatch.setattr(evaluation_cli, "LocalReviewSession", _FakeReviewer, raising=False)
    monkeypatch.setattr(evaluation_cli.sys, "stdin", StringIO("not a mapping"))

    evaluation_cli.main()

    stdout = capsys.readouterr().out
    payload = json.loads(stdout)
    assert created_reviewers == [received["reviewer"]]
    assert stdout == json.dumps(payload, separators=(",", ":"), sort_keys=True) + "\n"
    assert "candidate-01" not in stdout
    assert "member-01" not in stdout
    assert "private-source.mp4" not in stdout


def test_cli_prints_only_aggregate_metadata_and_metrics(
    monkeypatch, capsys
) -> None:
    scores: list[ComponentScore] = []
    candidate = ComponentCandidate(
        name="current-baseline",
        version="1.0",
        license_id="Apache-2.0",
        cpu_probe=lambda: True,
        run=lambda *args, **kwargs: scores[0],
        provenance="approved-manifest",
        supply_chain_reviewed=True,
    )
    score = ComponentScore(
        candidate=candidate,
        result=EvaluationResult(0.95, 0.95, 0, 0, 1),
        elapsed_seconds=1.0,
        labelled_minutes=1.0,
    )
    scores.append(score)
    monkeypatch.setattr(
        evaluation_cli,
        "_arguments",
        lambda: SimpleNamespace(source=Path("private-source.mp4"), model_root=Path("models")),
    )
    monkeypatch.setattr(evaluation_cli, "_components", lambda root: (object(), object()))
    monkeypatch.setattr(evaluation_cli, "_truth_path", lambda: Path("canonical.local.json"))
    monkeypatch.setattr(evaluation_cli, "load_ground_truth", lambda path: _truth())
    monkeypatch.setattr(evaluation_cli, "register_current_baseline", lambda: candidate)
    monkeypatch.setattr(evaluation_cli.sys, "stdin", StringIO('{"candidate-01":"member-01"}'))

    evaluation_cli.main()

    payload = json.loads(capsys.readouterr().out)
    assert set(payload) == {
        "candidate",
        "metrics",
        "elapsedSeconds",
        "labelledMinutes",
        "selected",
        "identityEvidenceVerified",
        "metricScope",
    }
    assert payload["identityEvidenceVerified"] is False
    assert payload["metricScope"] == "member_set_consistency_only"
    assert payload["selected"] is False
    assert "candidate-01" not in json.dumps(payload)
    assert "member-01" not in json.dumps(payload)
    assert "private-source.mp4" not in json.dumps(payload)
