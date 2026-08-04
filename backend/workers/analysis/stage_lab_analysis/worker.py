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
from .pose import PoseEstimator, PoseFrame, PoseKeypoint, SpotlightKeyframe, build_spotlight_track, validate_pose_track
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


@dataclass(frozen=True, slots=True)
class IdentityConfirmation:
    confirmation_id: str
    previous_image_path: str
    candidate_image_path: str
    previous_interval: tuple[float, float]
    candidate_interval: tuple[float, float]
    candidate_cluster_id: str


@dataclass(frozen=True, slots=True)
class TargetAnalysisCompleted:
    result: TargetAnalysis

    # Preserve the pre-Task-2 internal test ergonomics for completed outcomes.
    @property
    def candidate_id(self) -> str:
        return self.result.candidate_id

    @property
    def pose_frames(self) -> tuple[PoseFrame, ...]:
        return self.result.pose_frames

    @property
    def spotlight(self) -> tuple[SpotlightKeyframe, ...]:
        return self.result.spotlight

    @property
    def timeline(self) -> tuple[PracticeSegment, ...]:
        return self.result.timeline


@dataclass(frozen=True, slots=True)
class TargetAnalysisAwaitingConfirmation:
    confirmation: IdentityConfirmation


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
    ) -> TargetAnalysisCompleted | TargetAnalysisAwaitingConfirmation:
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
            result = self._target_result(candidate_id, selected_samples, pose_estimator, beats)
            return TargetAnalysisCompleted(result)
        else:
            return self._checkpointed_target_result(
                proxy.parent,
                candidate_id,
                selected_fragment_ids,
                frame_samples,
                pose_estimator,
                beats,
            )

    @staticmethod
    def _target_result(
        candidate_id: str,
        selected_samples: Iterable[tuple[float, object, object]],
        pose_estimator: PoseEstimator,
        beats: tuple[float, ...],
    ) -> TargetAnalysis:
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

    def _checkpointed_target_result(
        self,
        analysis_directory: Path,
        candidate_id: str,
        selected_fragment_ids: tuple[int, ...],
        frame_samples: dict[int, list[tuple[float, object, object]]],
        pose_estimator: PoseEstimator,
        beats: tuple[float, ...],
    ) -> TargetAnalysisCompleted | TargetAnalysisAwaitingConfirmation:
        clusters = self._read_identity_clusters(analysis_directory)
        fragments = {
            int(fragment["fragmentId"]): fragment
            for fragment in clusters["fragments"]
            if isinstance(fragment, dict) and isinstance(fragment.get("fragmentId"), int)
        }
        plan_path = analysis_directory / "target-work-plan.json"
        plan = self._read_optional_json(plan_path)
        if plan is None:
            ordered_fragment_ids = sorted(fragments, key=lambda item: self._fragment_start(fragments, item))
            accepted_fragment_ids = list(sorted(selected_fragment_ids, key=lambda item: self._fragment_start(fragments, item)))
            plan = {
                "candidateId": candidate_id,
                "fragmentIds": ordered_fragment_ids,
                "acceptedFragmentIds": accepted_fragment_ids,
                "excludedFragmentIds": [],
                "acceptedFragments": accepted_fragment_ids,
                "rejectedFragments": [],
                "pendingConfirmationId": None,
                "pendingFragmentId": None,
                "pendingPreviousFragmentId": None,
                "nextFragmentIndex": 0,
            }
            self._write_json_atomic(plan_path, plan)
        if plan.get("candidateId") != candidate_id:
            raise ValueError("target work plan belongs to another candidate")
        accepted = self._valid_fragment_ids(
            plan.get("acceptedFragmentIds", plan.get("acceptedFragments")), fragments
        )
        excluded = self._valid_fragment_ids(
            plan.get("excludedFragmentIds", plan.get("rejectedFragments")), fragments
        )
        ordered = self._valid_fragment_ids(
            plan.get("fragmentIds", sorted(fragments, key=lambda item: self._fragment_start(fragments, item))),
            fragments,
        )
        if set(ordered) != set(fragments):
            raise ValueError("target work plan does not cover every identity fragment")
        pending_id = plan.get("pendingConfirmationId")
        pending_fragment = plan.get("pendingFragmentId")
        decisions_value = self._read_optional_json(analysis_directory / "identity-decision.json")
        decisions = (
            decisions_value.get("decisions", [decisions_value])
            if isinstance(decisions_value, dict)
            else []
        )
        decision = next(
            (
                item for item in reversed(decisions)
                if isinstance(item, dict) and item.get("confirmationId") == pending_id
            ),
            None,
        )
        if pending_id is not None and decision is not None:
            if decision.get("confirmationId") != pending_id or decision.get("decision") not in {"same", "different"}:
                raise ValueError("identity decision does not match pending confirmation")
            if not isinstance(pending_fragment, int) or pending_fragment not in fragments:
                raise ValueError("pending confirmation fragment is invalid")
            if decision["decision"] == "same" and pending_fragment not in accepted:
                accepted.append(pending_fragment)
            if decision["decision"] == "different" and pending_fragment not in excluded:
                excluded.append(pending_fragment)
            accepted.sort(key=lambda item: self._fragment_start(fragments, item))
            plan.update({
                "acceptedFragmentIds": accepted,
                "excludedFragmentIds": excluded,
                "fragmentIds": ordered,
                "acceptedFragments": accepted,
                "rejectedFragments": excluded,
                "pendingConfirmationId": None,
                "pendingFragmentId": None,
                "pendingPreviousFragmentId": None,
            })
            self._write_json_atomic(plan_path, plan)
        if pending_id is not None and decision is None:
            confirmation = self._confirmation_from_plan(analysis_directory, candidate_id, fragments, plan)
            return TargetAnalysisAwaitingConfirmation(confirmation)
        checkpoints = analysis_directory / "target-checkpoints"
        next_index = int(plan.get("nextFragmentIndex", 0))
        while next_index < len(ordered):
            fragment_id = ordered[next_index]
            if fragment_id in excluded:
                next_index += 1
                plan["nextFragmentIndex"] = next_index
                self._write_json_atomic(plan_path, plan)
                continue
            if fragment_id not in accepted:
                pending = self._confirmation_for_fragment(clusters, accepted, excluded, fragment_id)
                if pending is not None:
                    previous_fragment, candidate_fragment = pending
                    confirmation_id = f"identity-{candidate_id}-{previous_fragment}-{candidate_fragment}"
                    plan.update({
                        "pendingConfirmationId": confirmation_id,
                        "pendingFragmentId": candidate_fragment,
                        "pendingPreviousFragmentId": previous_fragment,
                    })
                    self._write_json_atomic(plan_path, plan)
                    return TargetAnalysisAwaitingConfirmation(
                        self._confirmation_from_plan(analysis_directory, candidate_id, fragments, plan)
                    )
                next_index += 1
                plan["nextFragmentIndex"] = next_index
                self._write_json_atomic(plan_path, plan)
                continue
            checkpoint = checkpoints / f"{fragment_id}.json"
            if not checkpoint.exists():
                samples = frame_samples.get(fragment_id, ())
                if not samples:
                    raise ValueError("selected identity fragment has no tracked frames")
                poses = tuple(
                    pose_estimator.estimate(frame, (box.x, box.y, box.width, box.height), time_seconds)
                    for time_seconds, frame, box in samples
                )
                self._write_json_atomic(checkpoint, {
                    "fragmentId": fragment_id,
                    "poseFrames": [self._pose_json(frame) for frame in validate_pose_track(poses)],
                })
            next_index += 1
            plan["nextFragmentIndex"] = next_index
            self._write_json_atomic(plan_path, plan)
        pose_frames = tuple(
            frame
            for fragment_id in accepted
            for frame in self._read_checkpoint(checkpoints / f"{fragment_id}.json")
        )
        validated = validate_pose_track(tuple(sorted(pose_frames, key=lambda frame: frame.time_seconds)))
        return TargetAnalysisCompleted(TargetAnalysis(
            candidate_id=candidate_id,
            pose_frames=validated,
            spotlight=build_spotlight_track(validated),
            timeline=build_practice_timeline(validated, beats=beats),
        ))

    @staticmethod
    def _read_identity_clusters(analysis_directory: Path) -> dict:
        value = AnalysisWorker._read_optional_json(analysis_directory / "identity-clusters.json")
        if not isinstance(value, dict) or not isinstance(value.get("fragments"), list) or not isinstance(value.get("decisions"), list):
            raise ValueError("identity clusters are invalid")
        return value

    @staticmethod
    def _read_optional_json(path: Path):
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return None
        except json.JSONDecodeError as error:
            raise ValueError("analysis checkpoint JSON is invalid") from error

    @staticmethod
    def _write_json_atomic(path: Path, value: object) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
        temporary = Path(temporary_name)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                json.dump(value, handle, separators=(",", ":"), sort_keys=True, allow_nan=False)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, path)
            directory_descriptor = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
            try:
                os.fsync(directory_descriptor)
            finally:
                os.close(directory_descriptor)
        except Exception:
            temporary.unlink(missing_ok=True)
            raise

    @staticmethod
    def _fragment_start(fragments: dict[int, dict], fragment_id: int) -> float:
        try:
            value = fragments[fragment_id]["startSeconds"]
        except KeyError as error:
            raise ValueError("identity fragment is invalid") from error
        if not isinstance(value, (int, float)) or isinstance(value, bool) or not isfinite(value):
            raise ValueError("identity fragment start is invalid")
        return float(value)

    @staticmethod
    def _valid_fragment_ids(value: object, fragments: dict[int, dict]) -> list[int]:
        if not isinstance(value, list) or any(not isinstance(item, int) or item not in fragments for item in value):
            raise ValueError("target work plan fragments are invalid")
        return list(dict.fromkeys(value))

    @staticmethod
    def _next_confirmation(
        clusters: dict,
        accepted: list[int],
        excluded: list[int],
        fragments: dict[int, dict],
    ) -> tuple[int, int] | None:
        unresolved: list[tuple[int, int]] = []
        accepted_set = set(accepted)
        excluded_set = set(excluded)
        for decision in clusters["decisions"]:
            if not isinstance(decision, dict) or decision.get("kind") != "awaiting_confirmation":
                continue
            earlier = decision.get("earlierFragmentId")
            later = decision.get("laterFragmentId")
            if (
                isinstance(earlier, int)
                and isinstance(later, int)
                and earlier in accepted_set
                and later in fragments
                and later not in accepted_set
                and later not in excluded_set
            ):
                unresolved.append((earlier, later))
        return min(unresolved, key=lambda edge: (AnalysisWorker._fragment_start(fragments, edge[1]), edge[1])) if unresolved else None

    @staticmethod
    def _confirmation_for_fragment(
        clusters: dict,
        accepted: list[int],
        excluded: list[int],
        fragment_id: int,
    ) -> tuple[int, int] | None:
        accepted_set = set(accepted)
        excluded_set = set(excluded)
        for decision in clusters["decisions"]:
            if not isinstance(decision, dict) or decision.get("kind") != "awaiting_confirmation":
                continue
            earlier, later = decision.get("earlierFragmentId"), decision.get("laterFragmentId")
            if (
                isinstance(earlier, int)
                and later == fragment_id
                and earlier in accepted_set
                and later not in excluded_set
            ):
                return earlier, fragment_id
        return None

    @staticmethod
    def _confirmation_from_plan(
        analysis_directory: Path,
        candidate_id: str,
        fragments: dict[int, dict],
        plan: dict,
    ) -> IdentityConfirmation:
        pending_fragment = plan.get("pendingFragmentId")
        previous_fragment = plan.get("pendingPreviousFragmentId")
        if not isinstance(pending_fragment, int) or not isinstance(previous_fragment, int):
            raise ValueError("pending confirmation is invalid")
        inverse_clusters: dict[int, str] = {}
        clusters = AnalysisWorker._read_identity_clusters(analysis_directory).get("candidateClusters", {})
        if isinstance(clusters, dict):
            for cluster_id, ids in clusters.items():
                if isinstance(cluster_id, str) and isinstance(ids, list):
                    for fragment_id in ids:
                        if isinstance(fragment_id, int):
                            inverse_clusters.setdefault(fragment_id, cluster_id)
        previous_cluster = inverse_clusters.get(previous_fragment, candidate_id)
        candidate_cluster = inverse_clusters.get(pending_fragment)
        if candidate_cluster is None:
            raise ValueError("candidate confirmation image is unavailable")
        previous_path = f"analysis/candidates/{previous_cluster}-3.jpg"
        candidate_path = f"analysis/candidates/{candidate_cluster}-1.jpg"
        if not (analysis_directory / "candidates" / f"{previous_cluster}-3.jpg").is_file() or not (analysis_directory / "candidates" / f"{candidate_cluster}-1.jpg").is_file():
            raise RuntimeError("confirmation representative image is unavailable")
        confirmation_id = plan.get("pendingConfirmationId")
        if not isinstance(confirmation_id, str) or not confirmation_id:
            raise ValueError("pending confirmation ID is invalid")
        return IdentityConfirmation(
            confirmation_id=confirmation_id,
            previous_image_path=previous_path,
            candidate_image_path=candidate_path,
            previous_interval=AnalysisWorker._fragment_interval(fragments, previous_fragment),
            candidate_interval=AnalysisWorker._fragment_interval(fragments, pending_fragment),
            candidate_cluster_id=candidate_cluster,
        )

    @staticmethod
    def _fragment_interval(fragments: dict[int, dict], fragment_id: int) -> tuple[float, float]:
        fragment = fragments.get(fragment_id)
        if not isinstance(fragment, dict):
            raise ValueError("identity fragment is invalid")
        start, end = fragment.get("startSeconds"), fragment.get("endSeconds")
        if (
            not isinstance(start, (int, float))
            or not isinstance(end, (int, float))
            or isinstance(start, bool)
            or isinstance(end, bool)
            or not isfinite(start)
            or not isfinite(end)
            or end <= start
        ):
            raise ValueError("identity fragment interval is invalid")
        return float(start), float(end)

    @staticmethod
    def _pose_json(frame: PoseFrame) -> dict:
        return {
            "timeSeconds": frame.time_seconds,
            "box": list(frame.box),
            "keypoints": [
                {"name": point.name, "x": point.x, "y": point.y, "confidence": point.confidence}
                for point in frame.keypoints
            ],
            "confidence": frame.confidence,
        }

    @staticmethod
    def _read_checkpoint(path: Path) -> tuple[PoseFrame, ...]:
        value = AnalysisWorker._read_optional_json(path)
        if not isinstance(value, dict) or not isinstance(value.get("poseFrames"), list):
            raise ValueError("pose checkpoint is invalid")
        frames: list[PoseFrame] = []
        for item in value["poseFrames"]:
            if not isinstance(item, dict) or not isinstance(item.get("box"), list) or len(item["box"]) != 4:
                raise ValueError("pose checkpoint frame is invalid")
            try:
                frames.append(PoseFrame(
                    float(item["timeSeconds"]),
                    tuple(float(number) for number in item["box"]),
                    tuple(
                        PoseKeypoint(
                            str(point["name"]), float(point["x"]), float(point["y"]), float(point["confidence"])
                        )
                        for point in item["keypoints"]
                    ),
                    float(item["confidence"]),
                ))
            except (KeyError, TypeError, ValueError) as error:
                raise ValueError("pose checkpoint frame is invalid") from error
        return validate_pose_track(frames)

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
