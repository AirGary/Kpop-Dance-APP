from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from dataclasses import dataclass, replace
from math import isfinite
from typing import Callable, Iterable, Protocol

from .candidates import CandidateExtractor, CandidateSet
from .detection import Detection, PersonDetector
from .identity import ConservativeIdentityClusterer, TrackFragmentBuilder
from .pose import PoseEstimator, PoseFrame, SpotlightKeyframe, build_spotlight_track, validate_pose_track
from .timeline import PracticeSegment, build_practice_timeline
from .tracking import ByteTrackPersonTracker


class FrameReader(Protocol):
    def __call__(self, proxy: Path) -> Iterable[tuple[float, object, int, int]]: ...


@dataclass(frozen=True, slots=True)
class TargetAnalysis:
    candidate_id: str
    pose_frames: tuple[PoseFrame, ...]
    spotlight: tuple[SpotlightKeyframe, ...]
    timeline: tuple[PracticeSegment, ...]


def _opencv_frames(proxy: Path, frame_stride: int = 1):
    if frame_stride < 1:
        raise ValueError("frame stride must be positive")
    try:
        import cv2
    except ImportError as error:
        raise RuntimeError("OpenCV is required for candidate extraction") from error
    capture = cv2.VideoCapture(str(proxy))
    if not capture.isOpened():
        raise RuntimeError("analysis proxy could not be opened")
    try:
        fps = capture.get(cv2.CAP_PROP_FPS) or 30.0
        frame_index = 0
        while True:
            success, frame = capture.read()
            if not success:
                break
            if frame_index % frame_stride == 0:
                height, width = frame.shape[:2]
                yield frame_index / fps, frame, width, height
            frame_index += 1
    finally:
        capture.release()


class AnalysisWorker:
    def __init__(
        self,
        *,
        detector: PersonDetector,
        frame_reader: FrameReader = _opencv_frames,
        tracker: ByteTrackPersonTracker | None = None,
        candidate_extractor: CandidateExtractor | None = None,
        fragment_builder: TrackFragmentBuilder | None = None,
        clusterer: ConservativeIdentityClusterer | None = None,
        frame_stride: int = 1,
    ) -> None:
        self.detector = detector
        self.frame_reader = frame_reader
        self.tracker = tracker or ByteTrackPersonTracker()
        self.candidate_extractor = candidate_extractor or CandidateExtractor()
        self.fragment_builder = fragment_builder or TrackFragmentBuilder()
        self.clusterer = clusterer or ConservativeIdentityClusterer()
        if frame_stride < 1:
            raise ValueError("frame stride must be positive")
        self.frame_stride = frame_stride

    def detect_candidates(self, workspace: Path) -> CandidateSet:
        proxy = workspace / "proxy.mp4" if workspace.name == "analysis" else workspace / "analysis" / "proxy.mp4"
        if not proxy.is_file():
            raise FileNotFoundError("analysis proxy is missing")
        frame_samples: dict[int, list[tuple[float, object, object]]] = {}
        frame_sample_priorities: dict[int, list[int]] = {}
        frame_sample_counts: dict[int, int] = {}
        reader = self.frame_reader
        try:
            frames = reader(proxy, self.frame_stride)  # type: ignore[call-arg]
        except TypeError:
            frames = reader(proxy)
        for time_seconds, frame, _, _ in frames:
            detections = tuple(
                Detection(time_seconds, detection.box, detection.confidence)
                for detection in self.detector.detect(frame)
            )
            tracks = self.tracker.update(detections)
            for track in tracks:
                if track.samples and track.last_sample.time_seconds == time_seconds:
                    self._retain_candidate_sample(
                        frame_samples,
                        frame_sample_priorities,
                        frame_sample_counts,
                        track.track_id,
                        (time_seconds, frame, track.last_sample.box),
                    )
        analysis_directory = proxy.parent
        candidate_directory = analysis_directory / "candidates"
        candidate_directory.mkdir(parents=True, exist_ok=True)
        fragments = self.fragment_builder.build(self.tracker.all_tracks, frame_samples)
        clustering = self.clusterer.cluster(fragments)
        extracted = self.candidate_extractor.extract_clusters(
            clustering.clusters,
            representative_path=lambda cluster_id, index: f"analysis/candidates/cluster-{cluster_id}-{index}.jpg",
        )
        candidates = type(extracted)(
            tuple(
                replace(
                    candidate,
                    representative_image_paths=tuple(
                        f"analysis/candidates/{candidate.candidate_id}-{index}.jpg"
                        for index in range(1, 4)
                    ),
                )
                for candidate in extracted.candidates
            )
        )
        for candidate in candidates.candidates:
            samples = [
                sample
                for fragment_id in candidate.fragment_ids
                for sample in frame_samples.get(fragment_id, [])
            ]
            self._write_representatives(
                candidate,
                samples,
                candidate_directory,
            )
        self._write_identity_clusters(analysis_directory, clustering, candidates)
        return candidates

    def analyze_target(
        self,
        workspace: Path,
        candidate_id: str,
        pose_estimator: PoseEstimator,
        *,
        beats: tuple[float, ...] = (),
    ) -> TargetAnalysis:
        proxy = workspace / "proxy.mp4" if workspace.name == "analysis" else workspace / "analysis" / "proxy.mp4"
        if not proxy.is_file():
            raise FileNotFoundError("analysis proxy is missing")
        frame_samples: dict[int, list[tuple[float, object, object]]] = {}
        reader = self.frame_reader
        try:
            frames = reader(proxy, self.frame_stride)  # type: ignore[call-arg]
        except TypeError:
            frames = reader(proxy)
        for time_seconds, frame, _, _ in frames:
            detections = tuple(
                Detection(time_seconds, detection.box, detection.confidence)
                for detection in self.detector.detect(frame)
            )
            tracks = self.tracker.update(detections)
            for track in tracks:
                if track.samples and track.last_sample.time_seconds == time_seconds:
                    frame_samples.setdefault(track.track_id, []).append(
                        (time_seconds, frame, track.last_sample.box)
                    )
        selected_fragment_ids = self._selected_cluster_fragment_ids(proxy.parent, candidate_id)
        if selected_fragment_ids is None:
            candidates = self.candidate_extractor.extract(
                self.tracker.all_tracks,
                representative_path=lambda track_id, index: f"analysis/candidates/track-{track_id}-{index}.jpg",
            )
            selected = next((candidate for candidate in candidates.candidates if candidate.candidate_id == candidate_id), None)
            if selected is None:
                raise ValueError("selected candidate was not found")
            selected_samples = frame_samples.get(selected.primary_fragment_id, ())
        else:
            selected_samples = tuple(
                sample
                for fragment_id in selected_fragment_ids
                for sample in frame_samples.get(fragment_id, ())
            )
            if not selected_samples:
                raise ValueError("selected identity cluster has no tracked frames")
        pose_frames = tuple(
            pose_estimator.estimate(frame, (box.x, box.y, box.width, box.height), time_seconds)
            for time_seconds, frame, box in selected_samples
        )
        validated = validate_pose_track(pose_frames)
        return TargetAnalysis(
            candidate_id=candidate_id,
            pose_frames=validated,
            spotlight=build_spotlight_track(validated),
            timeline=build_practice_timeline(validated, beats=beats),
        )

    @staticmethod
    def _selected_cluster_fragment_ids(analysis_directory: Path, candidate_id: str) -> tuple[int, ...] | None:
        source = analysis_directory / "identity-clusters.json"
        if not source.exists():
            return None
        try:
            payload = json.loads(source.read_text(encoding="utf-8"))
            fragment_ids = payload["candidateClusters"][candidate_id]
        except (json.JSONDecodeError, KeyError, TypeError) as error:
            raise ValueError("selected identity cluster was not found") from error
        if not isinstance(fragment_ids, list) or not fragment_ids or any(
            not isinstance(fragment_id, int) or isinstance(fragment_id, bool) or fragment_id <= 0
            for fragment_id in fragment_ids
        ):
            raise ValueError("selected identity cluster is invalid")
        return tuple(fragment_ids)

    @staticmethod
    def _write_representatives(candidate, samples, directory: Path) -> None:
        """Write three temporally separated crops when the reader supplies image frames."""
        usable = sorted(
            (sample for sample in samples if hasattr(sample[1], "shape")),
            key=lambda sample: sample[0],
        )
        if not usable:
            return
        try:
            import cv2
        except ImportError as error:
            raise RuntimeError("OpenCV is required to write candidate images") from error
        selected = [usable[index * (len(usable) - 1) // 2] for index in range(3)]
        for index, (_, frame, box) in enumerate(selected, start=1):
            height, width = frame.shape[:2]
            padding_x = box.width * width * 0.12
            padding_y = box.height * height * 0.12
            left = max(0, int(box.x * width - padding_x))
            top = max(0, int(box.y * height - padding_y))
            right = min(width, int((box.x + box.width) * width + padding_x))
            bottom = min(height, int((box.y + box.height) * height + padding_y))
            crop = frame[top:bottom, left:right]
            success, encoded = cv2.imencode(".jpg", crop, [cv2.IMWRITE_JPEG_QUALITY, 90])
            if not success:
                raise RuntimeError("candidate image encoding failed")
            (directory / f"{candidate.candidate_id}-{index}.jpg").write_bytes(encoded.tobytes())

    @staticmethod
    def _retain_candidate_sample(
        samples_by_track: dict[int, list[tuple[float, object, object]]],
        priorities_by_track: dict[int, list[int]],
        counts_by_track: dict[int, int],
        track_id: int,
        sample: tuple[float, object, object],
    ) -> None:
        """Keep a deterministic, bounded reservoir of candidate-only frame samples."""
        count = counts_by_track.get(track_id, 0) + 1
        counts_by_track[track_id] = count
        samples = samples_by_track.setdefault(track_id, [])
        priorities = priorities_by_track.setdefault(track_id, [])
        if count == 1:
            samples.append(sample)
            priorities.append(-2)
            return
        latest_index = priorities.index(-2)
        priorities[latest_index] = -1 if count == 2 else AnalysisWorker._sample_priority(track_id, count - 1)
        samples.append(sample)
        priorities.append(-2)
        if len(samples) <= 6:
            return
        largest_index = max(range(len(priorities)), key=priorities.__getitem__)
        del samples[largest_index]
        del priorities[largest_index]

    @staticmethod
    def _sample_priority(track_id: int, count: int) -> int:
        value = ((track_id & 0xFFFFFFFF) << 32) | (count & 0xFFFFFFFF)
        value ^= value >> 30
        value = (value * 0xBF58476D1CE4E5B9) & 0xFFFFFFFFFFFFFFFF
        value ^= value >> 27
        value = (value * 0x94D049BB133111EB) & 0xFFFFFFFFFFFFFFFF
        return value ^ (value >> 31)

    @staticmethod
    def _write_identity_clusters(analysis_directory: Path, clustering, candidates: CandidateSet) -> None:
        candidate_clusters = {
            candidate.candidate_id: list(candidate.fragment_ids)
            for candidate in candidates.candidates
        }
        value = {
            "identitySchemaVersion": 1,
            "fragments": [
                {
                    "fragmentId": fragment.fragment_id,
                    "startSeconds": fragment.start_seconds,
                    "endSeconds": fragment.end_seconds,
                    "descriptor": {
                        "valid": fragment.descriptor.is_valid,
                        "hsvHistogram": [AnalysisWorker._json_number(value) for value in fragment.descriptor.hsv_histogram],
                        "edgeDensity": AnalysisWorker._json_number(fragment.descriptor.edge_density),
                        "shoulderToHipRatio": AnalysisWorker._json_number(fragment.descriptor.shoulder_to_hip_ratio),
                        "torsoToHeightRatio": AnalysisWorker._json_number(fragment.descriptor.torso_to_height_ratio),
                        "poseQuality": AnalysisWorker._json_number(fragment.descriptor.pose_quality),
                        "startCenter": [AnalysisWorker._json_number(value) for value in fragment.descriptor.start_center],
                        "endCenter": [AnalysisWorker._json_number(value) for value in fragment.descriptor.end_center],
                        "velocity": [AnalysisWorker._json_number(value) for value in fragment.descriptor.velocity],
                    },
                }
                for cluster in clustering.clusters
                for fragment in cluster.fragments
            ],
            "clusters": [
                {"clusterId": cluster.cluster_id, "fragmentIds": list(cluster.fragment_ids)}
                for cluster in clustering.clusters
            ],
            "decisions": [
                {
                    "kind": decision.kind.value,
                    "earlierFragmentId": decision.earlier_fragment_id,
                    "laterFragmentId": decision.later_fragment_id,
                    "score": AnalysisWorker._json_number(decision.score),
                }
                for decision in clustering.decisions
            ],
            "candidateClusters": candidate_clusters,
        }
        destination = analysis_directory / "identity-clusters.json"
        descriptor, temporary_name = tempfile.mkstemp(prefix=".identity-clusters.", suffix=".tmp", dir=analysis_directory)
        temporary = Path(temporary_name)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                json.dump(value, handle, separators=(",", ":"), sort_keys=True, allow_nan=False)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, destination)
            directory_descriptor = os.open(analysis_directory, os.O_RDONLY | os.O_DIRECTORY)
            try:
                os.fsync(directory_descriptor)
            finally:
                os.close(directory_descriptor)
        except Exception:
            temporary.unlink(missing_ok=True)
            raise

    @staticmethod
    def _json_number(value: float | None) -> float | None:
        return value if value is not None and isfinite(value) else None
