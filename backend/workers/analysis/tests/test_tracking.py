from __future__ import annotations

from stage_lab_analysis.detection import Detection
from stage_lab_analysis.tracking import ByteTrackPersonTracker, NormalizedBox


def detection(time: float, x: float, confidence: float = 0.9) -> Detection:
    return Detection(
        time_seconds=time,
        box=NormalizedBox(x=x, y=0.2, width=0.2, height=0.6),
        confidence=confidence,
    )


def test_tracker_keeps_identity_across_short_occlusion() -> None:
    tracker = ByteTrackPersonTracker(max_missed_frames=2, match_iou=0.2)

    first = tracker.update((detection(0.0, 0.1), detection(0.0, 0.7)))
    tracker.update((detection(1.0, 0.13), detection(1.0, 0.68)))
    tracker.update(())
    recovered = tracker.update((detection(3.0, 0.16), detection(3.0, 0.65)))

    assert len(first) == 2
    assert {track.track_id for track in recovered} == {
        track.track_id for track in first
    }
    assert all(
        [sample.time_seconds for sample in track.samples]
        == sorted(sample.time_seconds for sample in track.samples)
        for track in tracker.tracks
    )


def test_tracker_assigns_each_detection_to_at_most_one_track() -> None:
    tracker = ByteTrackPersonTracker(match_iou=0.1)
    tracker.update((detection(0.0, 0.1), detection(0.0, 0.5)))

    tracks = tracker.update((detection(1.0, 0.12), detection(1.0, 0.52)))

    assert len(tracks) == 2
    assert len({track.samples[-1].box for track in tracks}) == 2


def test_normalized_box_rejects_invalid_coordinates() -> None:
    try:
        NormalizedBox(x=0.9, y=0.1, width=0.2, height=0.2)
    except ValueError as error:
        assert "normalized" in str(error)
    else:
        raise AssertionError("invalid normalized box was accepted")
