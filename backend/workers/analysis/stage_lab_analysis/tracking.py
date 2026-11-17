from __future__ import annotations

from dataclasses import dataclass, field
from math import hypot
from typing import Sequence

from .detection import Detection, NormalizedBox
from .reid import MIN_REID_EMBEDDING_QUALITY, PersonEmbedding, cosine_similarity


@dataclass(frozen=True, slots=True)
class TrackSample:
    time_seconds: float
    box: NormalizedBox
    confidence: float
    # This is scoped to the current local Job and is never part of Candidate/API output.
    embedding: PersonEmbedding | None = None


@dataclass(slots=True)
class Track:
    track_id: int
    samples: list[TrackSample] = field(default_factory=list)
    missed_frames: int = 0

    @property
    def last_sample(self) -> TrackSample:
        return self.samples[-1]


class ByteTrackPersonTracker:
    """Deterministic, dependency-free association boundary for ByteTrack."""

    def __init__(self, *, match_iou: float = 0.3, max_missed_frames: int = 2) -> None:
        if not 0 < match_iou <= 1 or max_missed_frames < 0:
            raise ValueError("invalid tracker configuration")
        self.match_iou = match_iou
        self.max_missed_frames = max_missed_frames
        self.tracks: list[Track] = []
        self.completed_tracks: list[Track] = []
        self._next_track_id = 1

    @property
    def all_tracks(self) -> tuple[Track, ...]:
        """Return every track seen in this video, including completed ones."""
        return tuple(self.completed_tracks + self.tracks)

    def update(self, detections: tuple[Detection, ...]) -> tuple[Track, ...]:
        unmatched_tracks = set(range(len(self.tracks)))
        unmatched_detections = set(range(len(detections)))
        pairs: list[tuple[float, int, int]] = []
        for track_index, track in enumerate(self.tracks):
            for detection_index, detection in enumerate(detections):
                pairs.append((track.last_sample.box.iou(detection.box), track_index, detection_index))
        for overlap, track_index, detection_index in sorted(pairs, key=lambda item: (-item[0], item[1], item[2])):
            if overlap < self.match_iou or track_index not in unmatched_tracks or detection_index not in unmatched_detections:
                continue
            detection = detections[detection_index]
            self.tracks[track_index].samples.append(
                TrackSample(detection.time_seconds, detection.box, detection.confidence)
            )
            self.tracks[track_index].missed_frames = 0
            unmatched_tracks.remove(track_index)
            unmatched_detections.remove(detection_index)

        for track_index in unmatched_tracks:
            self.tracks[track_index].missed_frames += 1
        for detection_index in sorted(unmatched_detections):
            detection = detections[detection_index]
            self.tracks.append(
                Track(
                    track_id=self._next_track_id,
                    samples=[TrackSample(detection.time_seconds, detection.box, detection.confidence)],
                )
            )
            self._next_track_id += 1
        active_tracks: list[Track] = []
        for track in self.tracks:
            if track.missed_frames <= self.max_missed_frames:
                active_tracks.append(track)
            else:
                self.completed_tracks.append(track)
        self.tracks = active_tracks
        return tuple(sorted(self.tracks, key=lambda track: track.track_id))


class AppearanceAwarePersonTracker(ByteTrackPersonTracker):
    """CPU-only deterministic association with motion gating and Re-ID tie-breaking."""

    _DORMANT_REID_MIN_SIMILARITY = 0.90
    _DORMANT_REID_MIN_LEAD = 0.08
    _DORMANT_REID_MAX_ELAPSED_SECONDS = 3.0

    def __init__(
        self,
        *,
        match_iou: float = 0.3,
        max_missed_frames: int = 2,
        max_motion_distance: float = 0.45,
        min_embedding_quality: float = MIN_REID_EMBEDDING_QUALITY,
    ) -> None:
        super().__init__(match_iou=match_iou, max_missed_frames=max_missed_frames)
        if max_motion_distance <= 0 or not 0 <= min_embedding_quality <= 1:
            raise ValueError("invalid appearance tracker configuration")
        self.max_motion_distance = max_motion_distance
        self.min_embedding_quality = min_embedding_quality
        self._dormant_tracks: list[Track] = []

    @property
    def all_tracks(self) -> tuple[Track, ...]:
        """Return active, completed, and candidate-pass dormant tracks."""
        return tuple(self.completed_tracks + self._dormant_tracks + self.tracks)

    def update(
        self,
        detections: tuple[Detection, ...],
        embeddings: Sequence[PersonEmbedding | None] | None = None,
        *,
        allow_dormant_reid: bool = False,
    ) -> tuple[Track, ...]:
        if embeddings is None:
            embeddings = (None,) * len(detections)
        if len(embeddings) != len(detections):
            raise ValueError("detection embeddings must align with detections")

        self._purge_expired_dormant_tracks(detections)
        unmatched_tracks = set(range(len(self.tracks)))
        unmatched_detections = set(range(len(detections)))
        camera_motion = self._estimate_camera_motion(detections)
        pairs: list[tuple[float, int, int]] = []
        for track_index, track in enumerate(self.tracks):
            for detection_index, detection in enumerate(detections):
                if self._motion_compatible(track, detection, camera_motion):
                    pairs.append((
                        self._association_score(
                            track,
                            detection,
                            embeddings[detection_index],
                            camera_motion,
                        ),
                        track_index,
                        detection_index,
                    ))
        for _, track_index, detection_index in sorted(
            pairs,
            key=lambda item: (-item[0], item[1], item[2]),
        ):
            if track_index not in unmatched_tracks or detection_index not in unmatched_detections:
                continue
            detection = detections[detection_index]
            self.tracks[track_index].samples.append(
                TrackSample(
                    detection.time_seconds,
                    detection.box,
                    detection.confidence,
                    embeddings[detection_index],
                )
            )
            self.tracks[track_index].missed_frames = 0
            unmatched_tracks.remove(track_index)
            unmatched_detections.remove(detection_index)

        for track_index in unmatched_tracks:
            self.tracks[track_index].missed_frames += 1
        if allow_dormant_reid:
            for detection_index in sorted(unmatched_detections):
                detection = detections[detection_index]
                dormant_track = self._select_dormant_track(detection, embeddings[detection_index])
                if dormant_track is None:
                    continue
                self._restore_dormant_track(dormant_track, detection, embeddings[detection_index])
                unmatched_detections.remove(detection_index)
        for detection_index in sorted(unmatched_detections):
            detection = detections[detection_index]
            self.tracks.append(
                Track(
                    track_id=self._next_track_id,
                    samples=[
                        TrackSample(
                            detection.time_seconds,
                            detection.box,
                            detection.confidence,
                            embeddings[detection_index],
                        )
                    ],
                )
            )
            self._next_track_id += 1
        active_tracks: list[Track] = []
        for track in self.tracks:
            if track.missed_frames <= self.max_missed_frames:
                active_tracks.append(track)
            elif allow_dormant_reid and self._recent_embedding(track) is not None:
                self._dormant_tracks.append(track)
            else:
                self.completed_tracks.append(track)
        self.tracks = active_tracks
        return tuple(sorted(self.tracks, key=lambda track: track.track_id))

    def _purge_expired_dormant_tracks(self, detections: Sequence[Detection]) -> None:
        if not detections:
            return
        current_time = max(detection.time_seconds for detection in detections)
        active_dormant: list[Track] = []
        for track in self._dormant_tracks:
            if current_time - track.last_sample.time_seconds > self._DORMANT_REID_MAX_ELAPSED_SECONDS:
                self.completed_tracks.append(track)
            else:
                active_dormant.append(track)
        self._dormant_tracks = active_dormant

    def _select_dormant_track(
        self,
        detection: Detection,
        embedding: PersonEmbedding | None,
    ) -> Track | None:
        if not self._usable_embedding(embedding):
            return None
        scored_tracks = sorted(
            (
                (cosine_similarity(gallery, embedding), track)
                for track in self._dormant_tracks
                if (gallery := self._recent_embedding(track)) is not None
                and 0.0 < detection.time_seconds - track.last_sample.time_seconds
                <= self._DORMANT_REID_MAX_ELAPSED_SECONDS
            ),
            key=lambda item: (-item[0], item[1].track_id),
        )
        if not scored_tracks:
            return None
        best_similarity, best_track = scored_tracks[0]
        next_best_similarity = scored_tracks[1][0] if len(scored_tracks) > 1 else -1.0
        if (
            best_similarity < self._DORMANT_REID_MIN_SIMILARITY
            or best_similarity - next_best_similarity < self._DORMANT_REID_MIN_LEAD
        ):
            return None
        return best_track

    def _restore_dormant_track(
        self,
        track: Track,
        detection: Detection,
        embedding: PersonEmbedding | None,
    ) -> None:
        self._dormant_tracks.remove(track)
        track.samples.append(
            TrackSample(
                detection.time_seconds,
                detection.box,
                detection.confidence,
                embedding,
            )
        )
        track.missed_frames = 0
        self.tracks.append(track)

    def _motion_compatible(
        self,
        track: Track,
        detection: Detection,
        camera_motion: tuple[float, float, float] | None,
    ) -> bool:
        last = track.last_sample
        elapsed = detection.time_seconds - last.time_seconds
        if elapsed <= 0:
            return False
        expected_center = self._expected_center(track, elapsed, camera_motion)
        detected_center = self._center(detection.box)
        distance = hypot(detected_center[0] - expected_center[0], detected_center[1] - expected_center[1])
        allowance = self.max_motion_distance * max(1.0, elapsed) * (1.0 + 0.25 * track.missed_frames)
        return distance <= allowance or (
            camera_motion is None and last.box.iou(detection.box) >= self.match_iou
        )

    def _expected_center(
        self,
        track: Track,
        elapsed: float,
        camera_motion: tuple[float, float, float] | None,
    ) -> tuple[float, float]:
        last_center = self._center(track.last_sample.box)
        if camera_motion is not None:
            scale, offset_x, offset_y = camera_motion
            return scale * last_center[0] + offset_x, scale * last_center[1] + offset_y
        expected_center = last_center
        if len(track.samples) >= 2:
            previous = track.samples[-2]
            previous_elapsed = track.last_sample.time_seconds - previous.time_seconds
            if previous_elapsed > 0:
                previous_center = self._center(previous.box)
                expected_center = (
                    last_center[0] + (last_center[0] - previous_center[0]) / previous_elapsed * elapsed,
                    last_center[1] + (last_center[1] - previous_center[1]) / previous_elapsed * elapsed,
                )
        return expected_center

    def _association_score(
        self,
        track: Track,
        detection: Detection,
        embedding: PersonEmbedding | None,
        camera_motion: tuple[float, float, float] | None,
    ) -> float:
        motion = self._motion_similarity(track, detection, camera_motion)
        gallery = self._recent_embedding(track)
        if gallery is not None and self._usable_embedding(embedding):
            # Appearance dominates at crossings, while motion gives deterministic
            # ordering when descriptors are equal.
            return 2.0 + cosine_similarity(gallery, embedding) + 0.05 * motion
        return motion

    def _motion_similarity(
        self,
        track: Track,
        detection: Detection,
        camera_motion: tuple[float, float, float] | None,
    ) -> float:
        elapsed = detection.time_seconds - track.last_sample.time_seconds
        last_center = self._expected_center(track, elapsed, camera_motion)
        current_center = self._center(detection.box)
        distance = hypot(current_center[0] - last_center[0], current_center[1] - last_center[1])
        overlap = track.last_sample.box.iou(detection.box) if camera_motion is None else 0.0
        return overlap + max(0.0, 1.0 - distance / self.max_motion_distance)

    def _estimate_camera_motion(
        self,
        detections: tuple[Detection, ...],
    ) -> tuple[float, float, float] | None:
        if len(self.tracks) < 2 or len(detections) != len(self.tracks):
            return None
        previous_centers = tuple(self._center(track.last_sample.box) for track in self.tracks)
        current_centers = tuple(self._center(detection.box) for detection in detections)
        previous_mean = self._mean_center(previous_centers)
        current_mean = self._mean_center(current_centers)
        previous_spread = self._spread(previous_centers, previous_mean)
        current_spread = self._spread(current_centers, current_mean)
        scale = 1.0
        if previous_spread > 1e-6:
            candidate_scale = current_spread / previous_spread
            if 0.75 <= candidate_scale <= 1.33:
                scale = candidate_scale
        return (
            scale,
            current_mean[0] - scale * previous_mean[0],
            current_mean[1] - scale * previous_mean[1],
        )

    @staticmethod
    def _mean_center(centers: Sequence[tuple[float, float]]) -> tuple[float, float]:
        count = len(centers)
        return sum(center[0] for center in centers) / count, sum(center[1] for center in centers) / count

    @staticmethod
    def _spread(centers: Sequence[tuple[float, float]], mean: tuple[float, float]) -> float:
        return sum(hypot(center[0] - mean[0], center[1] - mean[1]) for center in centers) / len(centers)

    def _recent_embedding(self, track: Track) -> PersonEmbedding | None:
        for sample in reversed(track.samples[-6:]):
            if self._usable_embedding(sample.embedding):
                return sample.embedding
        return None

    def _usable_embedding(self, embedding: PersonEmbedding | None) -> bool:
        return embedding is not None and embedding.quality >= self.min_embedding_quality

    @staticmethod
    def _center(box: NormalizedBox) -> tuple[float, float]:
        return box.x + box.width / 2.0, box.y + box.height / 2.0
