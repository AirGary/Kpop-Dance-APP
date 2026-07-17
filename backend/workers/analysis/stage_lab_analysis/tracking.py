from __future__ import annotations

from dataclasses import dataclass, field

from .detection import Detection, NormalizedBox


@dataclass(frozen=True, slots=True)
class TrackSample:
    time_seconds: float
    box: NormalizedBox
    confidence: float


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
        self._next_track_id = 1

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
        self.tracks = [track for track in self.tracks if track.missed_frames <= self.max_missed_frames]
        return tuple(sorted(self.tracks, key=lambda track: track.track_id))
