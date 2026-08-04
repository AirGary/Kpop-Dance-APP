from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from math import hypot, isfinite
from typing import Mapping

from .tracking import Track


class IdentityDecisionKind(str, Enum):
    MERGE = "merge"
    AWAITING_CONFIRMATION = "awaiting_confirmation"
    REJECT = "reject"


@dataclass(frozen=True, slots=True)
class TrackDescriptor:
    """Non-biometric, job-local signals used to compare two track fragments."""

    hsv_histogram: tuple[float, ...]
    edge_density: float
    shoulder_to_hip_ratio: float | None
    torso_to_height_ratio: float | None
    pose_quality: float
    start_center: tuple[float, float]
    end_center: tuple[float, float]
    velocity: tuple[float, float]

    @property
    def is_valid(self) -> bool:
        values = (*self.hsv_histogram, self.edge_density, self.pose_quality, *self.start_center, *self.end_center, *self.velocity)
        if not self.hsv_histogram or not all(isfinite(value) for value in values):
            return False
        if (
            any(value < 0 for value in self.hsv_histogram)
            or sum(self.hsv_histogram) <= 0
            or not 0 <= self.edge_density <= 1
            or not 0 <= self.pose_quality <= 1
            or any(not 0 <= value <= 1 for value in (*self.start_center, *self.end_center))
        ):
            return False
        optional = (self.shoulder_to_hip_ratio, self.torso_to_height_ratio)
        return all(value is None or (isfinite(value) and value >= 0) for value in optional)


@dataclass(frozen=True, slots=True)
class TrackFragment:
    fragment_id: int
    track: Track
    descriptor: TrackDescriptor

    @property
    def start_seconds(self) -> float:
        return self.track.samples[0].time_seconds

    @property
    def end_seconds(self) -> float:
        return self.track.samples[-1].time_seconds


class TrackFragmentBuilder:
    """Build non-biometric descriptors from the detector's job-local frame samples."""

    def build(
        self,
        tracks: tuple[Track, ...],
        frame_samples: Mapping[int, list[tuple[float, object, object]]],
    ) -> tuple[TrackFragment, ...]:
        return tuple(
            TrackFragment(track.track_id, track, self._descriptor(track, frame_samples.get(track.track_id, [])))
            for track in tracks
            if track.samples
        )

    def _descriptor(self, track: Track, samples: list[tuple[float, object, object]]) -> TrackDescriptor:
        start = track.samples[0]
        end = track.samples[-1]
        duration = max(end.time_seconds - start.time_seconds, 0.001)
        start_center = (start.box.x + start.box.width / 2, start.box.y + start.box.height / 2)
        end_center = (end.box.x + end.box.width / 2, end.box.y + end.box.height / 2)
        histogram, edge_density = self._appearance(samples)
        return TrackDescriptor(
            hsv_histogram=histogram,
            edge_density=edge_density,
            shoulder_to_hip_ratio=None,
            torso_to_height_ratio=None,
            pose_quality=0.0,
            start_center=start_center,
            end_center=end_center,
            velocity=((end_center[0] - start_center[0]) / duration, (end_center[1] - start_center[1]) / duration),
        )

    @staticmethod
    def _appearance(samples: list[tuple[float, object, object]]) -> tuple[tuple[float, ...], float]:
        usable = sorted(
            (sample for sample in samples if hasattr(sample[1], "shape")),
            key=lambda sample: sample[0],
        )
        if not usable:
            # Synthetic/unit-test readers have no pixels. Real OpenCV input always takes the branch below.
            return (1.0,), 0.0
        try:
            import cv2
        except ImportError as error:
            raise RuntimeError("OpenCV is required for identity descriptors") from error
        histograms: list[tuple[float, ...]] = []
        edge_values: list[float] = []
        selected_count = min(6, len(usable))
        selected = [
            usable[index * (len(usable) - 1) // max(1, selected_count - 1)]
            for index in range(selected_count)
        ]
        for _, frame, box in selected:
            height, width = frame.shape[:2]
            left = max(0, int(box.x * width))
            top = max(0, int(box.y * height))
            right = min(width, int((box.x + box.width) * width))
            bottom = min(height, int((box.y + box.height) * height))
            crop = frame[top:bottom, left:right]
            if crop.size == 0:
                continue
            hsv = cv2.cvtColor(cv2.resize(crop, (32, 64)), cv2.COLOR_BGR2HSV)
            histogram = cv2.calcHist([hsv], [0, 1], None, [4, 4], [0, 180, 0, 256]).flatten()
            total = float(histogram.sum())
            if total <= 0:
                continue
            histograms.append(tuple(float(value / total) for value in histogram))
            edges = cv2.Canny(cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY), 80, 160)
            edge_values.append(float((edges > 0).mean()))
        if not histograms:
            return (), 0.0
        mean_histogram = tuple(sum(values) / len(histograms) for values in zip(*histograms))
        return mean_histogram, sum(edge_values) / len(edge_values)


@dataclass(frozen=True, slots=True)
class IdentityCluster:
    cluster_id: int
    fragments: tuple[TrackFragment, ...]

    @property
    def fragment_ids(self) -> tuple[int, ...]:
        return tuple(fragment.fragment_id for fragment in self.fragments)


@dataclass(frozen=True, slots=True)
class IdentityDecision:
    kind: IdentityDecisionKind
    earlier_fragment_id: int
    later_fragment_id: int
    score: float | None = None

    @classmethod
    def merge(cls, earlier_fragment_id: int, later_fragment_id: int, score: float = 1.0) -> "IdentityDecision":
        return cls(IdentityDecisionKind.MERGE, earlier_fragment_id, later_fragment_id, score)

    @classmethod
    def awaiting_confirmation(cls, earlier_fragment_id: int, later_fragment_id: int, score: float = 0.0) -> "IdentityDecision":
        return cls(IdentityDecisionKind.AWAITING_CONFIRMATION, earlier_fragment_id, later_fragment_id, score)

    @classmethod
    def reject(cls, earlier_fragment_id: int, later_fragment_id: int, score: float = 0.0) -> "IdentityDecision":
        return cls(IdentityDecisionKind.REJECT, earlier_fragment_id, later_fragment_id, score)


@dataclass(frozen=True, slots=True)
class IdentityClusteringResult:
    clusters: tuple[IdentityCluster, ...]
    decisions: tuple[IdentityDecision, ...]


class ConservativeIdentityClusterer:
    """Greedily merge only unambiguous, time-compatible track fragments."""

    auto_merge_score = 0.88
    auto_merge_without_pose_score = 0.93
    confirmation_score = 0.68
    max_gap_seconds = 5.0
    max_unexplained_distance = 0.30

    def cluster(self, fragments: tuple[TrackFragment, ...]) -> IdentityClusteringResult:
        ordered = tuple(sorted(fragments, key=lambda item: (item.start_seconds, item.fragment_id)))
        clusters: list[list[TrackFragment]] = []
        decisions: list[IdentityDecision] = []
        for fragment in ordered:
            compatible: list[tuple[float, int, TrackFragment]] = []
            nearest_previous: TrackFragment | None = None
            for index, cluster in enumerate(clusters):
                previous = cluster[-1]
                if nearest_previous is None or previous.end_seconds > nearest_previous.end_seconds:
                    nearest_previous = previous
                score = self._score(previous, fragment)
                if score is not None:
                    compatible.append((score, index, previous))
            if not compatible:
                clusters.append([fragment])
                if nearest_previous is not None:
                    decisions.append(IdentityDecision.reject(nearest_previous.fragment_id, fragment.fragment_id))
                continue
            score, cluster_index, previous = max(compatible, key=lambda item: (item[0], -item[1]))
            if score >= self._automatic_merge_threshold(previous, fragment):
                clusters[cluster_index].append(fragment)
                decisions.append(IdentityDecision.merge(previous.fragment_id, fragment.fragment_id, score))
            elif score >= self.confirmation_score:
                clusters.append([fragment])
                decisions.append(IdentityDecision.awaiting_confirmation(previous.fragment_id, fragment.fragment_id, score))
            else:
                clusters.append([fragment])
                decisions.append(IdentityDecision.reject(previous.fragment_id, fragment.fragment_id, score))
        return IdentityClusteringResult(
            clusters=tuple(IdentityCluster(index + 1, tuple(cluster)) for index, cluster in enumerate(clusters)),
            decisions=tuple(decisions),
        )

    def _automatic_merge_threshold(self, earlier: TrackFragment, later: TrackFragment) -> float:
        if self._pose_similarity(earlier.descriptor, later.descriptor) is None:
            return self.auto_merge_without_pose_score
        return self.auto_merge_score

    def _score(self, earlier: TrackFragment, later: TrackFragment) -> float | None:
        if not earlier.descriptor.is_valid or not later.descriptor.is_valid:
            return None
        gap = later.start_seconds - earlier.end_seconds
        if gap <= 0 or gap > self.max_gap_seconds:
            return None
        expected_x = earlier.descriptor.end_center[0] + earlier.descriptor.velocity[0] * gap
        expected_y = earlier.descriptor.end_center[1] + earlier.descriptor.velocity[1] * gap
        distance = hypot(later.descriptor.start_center[0] - expected_x, later.descriptor.start_center[1] - expected_y)
        if distance > self.max_unexplained_distance:
            return None
        appearance = self._appearance_similarity(earlier.descriptor, later.descriptor)
        temporal = max(0.0, 1.0 - distance / self.max_unexplained_distance)
        pose = self._pose_similarity(earlier.descriptor, later.descriptor)
        if pose is None:
            return (0.55 * appearance + 0.25 * temporal) / 0.80
        return 0.55 * appearance + 0.20 * pose + 0.25 * temporal

    @staticmethod
    def _appearance_similarity(first: TrackDescriptor, second: TrackDescriptor) -> float:
        if len(first.hsv_histogram) != len(second.hsv_histogram):
            return 0.0
        first_total = sum(first.hsv_histogram)
        second_total = sum(second.hsv_histogram)
        histogram_distance = sum(abs(left / first_total - right / second_total) for left, right in zip(first.hsv_histogram, second.hsv_histogram))
        histogram_similarity = max(0.0, 1.0 - histogram_distance / 2.0)
        edge_similarity = max(0.0, 1.0 - abs(first.edge_density - second.edge_density))
        return 0.8 * histogram_similarity + 0.2 * edge_similarity

    @staticmethod
    def _pose_similarity(first: TrackDescriptor, second: TrackDescriptor) -> float | None:
        if first.pose_quality <= 0 or second.pose_quality <= 0:
            return None
        if first.shoulder_to_hip_ratio is None or second.shoulder_to_hip_ratio is None:
            return None
        if first.torso_to_height_ratio is None or second.torso_to_height_ratio is None:
            return None
        shoulder = max(0.0, 1.0 - abs(first.shoulder_to_hip_ratio - second.shoulder_to_hip_ratio))
        torso = max(0.0, 1.0 - abs(first.torso_to_height_ratio - second.torso_to_height_ratio))
        return (shoulder + torso + min(first.pose_quality, second.pose_quality)) / 3.0
