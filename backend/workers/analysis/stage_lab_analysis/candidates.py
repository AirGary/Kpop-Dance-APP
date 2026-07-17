from __future__ import annotations

from dataclasses import dataclass
from statistics import median
from typing import Callable

from .tracking import Track


@dataclass(frozen=True, slots=True)
class Candidate:
    candidate_id: str
    track_id: int
    representative_image_paths: tuple[str, str, str]
    appearance_intervals: tuple[tuple[float, float], ...]
    box_summary: object
    confidence: float


@dataclass(frozen=True, slots=True)
class CandidateSet:
    candidates: tuple[Candidate, ...]


def _box_summary(track: Track):
    from .detection import NormalizedBox

    return NormalizedBox(
        x=median(sample.box.x for sample in track.samples),
        y=median(sample.box.y for sample in track.samples),
        width=median(sample.box.width for sample in track.samples),
        height=median(sample.box.height for sample in track.samples),
    )


class CandidateExtractor:
    def __init__(self, *, min_visible_seconds: float = 1.0) -> None:
        if min_visible_seconds <= 0:
            raise ValueError("minimum visible duration must be positive")
        self.min_visible_seconds = min_visible_seconds

    def extract(
        self,
        tracks: list[Track] | tuple[Track, ...],
        *,
        representative_path: Callable[[int, int], str],
    ) -> CandidateSet:
        accepted = [
            track
            for track in tracks
            if track.samples[-1].time_seconds - track.samples[0].time_seconds >= self.min_visible_seconds
        ]
        ranked = sorted(accepted, key=self._rank_key, reverse=True)
        candidates: list[Candidate] = []
        for index, track in enumerate(ranked, start=1):
            samples = track.samples
            duration = samples[-1].time_seconds - samples[0].time_seconds
            mean_confidence = sum(sample.confidence for sample in samples) / len(samples)
            stability = 1.0 / (1.0 + self._movement(samples))
            confidence = max(0.0, min(1.0, 0.65 * mean_confidence + 0.35 * stability))
            candidates.append(
                Candidate(
                    candidate_id=f"candidate-{index}",
                    track_id=track.track_id,
                    representative_image_paths=tuple(
                        representative_path(track.track_id, image_index) for image_index in range(1, 4)
                    ),
                    appearance_intervals=((samples[0].time_seconds, samples[-1].time_seconds),),
                    box_summary=_box_summary(track),
                    confidence=confidence,
                )
            )
        return CandidateSet(tuple(candidates))

    @staticmethod
    def _movement(samples) -> float:
        return sum(
            abs(current.box.x - previous.box.x) + abs(current.box.y - previous.box.y)
            for previous, current in zip(samples, samples[1:])
        ) / max(1, len(samples) - 1)

    @staticmethod
    def _rank_key(track: Track) -> tuple[float, float, float, float]:
        samples = track.samples
        duration = samples[-1].time_seconds - samples[0].time_seconds
        area = median(sample.box.area for sample in samples)
        full_body = median(min(1.0, sample.box.height / max(sample.box.width, 0.01)) for sample in samples)
        stability = 1.0 / (1.0 + CandidateExtractor._movement(samples))
        return duration, area, full_body, stability
