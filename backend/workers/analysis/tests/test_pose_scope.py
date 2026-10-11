import pytest
from stage_lab_analysis.pose import RTMPoseEstimator


def test_pose_restores_detector_scope_even_after_lazy_initialization(monkeypatch):
    registry = pytest.importorskip('mmengine.registry')
    registry.init_default_scope('mmdet')
    estimator = RTMPoseEstimator(config='unused', checkpoint='unused', expected_sha256='unused')
    def estimate(*args):
        registry.init_default_scope('mmpose')
        return 'pose'
    monkeypatch.setattr(estimator, '_estimate', estimate)
    assert estimator.estimate(None, (.1, .1, .2, .5), 0) == 'pose'
    assert registry.DefaultScope.get_current_instance().scope_name == 'mmdet'
