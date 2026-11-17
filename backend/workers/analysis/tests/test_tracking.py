from __future__ import annotations

from math import sqrt

from stage_lab_analysis.detection import Detection
from stage_lab_analysis.reid import PersonEmbedding
from stage_lab_analysis.tracking import (
    AppearanceAwarePersonTracker,
    ByteTrackPersonTracker,
    NormalizedBox,
)


def detection(time: float, x: float, confidence: float = 0.9) -> Detection:
    return Detection(
        time_seconds=time,
        box=NormalizedBox(x=x, y=0.2, width=0.2, height=0.6),
        confidence=confidence,
    )


def embedding(similarity_to_first: float, *, quality: float = 0.9) -> PersonEmbedding:
    return PersonEmbedding(
        (similarity_to_first, sqrt(1.0 - similarity_to_first * similarity_to_first)),
        quality,
    )


def test_appearance_tracker_keeps_ids_through_a_crossing_when_boxes_overlap() -> None:
    first_identity = embedding(1.0)
    second_identity = embedding(0.0)
    tracker = AppearanceAwarePersonTracker(match_iou=0.1)

    initial = tracker.update(
        (detection(0.0, 0.10), detection(0.0, 0.55)),
        (first_identity, second_identity),
    )
    tracker.update(
        # The detector reports the second dancer first at the overlapping crossing.
        (detection(1.0, 0.35), detection(1.0, 0.30)),
        (second_identity, first_identity),
    )
    recovered = tracker.update(
        (detection(2.0, 0.10), detection(2.0, 0.55)),
        (second_identity, first_identity),
    )

    by_initial_identity = {track.samples[0].embedding: track.track_id for track in initial}
    assert {
        track.track_id: track.last_sample.embedding
        for track in recovered
    } == {
        by_initial_identity[first_identity]: first_identity,
        by_initial_identity[second_identity]: second_identity,
    }


def test_appearance_tracker_recovers_a_short_occlusion_without_splitting_identity() -> None:
    first_identity = embedding(1.0)
    second_identity = embedding(0.0)
    tracker = AppearanceAwarePersonTracker(max_missed_frames=2, match_iou=0.1)

    initial = tracker.update(
        (detection(0.0, 0.10), detection(0.0, 0.55)),
        (first_identity, second_identity),
    )
    tracker.update(
        (detection(1.0, 0.20), detection(1.0, 0.45)),
        (first_identity, second_identity),
    )
    tracker.update((), ())
    recovered = tracker.update(
        (detection(3.0, 0.35), detection(3.0, 0.30)),
        (first_identity, second_identity),
    )

    assert {track.track_id for track in recovered} == {track.track_id for track in initial}
    assert all(len(track.samples) == 3 for track in recovered)


def test_appearance_tracker_compensates_a_shared_camera_pan() -> None:
    first_identity = embedding(1.0)
    second_identity = embedding(0.0)
    tracker = AppearanceAwarePersonTracker(max_motion_distance=0.1)

    initial = tracker.update(
        (detection(0.0, 0.05), detection(0.0, 0.30)),
        (first_identity, second_identity),
    )
    recovered = tracker.update(
        # Both dancers retain their world positions; the camera pans right.
        (detection(1.0, 0.45), detection(1.0, 0.70)),
        (first_identity, second_identity),
    )

    assert {track.track_id for track in recovered} == {track.track_id for track in initial}
    assert len(tracker.all_tracks) == 2


def test_reconnects_a_short_occlusion_only_with_an_unambiguous_high_quality_embedding() -> None:
    tracker = AppearanceAwarePersonTracker(max_missed_frames=0)

    tracker.update((detection(0.0, 0.2),), (embedding(1.0),), allow_dormant_reid=True)
    tracker.update((), (), allow_dormant_reid=True)
    tracks = tracker.update(
        (detection(1.0, 0.7),),
        (embedding(1.0),),
        allow_dormant_reid=True,
    )

    assert [track.track_id for track in tracks] == [1]


def test_ambiguous_dormant_embeddings_start_a_new_track() -> None:
    tracker = AppearanceAwarePersonTracker(max_missed_frames=0)
    first_identity = embedding(1.0)
    nearly_identical_identity = embedding(0.95)

    tracker.update(
        (detection(0.0, 0.05), detection(0.0, 0.6)),
        (first_identity, nearly_identical_identity),
        allow_dormant_reid=True,
    )
    tracker.update((), (), allow_dormant_reid=True)
    tracks = tracker.update(
        (detection(1.0, 0.35),),
        (first_identity,),
        allow_dormant_reid=True,
    )

    assert [track.track_id for track in tracks] == [3]


def test_dormant_track_returning_after_three_seconds_starts_a_new_track() -> None:
    tracker = AppearanceAwarePersonTracker(max_missed_frames=0)

    tracker.update((detection(0.0, 0.2),), (embedding(1.0),), allow_dormant_reid=True)
    tracker.update((), (), allow_dormant_reid=True)
    tracks = tracker.update(
        (detection(3.01, 0.7),),
        (embedding(1.0),),
        allow_dormant_reid=True,
    )

    assert [track.track_id for track in tracks] == [2]


def test_detection_time_purge_completes_a_dormant_track_exactly_once() -> None:
    tracker = AppearanceAwarePersonTracker(max_missed_frames=0)

    tracker.update((detection(0.0, 0.2),), (embedding(1.0),), allow_dormant_reid=True)
    tracker.update((), (), allow_dormant_reid=True)
    tracker.update(
        (detection(3.01, 0.7),),
        (embedding(1.0),),
        allow_dormant_reid=True,
    )

    assert [track.track_id for track in tracker.completed_tracks] == [1]
    assert [track.track_id for track in tracker.all_tracks] == [1, 2]


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


def test_tracker_retains_finished_tracks_for_later_candidate_extraction() -> None:
    tracker = ByteTrackPersonTracker(max_missed_frames=0, match_iou=0.1)
    tracker.update((detection(0.0, 0.1),))
    tracker.update((detection(1.0, 0.12),))
    tracker.update(())

    assert tracker.tracks == []
    assert len(tracker.all_tracks) == 1
    assert [sample.time_seconds for sample in tracker.all_tracks[0].samples] == [0.0, 1.0]


def test_normalized_box_rejects_invalid_coordinates() -> None:
    try:
        NormalizedBox(x=0.9, y=0.1, width=0.2, height=0.2)
    except ValueError as error:
        assert "normalized" in str(error)
    else:
        raise AssertionError("invalid normalized box was accepted")
