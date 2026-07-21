from stage_lab_analysis.pose import PoseFrame, PoseKeypoint
from stage_lab_analysis.timeline import build_practice_timeline


def pose(time_seconds: float, x: float) -> PoseFrame:
    return PoseFrame(
        time_seconds=time_seconds,
        box=(x, 0.1, 0.2, 0.7),
        keypoints=(PoseKeypoint("hip", x + 0.1, 0.5, 0.9),),
        confidence=0.9,
    )


def test_timeline_explains_fast_displacement_and_snaps_to_nearby_beat():
    timeline = build_practice_timeline(
        [pose(0, 0.1), pose(1.0, 0.3), pose(2.0, 0.8)],
        beats=(0.0, 1.02, 2.01),
    )

    assert timeline
    assert timeline[0].start_seconds == 0.0
    assert timeline[-1].end_seconds <= 8.0
    assert any(reason.code == "displacement" for reason in timeline[0].reasons)


def test_similar_motion_segments_share_repeat_group():
    first = [pose(0, 0.1), pose(1, 0.2), pose(2, 0.1)]
    second = [pose(4, 0.1), pose(5, 0.2), pose(6, 0.1)]

    timeline = build_practice_timeline(first + second)

    groups = {segment.repeat_group_id for segment in timeline if segment.repeat_group_id}
    assert groups
    assert sum(segment.repeat_group_id is not None for segment in timeline) >= 2
