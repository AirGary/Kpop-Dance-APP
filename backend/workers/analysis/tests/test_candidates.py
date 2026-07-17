from __future__ import annotations

from stage_lab_analysis.candidates import CandidateExtractor
from stage_lab_analysis.detection import Detection
from stage_lab_analysis.tracking import ByteTrackPersonTracker, NormalizedBox


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
