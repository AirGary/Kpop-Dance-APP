import math

import pytest

from stage_lab_analysis.pose import (
    COCO_WHOLEBODY_KEYPOINT_NAMES,
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


def test_coco_wholebody_names_preserve_all_133_documented_landmarks():
    """WholeBody result serialization must never fall back to anonymous joints."""
    assert len(COCO_WHOLEBODY_KEYPOINT_NAMES) == 133
    assert COCO_WHOLEBODY_KEYPOINT_NAMES[:17] == (
        "nose", "left_eye", "right_eye", "left_ear", "right_ear",
        "left_shoulder", "right_shoulder", "left_elbow", "right_elbow",
        "left_wrist", "right_wrist", "left_hip", "right_hip",
        "left_knee", "right_knee", "left_ankle", "right_ankle",
    )
    assert COCO_WHOLEBODY_KEYPOINT_NAMES[17:23] == (
        "left_big_toe", "left_small_toe", "left_heel",
        "right_big_toe", "right_small_toe", "right_heel",
    )
    assert COCO_WHOLEBODY_KEYPOINT_NAMES[23] == "face-0"
    assert COCO_WHOLEBODY_KEYPOINT_NAMES[90] == "face-67"
    assert COCO_WHOLEBODY_KEYPOINT_NAMES[91] == "left_hand_root"
    assert COCO_WHOLEBODY_KEYPOINT_NAMES[112] == "right_hand_root"
    assert COCO_WHOLEBODY_KEYPOINT_NAMES[-1] == "right_pinky_finger4"
