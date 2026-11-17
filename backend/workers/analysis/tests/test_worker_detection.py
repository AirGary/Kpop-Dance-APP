from __future__ import annotations

from argparse import Namespace
import json
from pathlib import Path
import sys

import pytest

from stage_lab_analysis.candidates import CandidateExtractor, CandidateSet
from stage_lab_analysis.detection import Detection, NormalizedBox
from stage_lab_analysis.identity import TrackDescriptor, TrackFragment, TrackFragmentBuilder
from stage_lab_analysis.pose import PoseFrame, PoseKeypoint
from stage_lab_analysis.reid import PersonEmbedding
from stage_lab_analysis.tracking import AppearanceAwarePersonTracker, ByteTrackPersonTracker
from stage_lab_analysis.worker import AnalysisWorker, TargetAnalysisAwaitingConfirmation
from stage_lab_analysis import worker_cli


def test_worker_detect_candidates_uses_proxy_and_writes_real_candidate_paths(
    tmp_path: Path,
) -> None:
    proxy = tmp_path / "analysis" / "proxy.mp4"
    proxy.parent.mkdir()
    proxy.write_bytes(b"proxy")

    def frames(_: Path):
        for second in range(3):
            yield float(second), object(), 100, 100

    class Detector:
        def detect(self, frame: object) -> tuple[Detection, ...]:
            return (Detection(0.0, NormalizedBox(0.2, 0.1, 0.3, 0.7), 0.9),)

    worker = AnalysisWorker(detector=Detector(), frame_reader=frames)
    result = worker.detect_candidates(tmp_path)

    assert len(result.candidates) == 1
    assert result.candidates[0].representative_image_paths == (
        "analysis/candidates/candidate-1-1.jpg",
        "analysis/candidates/candidate-1-2.jpg",
        "analysis/candidates/candidate-1-3.jpg",
    )


def test_worker_uses_dense_candidate_stride_and_target_stride_independently(tmp_path: Path) -> None:
    proxy = tmp_path / "analysis" / "proxy.mp4"
    proxy.parent.mkdir()
    proxy.write_bytes(b"proxy")
    observed_strides: list[int] = []

    def frames(_: Path, stride: int):
        observed_strides.append(stride)
        for second in range(3):
            yield float(second), object(), 100, 100

    class Detector:
        def detect(self, frame: object) -> tuple[Detection, ...]:
            return (Detection(0.0, NormalizedBox(0.2, 0.1, 0.3, 0.7), 0.9),)

    class Pose:
        def estimate(self, frame, box, time_seconds):
            return PoseFrame(time_seconds, box, (PoseKeypoint("hip", 0.3, 0.5, 0.9),), 0.9)

    worker = AnalysisWorker(
        detector=Detector(),
        frame_reader=frames,
        frame_stride=30,
        candidate_frame_stride=6,
    )

    candidate = worker.detect_candidates(tmp_path).candidates[0]
    target_worker = AnalysisWorker(
        detector=Detector(),
        frame_reader=frames,
        frame_stride=30,
        candidate_frame_stride=6,
    )
    target_worker.analyze_target(tmp_path, candidate.candidate_id, Pose())

    assert observed_strides == [6, 30]


def test_target_reassociates_selected_member_when_sparse_track_ids_are_reordered(tmp_path: Path) -> None:
    proxy = tmp_path / "analysis" / "proxy.mp4"
    proxy.parent.mkdir()
    proxy.write_bytes(b"proxy")

    def frames(_: Path, stride: int):
        labels = ("dense", "dense", "dense") if stride == 6 else ("sparse", "sparse", "sparse")
        for second, label in enumerate(labels):
            yield float(second), label, 100, 100

    class Detector:
        def detect(self, frame: object) -> tuple[Detection, ...]:
            target = Detection(0.0, NormalizedBox(0.10, 0.1, 0.2, 0.7), 0.9)
            other = Detection(0.0, NormalizedBox(0.65, 0.1, 0.2, 0.7), 0.9)
            return (target, other) if frame == "dense" else (other, target)

    class AppearanceFragments(TrackFragmentBuilder):
        def build(self, tracks, frame_samples):
            fragments = []
            for track in tracks:
                target = track.samples[0].box.x < 0.5
                fragments.append(
                    TrackFragment(
                        track.track_id,
                        track,
                        TrackDescriptor(
                            hsv_histogram=(1.0, 0.0) if target else (0.0, 1.0),
                            edge_density=0.2,
                            shoulder_to_hip_ratio=None,
                            torso_to_height_ratio=None,
                            pose_quality=0.0,
                            start_center=(track.samples[0].box.x + 0.1, 0.45),
                            end_center=(track.samples[-1].box.x + 0.1, 0.45),
                            velocity=(0.0, 0.0),
                        ),
                    )
                )
            return tuple(fragments)

    class Pose:
        def estimate(self, frame, box, time_seconds):
            return PoseFrame(time_seconds, box, (PoseKeypoint("hip", 0.3, 0.5, 0.9),), 0.9)

    dense_worker = AnalysisWorker(
        detector=Detector(),
        frame_reader=frames,
        tracker=ByteTrackPersonTracker(),
        fragment_builder=AppearanceFragments(),
        frame_stride=30,
        candidate_frame_stride=6,
    )
    candidate = dense_worker.detect_candidates(tmp_path).candidates[0]
    sparse_worker = AnalysisWorker(
        detector=Detector(),
        frame_reader=frames,
        tracker=ByteTrackPersonTracker(),
        fragment_builder=AppearanceFragments(),
        frame_stride=30,
        candidate_frame_stride=6,
    )

    result = sparse_worker.analyze_target(tmp_path, candidate.candidate_id, Pose())

    assert result.pose_frames
    assert {frame.box[0] for frame in result.pose_frames} == {0.1}


def test_target_pauses_for_confirmation_when_sparse_reassociation_is_ambiguous(tmp_path: Path) -> None:
    import numpy as np

    proxy = tmp_path / "analysis" / "proxy.mp4"
    proxy.parent.mkdir()
    proxy.write_bytes(b"proxy")

    def frames(_: Path, stride: int):
        value = 0 if stride == 6 else 1
        for second in range(3):
            yield float(second), np.full((100, 100, 3), value, dtype=np.uint8), 100, 100

    class Detector:
        def detect(self, frame: object) -> tuple[Detection, ...]:
            return (
                Detection(0.0, NormalizedBox(0.10, 0.1, 0.2, 0.7), 0.9),
                Detection(0.0, NormalizedBox(0.65, 0.1, 0.2, 0.7), 0.9),
            )

    class AmbiguousFragments(TrackFragmentBuilder):
        def build(self, tracks, frame_samples):
            fragments = []
            for track in tracks:
                sparse = int(frame_samples[track.track_id][0][1][0, 0, 0]) == 1
                target = track.samples[0].box.x < 0.5
                histogram = (0.95, 0.05) if sparse and target else (1.0, 0.0) if target else (0.9, 0.1)
                fragments.append(
                    TrackFragment(
                        track.track_id,
                        track,
                        TrackDescriptor(
                            hsv_histogram=histogram,
                            edge_density=0.2,
                            shoulder_to_hip_ratio=None,
                            torso_to_height_ratio=None,
                            pose_quality=0.0,
                            start_center=(track.samples[0].box.x + 0.1, 0.45),
                            end_center=(track.samples[-1].box.x + 0.1, 0.45),
                            velocity=(0.0, 0.0),
                        ),
                    )
                )
            return tuple(fragments)

    class Pose:
        def estimate(self, frame, box, time_seconds):
            return PoseFrame(time_seconds, box, (PoseKeypoint("hip", 0.3, 0.5, 0.9),), 0.9)

    dense_worker = AnalysisWorker(
        detector=Detector(),
        frame_reader=frames,
        tracker=ByteTrackPersonTracker(),
        fragment_builder=AmbiguousFragments(),
        frame_stride=30,
        candidate_frame_stride=6,
    )
    candidate = dense_worker.detect_candidates(tmp_path).candidates[0]
    fragments = tmp_path / "analysis" / "identity-fragments"
    for fragment_id in (1, 2):
        for index in (1, 3):
            (fragments / f"fragment-{fragment_id}-{index}.jpg").write_bytes(b"private-crop")
    sparse_worker = AnalysisWorker(
        detector=Detector(),
        frame_reader=frames,
        tracker=ByteTrackPersonTracker(),
        fragment_builder=AmbiguousFragments(),
        frame_stride=30,
        candidate_frame_stride=6,
    )

    result = sparse_worker.analyze_target(tmp_path, candidate.candidate_id, Pose())

    assert isinstance(result, TargetAnalysisAwaitingConfirmation)
    assert result.confirmation.previous_image_path.startswith("analysis/identity-fragments/")
    assert result.confirmation.candidate_image_path.startswith("analysis/target-identity-fragments/")


def test_reassociation_confirmation_shows_sparse_fragment_and_same_admits_its_poses(tmp_path: Path) -> None:
    import numpy as np

    proxy = tmp_path / "analysis" / "proxy.mp4"
    proxy.parent.mkdir()
    proxy.write_bytes(b"proxy")

    def frames(_: Path, stride: int):
        value, times = (0, (10.0, 11.0, 12.0)) if stride == 6 else (1, (100.0, 130.0, 160.0))
        for second in times:
            yield second, np.full((100, 100, 3), value, dtype=np.uint8), 100, 100

    class Detector:
        def detect(self, frame: object) -> tuple[Detection, ...]:
            return (
                Detection(0.0, NormalizedBox(0.10, 0.1, 0.2, 0.7), 0.9),
                Detection(0.0, NormalizedBox(0.65, 0.1, 0.2, 0.7), 0.9),
            )

    class AmbiguousFragments(TrackFragmentBuilder):
        def build(self, tracks, frame_samples):
            fragments = []
            for track in tracks:
                sparse = int(frame_samples[track.track_id][0][1][0, 0, 0]) == 1
                target = track.samples[0].box.x < 0.5
                if sparse:
                    histogram = (0.95, 0.05) if target else (0.0, 1.0)
                else:
                    histogram = (1.0, 0.0) if target else (0.9, 0.1)
                fragments.append(
                    TrackFragment(
                        track.track_id,
                        track,
                        TrackDescriptor(
                            hsv_histogram=histogram,
                            edge_density=0.2,
                            shoulder_to_hip_ratio=None,
                            torso_to_height_ratio=None,
                            pose_quality=0.0,
                            start_center=(track.samples[0].box.x + 0.1, 0.45),
                            end_center=(track.samples[-1].box.x + 0.1, 0.45),
                            velocity=(0.0, 0.0),
                        ),
                    )
                )
            return tuple(fragments)

    class Pose:
        def estimate(self, frame, box, time_seconds):
            return PoseFrame(time_seconds, box, (PoseKeypoint("hip", 0.3, 0.5, 0.9),), 0.9)

    def worker() -> AnalysisWorker:
        return AnalysisWorker(
            detector=Detector(),
            frame_reader=frames,
            tracker=ByteTrackPersonTracker(),
            fragment_builder=AmbiguousFragments(),
            frame_stride=30,
            candidate_frame_stride=6,
        )

    candidate = worker().detect_candidates(tmp_path).candidates[0]
    awaiting = worker().analyze_target(tmp_path, candidate.candidate_id, Pose())

    assert isinstance(awaiting, TargetAnalysisAwaitingConfirmation)
    assert awaiting.confirmation.candidate_image_path.startswith("analysis/target-identity-fragments/")
    assert awaiting.confirmation.candidate_interval == (100.0, 160.0)

    (tmp_path / "analysis" / "identity-decision.json").write_text(
        json.dumps({"decisions": [{
            "confirmationId": awaiting.confirmation.confirmation_id,
            "decision": "same",
            "idempotencyKey": "sparse-same",
        }]}),
        encoding="utf-8",
    )
    completed = worker().analyze_target(tmp_path, candidate.candidate_id, Pose())

    assert not isinstance(completed, TargetAnalysisAwaitingConfirmation)
    assert {frame.box[0] for frame in completed.pose_frames} == {0.1}


def test_worker_omitting_candidate_stride_keeps_legacy_frame_stride(tmp_path: Path) -> None:
    proxy = tmp_path / "analysis" / "proxy.mp4"
    proxy.parent.mkdir()
    proxy.write_bytes(b"proxy")
    observed_strides: list[int] = []

    def frames(_: Path, stride: int):
        observed_strides.append(stride)
        for second in range(3):
            yield float(second), object(), 100, 100

    class Detector:
        def detect(self, frame: object) -> tuple[Detection, ...]:
            return (Detection(0.0, NormalizedBox(0.2, 0.1, 0.3, 0.7), 0.9),)

    AnalysisWorker(detector=Detector(), frame_reader=frames, frame_stride=30).detect_candidates(tmp_path)

    assert observed_strides == [30]


def test_cli_parses_candidate_frame_stride(monkeypatch) -> None:
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "worker_cli",
            "detect",
            "--workspace",
            "/tmp/workspace",
            "--model-root",
            "/tmp/models",
            "--frame-stride",
            "30",
            "--candidate-frame-stride",
            "6",
        ],
    )

    args = worker_cli._arguments()

    assert args.frame_stride == 30
    assert args.candidate_frame_stride == 6


def test_worker_rejects_non_positive_candidate_frame_stride() -> None:
    class Detector:
        def detect(self, frame: object) -> tuple[Detection, ...]:
            return ()

    with pytest.raises(ValueError, match="candidate frame stride must be positive"):
        AnalysisWorker(detector=Detector(), candidate_frame_stride=0)


def test_worker_passes_job_local_reid_embeddings_to_appearance_tracking(tmp_path: Path) -> None:
    proxy = tmp_path / "analysis" / "proxy.mp4"
    proxy.parent.mkdir()
    proxy.write_bytes(b"proxy")

    class Detector:
        def detect(self, frame: object) -> tuple[Detection, ...]:
            return (Detection(0.0, NormalizedBox(0.2, 0.1, 0.3, 0.7), 0.9),)

    class Embedder:
        def __init__(self) -> None:
            self.calls: list[tuple[object, NormalizedBox]] = []

        def embed(self, frame: object, box: NormalizedBox) -> PersonEmbedding:
            self.calls.append((frame, box))
            return PersonEmbedding((1.0, 0.0), 0.9)

    embedder = Embedder()
    worker = AnalysisWorker(
        detector=Detector(),
        frame_reader=lambda _: ((float(second), object(), 100, 100) for second in range(3)),
        tracker=AppearanceAwarePersonTracker(),
        reid_embedder=embedder,
    )

    worker.detect_candidates(tmp_path)

    assert len(embedder.calls) == 3
    assert all(sample.embedding == PersonEmbedding((1.0, 0.0), 0.9) for sample in worker.tracker.all_tracks[0].samples)


def test_cli_injects_the_verified_reid_embedder_into_detection_worker(
    tmp_path: Path,
    monkeypatch,
) -> None:
    captured: dict[str, object] = {}
    sentinel_embedder = object()

    class Worker:
        def __init__(self, **kwargs) -> None:
            captured.update(kwargs)

        def detect_candidates(self, workspace: Path) -> CandidateSet:
            return CandidateSet(())

    monkeypatch.setattr(
        worker_cli,
        "_arguments",
        lambda: Namespace(
            operation="detect",
            workspace=tmp_path,
            model_root=tmp_path,
            candidate_id=None,
            frame_stride=6,
            candidate_frame_stride=6,
        ),
    )
    monkeypatch.setattr(worker_cli, "create_proxy", lambda _source, _proxy: None)
    monkeypatch.setattr(worker_cli, "RTMDetPersonDetector", lambda **_kwargs: object())
    monkeypatch.setattr(worker_cli, "_reid_embedder", lambda _root: sentinel_embedder, raising=False)
    monkeypatch.setattr(worker_cli, "AnalysisWorker", Worker)

    worker_cli.main()

    assert captured["reid_embedder"] is sentinel_embedder


def test_worker_keeps_candidates_that_leave_before_the_final_frame(tmp_path: Path) -> None:
    proxy = tmp_path / "analysis" / "proxy.mp4"
    proxy.parent.mkdir()
    proxy.write_bytes(b"proxy")

    frames = iter(
        (
            (0.0, "first", 100, 100),
            (1.0, "first", 100, 100),
            (2.0, "missing", 100, 100),
            (3.0, "second", 100, 100),
            (4.0, "second", 100, 100),
        )
    )

    class Detector:
        def detect(self, frame: object) -> tuple[Detection, ...]:
            if frame == "missing":
                return ()
            x = 0.1 if frame == "first" else 0.6
            return (Detection(0.0, NormalizedBox(x, 0.1, 0.2, 0.7), 0.9),)

    worker = AnalysisWorker(
        detector=Detector(),
        frame_reader=lambda _: frames,
        tracker=ByteTrackPersonTracker(max_missed_frames=0, match_iou=0.1),
        candidate_extractor=CandidateExtractor(min_visible_seconds=0.5),
    )

    result = worker.detect_candidates(tmp_path)

    assert [candidate.appearance_intervals for candidate in result.candidates] == [
        ((0.0, 1.0),),
        ((3.0, 4.0),),
    ]


def test_worker_merges_compatible_fragments_into_one_candidate(tmp_path: Path) -> None:
    proxy = tmp_path / "analysis" / "proxy.mp4"
    proxy.parent.mkdir()
    proxy.write_bytes(b"proxy")

    frames = iter(
        (
            (0.0, "first", 100, 100),
            (1.0, "first", 100, 100),
            (2.0, "missing", 100, 100),
            (3.0, "second", 100, 100),
            (4.0, "second", 100, 100),
        )
    )

    class Detector:
        def detect(self, frame: object) -> tuple[Detection, ...]:
            if frame == "missing":
                return ()
            return (Detection(0.0, NormalizedBox(0.2, 0.1, 0.2, 0.7), 0.9),)

    worker = AnalysisWorker(
        detector=Detector(),
        frame_reader=lambda _: frames,
        tracker=ByteTrackPersonTracker(max_missed_frames=0, match_iou=0.1),
        candidate_extractor=CandidateExtractor(min_visible_seconds=0.5),
    )

    result = worker.detect_candidates(tmp_path)

    assert [candidate.appearance_intervals for candidate in result.candidates] == [
        ((0.0, 1.0), (3.0, 4.0)),
    ]
    payload = json.loads((tmp_path / "analysis" / "identity-clusters.json").read_text())
    assert payload["identitySchemaVersion"] == 1
    assert payload["fragments"][0]["descriptor"]["hsvHistogram"]
    assert payload["candidateClusters"] == {"candidate-1": [1, 2]}


def test_target_analysis_uses_every_fragment_in_the_selected_identity_cluster(tmp_path: Path) -> None:
    proxy = tmp_path / "analysis" / "proxy.mp4"
    proxy.parent.mkdir()
    proxy.write_bytes(b"proxy")

    sequence = (
        (0.0, "first", 100, 100),
        (1.0, "first", 100, 100),
        (2.0, "missing", 100, 100),
        (3.0, "second", 100, 100),
        (4.0, "second", 100, 100),
    )

    class Detector:
        def detect(self, frame: object) -> tuple[Detection, ...]:
            if frame == "missing":
                return ()
            return (Detection(0.0, NormalizedBox(0.2, 0.1, 0.2, 0.7), 0.9),)

    class Pose:
        def estimate(self, frame: object, box: tuple[float, float, float, float], time_seconds: float) -> PoseFrame:
            return PoseFrame(time_seconds, box, (PoseKeypoint("hip", 0.3, 0.5, 0.9),), 0.9)

    def reader(_: Path):
        return iter(sequence)

    def worker() -> AnalysisWorker:
        return AnalysisWorker(
            detector=Detector(),
            frame_reader=reader,
            tracker=ByteTrackPersonTracker(max_missed_frames=0, match_iou=0.1),
            candidate_extractor=CandidateExtractor(min_visible_seconds=0.5),
        )

    candidate = worker().detect_candidates(tmp_path).candidates[0]
    target = worker().analyze_target(tmp_path, candidate.candidate_id, Pose())

    assert [frame.time_seconds for frame in target.pose_frames] == [0.0, 1.0, 3.0, 4.0]


def test_detection_retains_at_most_six_frame_samples_per_track(tmp_path: Path) -> None:
    proxy = tmp_path / "analysis" / "proxy.mp4"
    proxy.parent.mkdir()
    proxy.write_bytes(b"proxy")

    class RecordingBuilder(TrackFragmentBuilder):
        sample_counts: dict[int, int]
        sample_times: dict[int, list[float]]

        def build(self, tracks, frame_samples):
            self.sample_counts = {track_id: len(samples) for track_id, samples in frame_samples.items()}
            self.sample_times = {
                track_id: sorted(sample[0] for sample in samples)
                for track_id, samples in frame_samples.items()
            }
            return super().build(tracks, frame_samples)

    class Detector:
        def detect(self, frame: object) -> tuple[Detection, ...]:
            return (Detection(0.0, NormalizedBox(0.2, 0.1, 0.3, 0.7), 0.9),)

    builder = RecordingBuilder()
    worker = AnalysisWorker(
        detector=Detector(),
        frame_reader=lambda _: ((float(second), object(), 100, 100) for second in range(10)),
        fragment_builder=builder,
    )

    worker.detect_candidates(tmp_path)

    assert builder.sample_counts == {1: 6}
    assert builder.sample_times[1][0] == 0.0
    assert builder.sample_times[1][-1] == 9.0


def test_worker_analyzes_only_selected_candidate(tmp_path: Path) -> None:
    proxy = tmp_path / "analysis" / "proxy.mp4"
    proxy.parent.mkdir()
    proxy.write_bytes(b"proxy")

    def frames(_: Path):
        for second in range(3):
            yield float(second), object(), 100, 100

    class Detector:
        def detect(self, frame: object) -> tuple[Detection, ...]:
            return (Detection(0.0, NormalizedBox(0.2, 0.1, 0.3, 0.7), 0.9),)

    class Pose:
        def estimate(self, frame, box, time_seconds):
            return PoseFrame(time_seconds, box, (PoseKeypoint("hip", 0.3, 0.5, 0.9),), 0.9)

    worker = AnalysisWorker(detector=Detector(), frame_reader=frames)
    result = worker.analyze_target(tmp_path, "candidate-1", Pose())

    assert len(result.pose_frames) == 3
    assert result.spotlight
    assert result.timeline
