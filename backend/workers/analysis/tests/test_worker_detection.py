from __future__ import annotations

import json
from pathlib import Path

from stage_lab_analysis.candidates import CandidateExtractor
from stage_lab_analysis.detection import Detection, NormalizedBox
from stage_lab_analysis.identity import TrackFragmentBuilder
from stage_lab_analysis.pose import PoseFrame, PoseKeypoint
from stage_lab_analysis.tracking import ByteTrackPersonTracker
from stage_lab_analysis.worker import AnalysisWorker


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
