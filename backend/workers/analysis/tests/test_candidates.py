from __future__ import annotations

from stage_lab_analysis.candidates import CandidateExtractor
from stage_lab_analysis.detection import Detection
from stage_lab_analysis.identity import IdentityCluster, TrackDescriptor, TrackFragment
from stage_lab_analysis.tracking import ByteTrackPersonTracker, NormalizedBox, Track, TrackSample


def test_candidate_ranking_is_deterministic_and_rejects_short_tracks() -> None:
    tracker = ByteTrackPersonTracker(match_iou=0.1)
    for time in range(5):
        detections = [
            Detection(time, NormalizedBox(0.1, 0.1, 0.25, 0.75), 0.95)
        ]
        if time == 0:
            detections.append(Detection(time, NormalizedBox(0.6, 0.2, 0.1, 0.2), 0.99))
        tracker.update(tuple(detections))

    candidates = CandidateExtractor(min_visible_seconds=2.0).extract(
        tracker.tracks,
        representative_path=lambda track_id, index: f"analysis/candidates/{track_id}-{index}.jpg",
    )

    assert [candidate.candidate_id for candidate in candidates.candidates] == [
        "candidate-1"
    ]
    assert len(candidates.candidates[0].representative_image_paths) == 3
    assert candidates.candidates[0].confidence > 0.0


def test_candidate_summary_uses_normalized_boxes_and_intervals() -> None:
    tracker = ByteTrackPersonTracker(match_iou=0.1)
    tracker.update((Detection(0.0, NormalizedBox(0.2, 0.1, 0.3, 0.7), 0.8),))
    tracker.update((Detection(2.0, NormalizedBox(0.25, 0.1, 0.3, 0.7), 0.9),))

    candidate = CandidateExtractor(min_visible_seconds=1.0).extract(
        tracker.tracks,
        representative_path=lambda track_id, index: f"candidate-{index}.jpg",
    ).candidates[0]

    assert candidate.box_summary.x == 0.225
    assert candidate.appearance_intervals == ((0.0, 2.0),)


def test_cluster_candidates_combine_fragments_and_limit_the_list_to_eight() -> None:
    descriptor = TrackDescriptor(
        hsv_histogram=(0.2, 0.3, 0.5),
        edge_density=0.2,
        shoulder_to_hip_ratio=None,
        torso_to_height_ratio=None,
        pose_quality=0,
        start_center=(0.2, 0.4),
        end_center=(0.2, 0.4),
        velocity=(0, 0),
    )

    def track(track_id: int, start: float, end: float) -> Track:
        return Track(
            track_id,
            [
                TrackSample(start, NormalizedBox(0.1, 0.1, 0.25, 0.75), 0.95),
                TrackSample(end, NormalizedBox(0.1, 0.1, 0.25, 0.75), 0.95),
            ],
        )

    first = TrackFragment(1, track(1, 0, 5), descriptor)
    second = TrackFragment(2, track(2, 6, 10), descriptor)
    extra = tuple(
        IdentityCluster(index + 2, (TrackFragment(index + 2, track(index + 2, 20 + index, 22 + index), descriptor),))
        for index in range(8)
    )
    clusters = (IdentityCluster(1, (first, second)), *extra)

    candidates = CandidateExtractor(min_visible_seconds=1).extract_clusters(
        clusters,
        representative_path=lambda cluster_id, index: f"analysis/candidates/{cluster_id}-{index}.jpg",
    )

    assert len(candidates.candidates) == 8
    assert candidates.candidates[0].fragment_ids == (1, 2)
    assert candidates.candidates[0].primary_fragment_id == 1
    assert candidates.candidates[0].appearance_intervals == ((0.0, 5.0), (6.0, 10.0))
    assert candidates.candidates[0].representative_image_paths == (
        "analysis/candidates/1-1.jpg",
        "analysis/candidates/1-2.jpg",
        "analysis/candidates/1-3.jpg",
    )
