from __future__ import annotations

from dataclasses import dataclass
from statistics import median
from typing import Callable

from .identity import IdentityCluster
from .tracking import Track


@dataclass(frozen=True, slots=True)
class Candidate:
    candidate_id: str
    fragment_ids: tuple[int, ...]
    representative_image_paths: tuple[str, str, str]
    appearance_intervals: tuple[tuple[float, float], ...]
    box_summary: object
    confidence: float

    @property
    def primary_fragment_id(self) -> int:
        """Representative fragment used only by the legacy non-cluster fallback."""
        return self.fragment_ids[0]


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
                    fragment_ids=(track.track_id,),
                    representative_image_paths=tuple(
                        representative_path(track.track_id, image_index) for image_index in range(1, 4)
                    ),
                    appearance_intervals=((samples[0].time_seconds, samples[-1].time_seconds),),
                    box_summary=_box_summary(track),
                    confidence=confidence,
                )
            )
        return CandidateSet(tuple(candidates))

    def extract_clusters(
        self,
        clusters: tuple[IdentityCluster, ...],
        *,
        representative_path: Callable[[int, int], str],
        maximum_candidates: int = 8,
    ) -> CandidateSet:
        if maximum_candidates <= 0:
            raise ValueError("maximum candidates must be positive")
        accepted = [
            cluster
            for cluster in clusters
            if self._cluster_duration(cluster) >= self.min_visible_seconds
        ]
        ranked = sorted(accepted, key=self._cluster_rank_key, reverse=True)[:maximum_candidates]
        candidates: list[Candidate] = []
        for index, cluster in enumerate(ranked, start=1):
            tracks = tuple(fragment.track for fragment in cluster.fragments)
            samples = tuple(sample for track in tracks for sample in track.samples)
            mean_confidence = sum(sample.confidence for sample in samples) / len(samples)
            stability = 1.0 / (1.0 + self._movement(samples))
            confidence = max(0.0, min(1.0, 0.65 * mean_confidence + 0.35 * stability))
            candidates.append(
                Candidate(
                    candidate_id=f"candidate-{index}",
                    fragment_ids=cluster.fragment_ids,
                    representative_image_paths=tuple(
                        representative_path(cluster.cluster_id, image_index)
                        for image_index in range(1, 4)
                    ),
                    appearance_intervals=tuple(
                        (fragment.start_seconds, fragment.end_seconds)
                        for fragment in cluster.fragments
                    ),
                    box_summary=self._cluster_box_summary(tracks),
                    confidence=confidence,
                )
            )
        return CandidateSet(tuple(candidates))

    @staticmethod
    def _cluster_duration(cluster: IdentityCluster) -> float:
        return sum(fragment.end_seconds - fragment.start_seconds for fragment in cluster.fragments)

    @staticmethod
    def _cluster_box_summary(tracks: tuple[Track, ...]):
        from .detection import NormalizedBox

        samples = tuple(sample for track in tracks for sample in track.samples)
        return NormalizedBox(
            x=median(sample.box.x for sample in samples),
            y=median(sample.box.y for sample in samples),
            width=median(sample.box.width for sample in samples),
            height=median(sample.box.height for sample in samples),
        )

    @staticmethod
    def _cluster_rank_key(cluster: IdentityCluster) -> tuple[float, float, float]:
        tracks = tuple(fragment.track for fragment in cluster.fragments)
        samples = tuple(sample for track in tracks for sample in track.samples)
        duration = CandidateExtractor._cluster_duration(cluster)
        area = median(sample.box.area for sample in samples)
        stability = 1.0 / (1.0 + CandidateExtractor._movement(samples))
        return duration, area, stability

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
