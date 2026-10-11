import pytest
import numpy as np
from stage_lab_analysis.detection import Detection, NormalizedBox
from stage_lab_analysis.fancam_demo.preview import analyze_samples


class Detector:
    def detect(self, frame):
        return tuple(Detection(0, NormalizedBox(x, .2, .1, .6), .9) for x in frame)


class Embedder:
    def embed(self, frame, box):
        return None


def test_recovery_callback_only_emits_confirmed_detection_not_pose_bounds():
    from stage_lab_analysis.reid import PersonEmbedding
    from stage_lab_analysis.pose import PoseFrame, PoseKeypoint
    class Identity:
        def embed(self, frame, box):
            return PersonEmbedding((1., 0.), 1.)
    class Pose:
        def estimate(self, frame, box, time_seconds):
            return PoseFrame(time_seconds, box, (PoseKeypoint('left_heel', .15, .84, .9),), .9)
    events = []
    samples, metrics = analyze_samples(
        iter(((0., [.1]), (.1, []), (.2, [.1]), (.3, [.1]), (.4, [.1]))),
        Detector(), Identity(), member_count=1, member_index=0,
        strict_reentry=True, separate_identity=True, pose_estimator=Pose(),
        on_reacquired=lambda t,b: events.append((t,b)))
    assert events == [(.4, NormalizedBox(.1, .2, .1, .6))]
    assert samples[-1][1].height == pytest.approx(.64)
    assert metrics['reacquisitions'] == 1
    assert samples[2][1] is samples[3][1] is None


def test_pose_expands_selected_geometry_and_reports_observation_count():
    from stage_lab_analysis.pose import PoseFrame, PoseKeypoint
    class Pose:
        def estimate(self, frame, box, time_seconds):
            return PoseFrame(time_seconds, box, (PoseKeypoint('left_heel', .15, .84, .9),), .9)
    samples, metrics = analyze_samples(iter(((0., [.1]), (.2, []))),
        Detector(), Embedder(), member_count=1, member_index=0, pose_estimator=Pose(),
        strict_reentry=True)
    assert samples[0][1].y+samples[0][1].height == pytest.approx(.84)
    assert samples[1][1] is None
    assert metrics['poseSamples'] == 1
    assert metrics['fullBodyVerified'] is False


def test_preview_keeps_samples_and_counts_fallback_without_user_prompts():
    samples, metrics = analyze_samples(iter(((0., [.1, .6]), (.2, [.11, .59]), (.4, [.12]))), Detector(), Embedder(), member_count=2, member_index=1)
    assert len(samples) == 3
    assert samples[0][1].x == .6
    assert samples[-1][1] is None
    assert metrics['trackedSamples'] == 2
    assert metrics['fallbackSamples'] == 1
    assert metrics['reviewPrompts'] == 0
    assert metrics['identityAccuracy'] is None


def test_offline_stitching_replays_only_new_pose_bounds_and_keeps_inference_separate():
    from stage_lab_analysis.reid import PersonEmbedding
    from stage_lab_analysis.pose import PoseFrame, PoseKeypoint
    class Identity:
        def embed(self, frame, box):
            return None if .101 < box.x < .117 else PersonEmbedding((1., 0.), 1.)
    class Pose:
        def __init__(self):
            self.times = []
        def estimate(self, frame, box, time_seconds):
            self.times.append(time_seconds)
            return PoseFrame(time_seconds, box, (PoseKeypoint('left_heel', box[0], .84, .9),), .9)
    frames = tuple((i / 10, [.1 + i * .002]) for i in range(15))
    events, inferred = [], []
    pose = Pose()
    samples, metrics = analyze_samples(iter(frames), Detector(), Identity(),
        member_count=1, member_index=0, pose_estimator=pose,
        offline_trajectories=True, replay_frames=lambda: iter(frames),
        on_inferred=inferred.append, on_reacquired=lambda t, b: events.append((t, b)))
    assert all(box is not None for _, box in samples)
    assert all(box.y + box.height == pytest.approx(.84) for _, box in samples)
    assert inferred == [i / 10 for i in range(1, 11)]
    assert sorted(pose.times) == [i / 10 for i in range(15)]
    assert [t for t, _ in events] == [1.1]
    assert events[0][1].height == .6
    assert metrics['identityObservedSamples'] == 5
    assert metrics['trajectoryInferredSamples'] == 10
    assert metrics['visibilityStateCounts'] == {
        'visible': 5, 'partially_occluded': 10,
        'fully_occluded': 0, 'out_of_frame': 0, 'unknown': 0}
    assert metrics['identityAccuracy'] is None


def test_offline_pose_requires_replay_before_consuming_source():
    with pytest.raises(ValueError, match='replay'):
        analyze_samples(iter(()), Detector(), Embedder(), member_count=1, member_index=0,
                        offline_trajectories=True, pose_estimator=object())


def test_offline_weak_detections_never_enter_identity_tracker(monkeypatch):
    from stage_lab_analysis.fancam_demo import preview
    calls = []

    class Tracker:
        reacquired = set()
        def __init__(self, *_args, **_kwargs):
            pass
        def update(self, _timestamp, detections, _embeddings):
            calls.append(tuple(d.confidence for d in detections))
            return {0: detections[0].box} if detections else {}

    class MixedDetector:
        def detect(self, frame):
            return tuple(Detection(0, NormalizedBox(x, .2, .1, .6), confidence)
                         for x, confidence in frame)

    monkeypatch.setattr(preview, 'ContinuousMemberTracker', Tracker)
    preview.analyze_samples(iter(((0., ((.2, .95), (.5, .2))),
                                   (.1, ((.21, .9), (.49, .1))))),
                            MixedDetector(), Embedder(), member_count=1, member_index=0,
                            offline_trajectories=True)

    assert calls == [(0.95,), (0.9,)]


def test_offline_tracker_receives_frame_based_camera_motion(monkeypatch):
    from stage_lab_analysis.fancam_demo import offline_tracker, preview
    captured = []
    first = np.random.default_rng(3).integers(0, 256, (90, 160, 3), dtype=np.uint8)
    second = np.roll(first, 8, axis=1)

    def stitch(observations, anchors, **options):
        captured.extend(options['camera_transforms'])
        return tuple(anchors), tuple(frozenset() for _ in anchors)

    class StaticDetector:
        def detect(self, _frame):
            return (Detection(0, NormalizedBox(.2, .2, .1, .6), .9),)

    monkeypatch.setattr(offline_tracker, 'stitch_trajectories', stitch)
    _, metrics = preview.analyze_samples(
        iter(((0., first), (.1, second))), StaticDetector(), Embedder(),
        member_count=1, member_index=0, offline_trajectories=True)

    assert captured[0] is None
    assert captured[1][1] == pytest.approx(8 / 160, abs=.01)
    assert metrics['cameraMotionSamples'] == 1
    assert metrics['sceneCutSamples'] == 0


def test_cli_passes_offline_inference_and_hold_policy(monkeypatch, tmp_path, capsys):
    import json
    import sys
    from stage_lab_analysis.fancam_demo import preview_cli, preview_render
    from stage_lab_analysis.reid import PersonEmbedding
    class Identity:
        def embed(self, frame, box):
            return None if .101 < box.x < .117 else PersonEmbedding((1., 0.), 1.)
    frames = tuple((i / 10, [.1 + i * .002]) for i in range(15))
    component_options = []
    monkeypatch.setattr(preview_cli, '_components',
                        lambda root, **options: (component_options.append(options) or
                                                 (Detector(), Identity())))
    monkeypatch.setattr(preview_cli, 'native_samples', lambda *args: iter(frames))
    calls = []
    def render(source, output, samples, **kwargs):
        calls.append((samples, kwargs))
        return {'preview_only': True}
    monkeypatch.setattr(preview_render, 'render_preview', render)
    monkeypatch.setattr(sys, 'argv', ['preview', '--source', str(tmp_path / 'source.mp4'),
        '--output', str(tmp_path / 'new.mp4'), '--members', '1', '--member', 'A',
        '--offline-trajectories', '--absence-hold-seconds', '0.3'])
    preview_cli.main()
    samples, options = calls[0]
    assert all(box is not None for _, box in samples)
    assert options['missing_policy'] == 'hold'
    assert options['hold_seconds'] == .3
    assert options['inferred_times'] == {i / 10 for i in range(1, 11)}
    assert json.loads(capsys.readouterr().out)['trajectoryInferredSamples'] == 10
    assert component_options == [{'detector_threshold': .1}]
