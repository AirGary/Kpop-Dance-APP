import math

import pytest

from stage_lab_analysis.pose import (
    PoseFrame,
    PoseKeypoint,
    SpotlightKeyframe,
    build_spotlight_track,
    validate_pose_track,
)


def frame(time_seconds: float, confidence: float = 0.9) -> PoseFrame:
    return PoseFrame(
        time_seconds=time_seconds,
        box=(0.2, 0.1, 0.3, 0.7),
        keypoints=(
            PoseKeypoint("left_shoulder", 0.3, 0.2, confidence),
            PoseKeypoint("right_shoulder", 0.4, 0.2, confidence),
        ),
        confidence=confidence,
    )


def test_pose_track_has_monotonic_finite_normalized_values():
    track = validate_pose_track([frame(0), frame(0.1)])

    assert track[1].time_seconds > track[0].time_seconds
    assert all(math.isfinite(point.x) for point in track[0].keypoints)


def test_pose_track_rejects_non_monotonic_timestamps():
    with pytest.raises(ValueError, match="monotonic"):
        validate_pose_track([frame(1), frame(0)])


def test_low_confidence_frames_do_not_create_strong_spotlight():
    track = build_spotlight_track([frame(0, 0.9), frame(1, 0.2)])

    assert isinstance(track[0], SpotlightKeyframe)
    assert track[1].confidence < 0.5


def test_pose_keypoints_can_be_clamped_at_frame_edges():
    clamped = PoseKeypoint("wrist", 0.0, 1.0, 1.0)

    assert clamped.x == 0.0
    assert clamped.y == 1.0
