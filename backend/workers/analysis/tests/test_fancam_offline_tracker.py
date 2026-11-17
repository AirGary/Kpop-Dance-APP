import importlib
import importlib.util

import numpy as np
import pytest

from stage_lab_analysis.detection import Detection, NormalizedBox
from stage_lab_analysis.reid import PersonEmbedding


def stitch(*args, **kwargs):
    name = 'stage_lab_analysis.fancam_demo.offline_tracker'
    assert importlib.util.find_spec(name) is not None, 'offline trajectories not implemented'
    return importlib.import_module(name).stitch_trajectories(*args, **kwargs)


def observation(t, xs, features=None):
    detections = tuple(Detection(t, NormalizedBox(x, .2, .07, .5), .95) for x in xs)
    return t, detections, tuple(features or [None] * len(xs))


def history_rows(xs=(.32, .30, .40, .38), *, width=.3, height=.6):
    return tuple((i / 10, (Detection(i / 10,
        NormalizedBox(x, .3, width, height), .95),), (None,))
        for i, x in enumerate(xs))


def history_links(rows, cameras=None, *, reverse=False):
    module = importlib.import_module('stage_lab_analysis.fancam_demo.offline_tracker')
    cameras = cameras or ((None,) + ((1., 0., 0.),) * (len(rows) - 1))
    original = (module._directional_links(rows, cameras)
                & module._directional_links(rows, cameras, reverse=True))
    return module._directional_links(rows, cameras, reverse=reverse,
                                     reciprocal_history=frozenset(original))


def test_bounded_history_recovers_endpoint_edge_between_agreeing_anchors():
    rows = history_rows()
    anchors = ({0: rows[0][1][0].box}, {}, {}, {0: rows[3][1][0].box})
    paths, inferred = stitch(rows, anchors, member_count=1,
        camera_transforms=(None,) + ((1., 0., 0.),) * 3)
    assert all(path.get(0) == rows[i][1][0].box for i, path in enumerate(paths))
    assert inferred == (frozenset(), frozenset({0}), frozenset({0}), frozenset())


@pytest.mark.parametrize('reverse', [False, True])
def test_bounded_history_links_endpoints_without_branch_or_skip(reverse):
    links = history_links(history_rows(), reverse=reverse)
    assert links == {((0, 0), (1, 0)), ((1, 0), (2, 0)), ((2, 0), (3, 0))}


def test_bounded_history_cannot_reuse_rescued_node_after_ordinary_link():
    rows = history_rows((.30, .34, .28, .32, .265, .31), width=.05, height=.2)
    links = history_links(rows)
    assert ((1, 0), (2, 0)) in links
    assert ((2, 0), (3, 0)) in links
    assert ((3, 0), (4, 0)) not in links
    # Clean original support after the rejected edge remains usable.
    clean = history_rows((.30, .34, .28, .32, .33, .275), width=.05, height=.2)
    assert ((4, 0), (5, 0)) in history_links(clean)


def test_bounded_history_requires_original_reciprocal_support():
    rows = history_rows((.34, .30, .358, .32), width=.05, height=.2)
    rows = ((0., rows[0][1] + (Detection(0., NormalizedBox(.30, .3, .05, .2), .2),),
             (None, None)),) + rows[1:]
    module = importlib.import_module('stage_lab_analysis.fancam_demo.offline_tracker')
    cameras = (None,) + ((1., 0., 0.),) * 3
    assert ((0, 0), (1, 0)) in module._directional_links(rows, cameras)
    assert ((0, 1), (1, 0)) in module._directional_links(rows, cameras, reverse=True)
    assert ((1, 0), (2, 0)) not in history_links(rows)


@pytest.mark.parametrize('index', [1, 2])
@pytest.mark.parametrize('camera', [None, False])
def test_bounded_history_requires_two_known_camera_transforms(index, camera):
    cameras = [None] + [(1., 0., 0.)] * 3
    cameras[index] = camera
    assert ((1, 0), (2, 0)) not in history_links(history_rows(), tuple(cameras))


@pytest.mark.parametrize('mode', ['confidence', 'size', 'distance', 'appearance'])
def test_bounded_history_preserves_direct_hard_gates(mode):
    rows = list(history_rows())
    t, ds, es = rows[2]
    if mode == 'confidence':
        ds = (Detection(t, ds[0].box, .09),)
    elif mode == 'size':
        ds = (Detection(t, NormalizedBox(.4, .3, .1, .2), .95),)
    elif mode == 'distance':
        ds = (Detection(t, NormalizedBox(.7, .3, .3, .6), .95),)
    else:
        rows = [(time, detections, (PersonEmbedding((1., 0.), 1.),))
                for time, detections, _ in rows]
        es = (PersonEmbedding((0., 1.), 1.),)
    rows[2] = t, ds, es
    assert ((1, 0), (2, 0)) not in history_links(tuple(rows))


def test_bounded_history_keeps_direct_row_and_column_options():
    rows = list(history_rows())
    t, ds, _ = rows[2]
    rows[2] = t, ds + (Detection(t, NormalizedBox(.301, .3, .3, .6), .95),), (None, None)
    links = history_links(tuple(rows))
    assert ((1, 0), (2, 1)) in links
    assert ((1, 0), (2, 0)) not in links


def test_bounded_history_rejects_ambiguous_assignment():
    rows = list(history_rows())
    t, ds, _ = rows[2]
    rows[2] = t, ds * 2, (None, None)
    assert not any(left == (1, 0) for left, _ in history_links(tuple(rows)))


def test_bounded_history_preserves_another_endpoints_direct_column_option():
    rows = list(history_rows())
    t, ds, _ = rows[1]
    rows[1] = t, ds + (Detection(t, NormalizedBox(.41, .3, .3, .6), .95),), (None, None)
    links = history_links(tuple(rows))
    assert ((1, 1), (2, 0)) in links
    assert ((1, 0), (2, 0)) not in links


@pytest.mark.parametrize('step, expected', [(.25, True), (.3, False)])
def test_bounded_history_elapsed_time_is_bounded(step, expected):
    rows = tuple((i * step, tuple(Detection(i * step, d.box, d.confidence) for d in ds), es)
                 for i, (_, ds, es) in enumerate(history_rows((.32, .30, .44, .42))))
    assert (((1, 0), (2, 0)) in history_links(rows)) is expected


def test_bounded_history_cannot_span_a_missing_adjacent_frame():
    rows = history_rows((.32, .30, .35, .42, .40))
    rows = rows[:2] + ((.2, (), ()),) + rows[3:]
    assert ((1, 0), (3, 0)) not in history_links(rows)


def test_bounded_history_one_direction_is_insufficient_for_identity_inference():
    rows = history_rows((.32, .30, .40, .43))
    assert ((1, 0), (2, 0)) in history_links(rows)
    assert ((1, 0), (2, 0)) not in history_links(rows, reverse=True)
    anchors = ({0: rows[0][1][0].box}, {}, {}, {0: rows[3][1][0].box})
    paths, inferred = stitch(rows, anchors, member_count=1,
        camera_transforms=(None,) + ((1., 0., 0.),) * 3)
    assert paths == anchors
    assert not any(inferred)


@pytest.mark.parametrize('reverse', [False, True])
def test_bounded_history_composes_scale_translation_in_traversal_order(reverse, monkeypatch):
    # Apply a different camera transform to each frame of the same local motion.
    cameras = (None, (.9, .08, -.01), (1.1, -.025, .015), (.95, .01, -.005))
    rows = []
    scale, dx, dy = 1., 0., 0.
    for i, (t, ds, es) in enumerate(history_rows()):
        if i:
            s, x, y = cameras[i]
            scale, dx, dy = s * scale, s * dx + x, s * dy + y
        box = ds[0].box
        rows.append((t, (Detection(t, NormalizedBox(scale * box.x + dx,
            scale * box.y + dy, scale * box.width, scale * box.height), .95),), es))
    module = importlib.import_module('stage_lab_analysis.fancam_demo.offline_tracker')
    original_cost = module._association_cost
    projections = []
    source, target = (3, 1) if reverse else (0, 2)

    def capture(old, old_embedding, predicted, detection, embedding, dt):
        if old == rows[source][1][0].box and detection is rows[target][1][0]:
            projections.append(predicted)
        return original_cost(old, old_embedding, predicted, detection, embedding, dt)

    monkeypatch.setattr(module, '_association_cost', capture)
    assert history_links(tuple(rows), cameras, reverse=reverse) == {
        ((0, 0), (1, 0)), ((1, 0), (2, 0)), ((2, 0), (3, 0))}
    box = rows[source][1][0].box
    transforms = (cameras[3], cameras[2]) if reverse else cameras[1:3]
    x, y, width, height = box.x, box.y, box.width, box.height
    for scale, dx, dy in transforms:
        if reverse:
            scale, dx, dy = 1 / scale, -dx / scale, -dy / scale
        x, y, width, height = scale * x + dx, scale * y + dy, scale * width, scale * height
    assert projections
    assert any((p.x, p.y, p.width, p.height) == pytest.approx((x, y, width, height))
               for p in projections)


def test_bounded_history_does_not_clamp_between_camera_transforms():
    rows = history_rows((.62, .70, .70, .68))
    cameras = (None, (1., .15, 0.), (1., -.15, 0.), (1., 0., 0.))
    assert ((1, 0), (2, 0)) in history_links(rows, cameras)
    anchors = ({0: rows[0][1][0].box}, {}, {}, {0: rows[3][1][0].box})
    paths, _ = stitch(rows, anchors, member_count=1, camera_transforms=cameras)
    assert all(path.get(0) == rows[i][1][0].box for i, path in enumerate(paths))


def test_bounded_history_conflicting_anchors_still_reject():
    rows = history_rows()
    anchors = ({0: rows[0][1][0].box}, {}, {}, {1: rows[3][1][0].box})
    paths, inferred = stitch(rows, anchors, member_count=2,
        camera_transforms=(None,) + ((1., 0., 0.),) * 3)
    assert paths == anchors
    assert not any(inferred)


def test_bounded_history_global_same_member_exclusion_still_rejects_span():
    rows = list(history_rows())
    t, ds, _ = rows[1]
    rows[1] = t, ds + (Detection(t, NormalizedBox(.01, .01, .05, .2), .95),), (None, None)
    anchors = ({0: rows[0][1][0].box}, {0: rows[1][1][1].box}, {}, {0: rows[3][1][0].box})
    paths, inferred = stitch(tuple(rows), anchors, member_count=1,
        camera_transforms=(None,) + ((1., 0., 0.),) * 3)
    assert paths == anchors
    assert not any(inferred)


def test_two_sided_five_member_path_recovers_real_detections_without_features():
    observations = tuple(observation(i / 10, [.05, .22 + i * .002, .44, .63, .82])
                         for i in range(21))
    anchors = tuple({m: d.box for m, d in enumerate(row[1])
                     if m != 1 or i in (0, 20)} for i, row in enumerate(observations))
    before = tuple(dict(a) for a in anchors)
    paths, inferred = stitch(observations, anchors, member_count=5)
    assert all(set(p) == set(range(5)) for p in paths)
    assert all(p[1] == observations[i][1][1].box for i, p in enumerate(paths))
    assert inferred == (frozenset(),) + (frozenset({1}),) * 19 + (frozenset(),)
    assert anchors == before  # No identity memory mutation.


def test_conflicting_endpoint_identities_do_not_propagate():
    rows = tuple(observation(i / 10, [.2 + i * .001]) for i in range(5))
    anchors = ({0: rows[0][1][0].box}, {}, {}, {}, {1: rows[-1][1][0].box})
    paths, inferred = stitch(rows, anchors, member_count=2)
    assert paths == anchors
    assert not any(inferred)


def test_weak_detections_extend_anchored_path_but_do_not_become_anchors():
    rows = tuple(observation(i / 10, [.2 + i * .001]) for i in range(5))
    rows = tuple((t, tuple(Detection(t, d.box, .2 if 0 < i < 4 else .95)
                          for d in ds), es) for i, (t, ds, es) in enumerate(rows))
    anchors = ({0: rows[0][1][0].box}, {}, {}, {}, {0: rows[4][1][0].box})
    paths, inferred = stitch(rows, anchors, member_count=1)
    assert all(0 in p for p in paths)
    assert inferred[1:4] == (frozenset({0}),) * 3
    assert anchors[1:4] == ({}, {}, {})


def test_weak_detections_cannot_start_a_path():
    rows = tuple(observation(i / 10, [.2 + i * .001]) for i in range(5))
    rows = tuple((t, tuple(Detection(t, d.box, .2 if i < 2 else .95)
                          for d in ds), es) for i, (t, ds, es) in enumerate(rows))
    anchors = ({}, {}, {0: rows[2][1][0].box}, {}, {0: rows[4][1][0].box})

    paths, inferred = stitch(rows, anchors, member_count=1)

    assert paths[:2] == anchors[:2]
    assert not inferred[0] and not inferred[1]


def test_weak_candidate_cannot_steal_an_equally_plausible_strong_path():
    rows = (observation(0., [.2]), observation(.1, [.201, .199]),
            observation(.2, [.202]))
    rows = (rows[0], (rows[1][0], (
        Detection(.1, rows[1][1][0].box, .2),
        Detection(.1, rows[1][1][1].box, .95)), rows[1][2]), rows[2])
    anchors = ({0: rows[0][1][0].box}, {}, {0: rows[2][1][0].box})

    paths, inferred = stitch(rows, anchors, member_count=1)

    assert paths[1][0] == rows[1][1][1].box
    assert inferred[1] == {0}


def test_future_identity_requires_a_matching_past_anchor():
    rows = tuple(observation(i / 10, [.2]) for i in range(5))
    anchors = ({}, {}, {}, {}, {0: rows[-1][1][0].box})
    paths, inferred = stitch(rows, anchors, member_count=1)
    assert paths == anchors
    assert not any(inferred)


def test_same_identity_elsewhere_rejects_entire_stitch_span():
    rows = tuple(observation(i / 10, [.2, .7]) for i in range(5))
    anchors = ({0: rows[0][1][0].box}, {}, {0: rows[2][1][1].box}, {},
               {0: rows[4][1][0].box})
    paths, inferred = stitch(rows, anchors, member_count=1)
    assert paths == anchors
    assert not any(inferred)


def test_ambiguous_crossing_cannot_join_two_identities():
    rows = (observation(0, [.2, .3]), observation(.4, [.25, .25]),
            observation(.8, [.3, .2]))
    anchors = ({0: rows[0][1][0].box, 1: rows[0][1][1].box}, {},
               {0: rows[2][1][0].box, 1: rows[2][1][1].box})
    paths, inferred = stitch(rows, anchors, member_count=2)
    assert paths[1] == {}
    assert not any(inferred)


def test_long_detector_gap_never_creates_boxes_or_joins_stale_motion():
    rows = (observation(0, [.2]), observation(.1, [.2]), observation(.2, []),
            observation(2, [.2]), observation(2.1, [.2]))
    anchors = ({0: rows[0][1][0].box}, {}, {}, {}, {0: rows[-1][1][0].box})
    paths, inferred = stitch(rows, anchors, member_count=1)
    assert paths == anchors
    assert not any(inferred)


def test_global_camera_pan_is_removed_before_local_path_matching():
    rows = tuple(observation(i / 10, [.05 + .18 * i, .25 + .18 * i, .45 + .18 * i])
                 for i in range(3))
    anchors = ({0: rows[0][1][1].box}, {}, {0: rows[2][1][1].box})

    paths, inferred = stitch(rows, anchors, member_count=1,
                             camera_transforms=(None, (1., .18, 0.), (1., .18, 0.)))

    assert paths[1][0] == rows[1][1][1].box
    assert inferred[1] == {0}


def test_overlapping_large_boxes_can_bridge_agreeing_identity_anchors():
    rows = tuple((i / 10, (Detection(i / 10,
        NormalizedBox(.2 + .08 * i, .2, .3, .6), .95),), (None,))
        for i in range(3))
    anchors = ({0: rows[0][1][0].box}, {}, {0: rows[2][1][0].box})

    paths, inferred = stitch(rows, anchors, member_count=1)

    assert paths[1].get(0) == rows[1][1][0].box
    assert inferred[1] == {0}


def test_far_nonoverlapping_boxes_cannot_jump_even_with_identical_appearance():
    feature = PersonEmbedding((1., 0.), 1.)
    rows = tuple(observation(i / 10, [.2 + .1 * i], [feature]) for i in range(3))
    anchors = ({0: rows[0][1][0].box}, {}, {0: rows[2][1][0].box})

    paths, inferred = stitch(rows, anchors, member_count=1)

    assert paths == anchors
    assert not any(inferred)


@pytest.mark.parametrize('ambiguous', [False, True])
def test_stale_endpoint_does_not_override_recent_continuity(ambiguous):
    positions = [[.2, .4], [.2], [.2], [.28, .281] if ambiguous else [.28], [.3]]
    rows = tuple((i / 10, tuple(Detection(i / 10,
        NormalizedBox(x, .2, .3, .6), .95) for x in xs), (None,) * len(xs))
        for i, xs in enumerate(positions))
    anchors = ({0: rows[0][1][0].box}, {}, {}, {}, {0: rows[-1][1][0].box})

    paths, inferred = stitch(rows, anchors, member_count=1,
        camera_transforms=(None,) + ((1., 0., 0.),) * 4)

    if ambiguous:
        assert paths == anchors
        assert not any(inferred)
    else:
        assert all(path.get(0) == rows[i][1][0].box for i, path in enumerate(paths))
        assert inferred[1:4] == (frozenset({0}),) * 3


def test_scene_cut_does_not_reuse_pre_cut_velocity():
    rows = (observation(0., [.2, .4, .6]),
            observation(.1, [.21, .41, .61]),
            observation(.2, [.01, .41, .81]),
            observation(.3, [.02, .42, .82]))
    anchors = ({0: rows[0][1][1].box}, {}, {}, {0: rows[3][1][1].box})

    paths, inferred = stitch(rows, anchors, member_count=1,
                             camera_transforms=(None, None, False, None))

    assert paths == anchors
    assert not any(inferred)


def test_camera_scale_compensation_keeps_predicted_boxes_normalized():
    def wide(t, xs):
        detections = tuple(Detection(t, NormalizedBox(x, .1, .8, .8), .95) for x in xs)
        return t, detections, (None,) * len(detections)

    rows = (wide(0., [.05, .1, .15]), wide(.1, [.035, .1, .165]))
    anchors = ({0: rows[0][1][1].box}, {0: rows[1][1][1].box})

    paths, inferred = stitch(rows, anchors, member_count=1,
                             camera_transforms=(None, (1.3, 0., 0.)))

    assert paths == anchors
    assert not any(inferred)


def test_frame_camera_transform_measures_background_pan_and_rejects_hard_cut():
    module = importlib.import_module('stage_lab_analysis.fancam_demo.offline_tracker')
    random = np.random.default_rng(7)
    first = random.integers(0, 256, (90, 160), dtype=np.uint8)
    shifted = np.roll(first, 12, axis=1)

    motion = module.frame_camera_transform(first, shifted)

    assert motion[0] == 1.
    assert motion[1] == pytest.approx(12 / 160, abs=.01)
    assert motion[2] == pytest.approx(0., abs=.01)
    assert module.frame_camera_transform(
        np.zeros((90, 160), np.uint8), np.full((90, 160), 255, np.uint8)) is False


def test_short_detector_gap_stitches_only_existing_detection_nodes():
    rows = (observation(0, [.2]), observation(.1, [.201]), observation(.2, []),
            observation(.3, [.203]), observation(.4, [.204]))
    anchors = ({0: rows[0][1][0].box}, {}, {}, {}, {0: rows[-1][1][0].box})
    paths, inferred = stitch(rows, anchors, member_count=1)
    assert paths[2] == {}
    assert inferred[1] == inferred[3] == {0}
    assert paths[3][0] == rows[3][1][0].box


def test_moving_subject_does_not_become_camera_motion():
    module = importlib.import_module('stage_lab_analysis.fancam_demo.offline_tracker')
    random = np.random.default_rng(19)
    first = random.integers(0, 80, (90, 160), dtype=np.uint8)
    subject = random.integers(80, 256, (65, 90), dtype=np.uint8)
    second = first.copy()
    first[10:75, 15:105] = subject
    second[10:75, 35:125] = subject
    before = (NormalizedBox(15/160, 10/90, 90/160, 65/90),)
    after = (NormalizedBox(35/160, 10/90, 90/160, 65/90),)

    assert module.frame_camera_transform(first, second,
        previous_boxes=before, current_boxes=after) in (None, (1., 0., 0.))


def test_reliably_static_background_is_not_missing_motion_evidence():
    module = importlib.import_module('stage_lab_analysis.fancam_demo.offline_tracker')
    frame = np.random.default_rng(7).integers(0, 256, (90, 160), dtype=np.uint8)
    assert module.frame_camera_transform(frame, frame) == (1., 0., 0.)


def test_textureless_background_cannot_supply_camera_translation():
    module = importlib.import_module('stage_lab_analysis.fancam_demo.offline_tracker')
    frame = np.full((90, 160), 90, np.uint8)
    assert module.frame_camera_transform(frame, frame) is None


def test_background_validation_keeps_real_pan_with_people_excluded():
    module = importlib.import_module('stage_lab_analysis.fancam_demo.offline_tracker')
    frame = np.random.default_rng(7).integers(0, 256, (90, 160), dtype=np.uint8)
    motion = module.frame_camera_transform(frame, np.roll(frame, 12, axis=1),
        previous_boxes=(NormalizedBox(.3, .2, .2, .5),),
        current_boxes=(NormalizedBox(.375, .2, .2, .5),))
    assert motion[1] == pytest.approx(12/160, abs=.01)


def test_all_people_no_background_cannot_validate_motion():
    module = importlib.import_module('stage_lab_analysis.fancam_demo.offline_tracker')
    frame = np.random.default_rng(7).integers(0, 256, (90, 160), dtype=np.uint8)
    assert module.frame_camera_transform(frame, np.roll(frame, 12, axis=1),
        previous_boxes=(NormalizedBox(0., 0., 1., 1.),),
        current_boxes=(NormalizedBox(0., 0., 1., 1.),)) is None


def test_incompatible_appearance_cuts_motion_link():
    first = PersonEmbedding((1., 0.), 1.)
    other = PersonEmbedding((0., 1.), 1.)
    rows = (observation(0, [.2], [first]), observation(.1, [.2], [other]),
            observation(.2, [.2], [first]))
    anchors = ({0: rows[0][1][0].box}, {}, {0: rows[2][1][0].box})
    paths, inferred = stitch(rows, anchors, member_count=1)
    assert paths[1] == {}
    assert not any(inferred)


def test_visibility_states_distinguish_partial_occlusion_absence_and_exit():
    module = importlib.import_module('stage_lab_analysis.fancam_demo.offline_tracker')
    rows = (observation(0., [.2]), observation(.1, [.201]), observation(.2, [.7]),
            observation(.3, [.203]), observation(.4, [.93]), observation(.5, []))
    rows = (rows[0], (rows[1][0],
            (Detection(.1, rows[1][1][0].box, .2),), rows[1][2]), *rows[2:])
    paths = ({0: rows[0][1][0].box}, {0: rows[1][1][0].box}, {},
             {0: rows[3][1][0].box}, {0: rows[4][1][0].box}, {})
    inferred = (frozenset(), frozenset({0}), frozenset(),
                frozenset(), frozenset(), frozenset())

    states = module.visibility_states(rows, paths, inferred, member_index=0)

    assert states == ('visible', 'partially_occluded', 'fully_occluded',
                      'visible', 'visible', 'out_of_frame')


def test_unbounded_missing_member_state_remains_unknown():
    module = importlib.import_module('stage_lab_analysis.fancam_demo.offline_tracker')
    rows = (observation(0., []), observation(.1, [.4]))
    states = module.visibility_states(
        rows, ({}, {0: rows[1][1][0].box}), (frozenset(), frozenset()), member_index=0)
    assert states == ('unknown', 'visible')


@pytest.mark.parametrize('invalid', ['count', 'order', 'alignment', 'anchor', 'duplicate'])
def test_invalid_inputs_fail_closed(invalid):
    rows = (observation(0, [.2]), observation(.1, [.21]))
    anchors = ({0: rows[0][1][0].box}, {})
    count = 1
    if invalid == 'count':
        count = True
    elif invalid == 'order':
        rows = (rows[1], rows[0])
    elif invalid == 'alignment':
        anchors = anchors[:1]
    elif invalid == 'anchor':
        anchors = ({0: NormalizedBox(.7, .2, .07, .5)}, {})
    else:
        count = 2
        anchors = ({0: rows[0][1][0].box, 1: rows[0][1][0].box}, {})
    with pytest.raises(ValueError):
        stitch(rows, anchors, member_count=count)
