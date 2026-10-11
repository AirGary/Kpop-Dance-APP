import pytest
from stage_lab_analysis.detection import NormalizedBox
from stage_lab_analysis.pose import PoseKeypoint
from stage_lab_analysis.fancam_demo import body_bounds


def test_visible_head_and_feet_extend_not_shrink_box():
    box = NormalizedBox(.3, .2, .2, .6)
    points = (PoseKeypoint('nose', .4, .18, .9),
              PoseKeypoint('left_heel', .4, .84, .9))
    result = body_bounds.visible_body_box(box, points)
    assert result.y == pytest.approx(.18)
    assert result.y+result.height == pytest.approx(.84)
    assert result.x == .3
    assert result.width == pytest.approx(.2)


def test_unreliable_or_remote_points_cannot_move_camera():
    box = NormalizedBox(.3, .2, .2, .6)
    points = (PoseKeypoint('left_heel', .4, .85, .1),
              PoseKeypoint('nose', .95, .1, .99))
    assert body_bounds.visible_body_box(box, points) == box


def test_missing_keypoints_preserve_detection_without_inventing_feet():
    box = NormalizedBox(.3, .2, .2, .6)
    assert body_bounds.visible_body_box(box, ()) == box
