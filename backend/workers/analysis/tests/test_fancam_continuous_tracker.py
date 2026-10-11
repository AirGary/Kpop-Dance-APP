import math

import pytest

from stage_lab_analysis.detection import Detection, NormalizedBox
from stage_lab_analysis.reid import PersonEmbedding
from stage_lab_analysis.fancam_demo.continuous_tracker import ContinuousMemberTracker


def det(x):
    return Detection(0, NormalizedBox(x, .3, .08, .5), .95)


def emb(i):
    return PersonEmbedding(tuple(float(j == i) for j in range(5)), 1.)


def partial_emb(similarity):
    return PersonEmbedding((similarity, 0., math.sqrt(1-similarity**2), 0., 0.), 1.)


def test_separated_motion_does_not_change_trusted_identity():
    tracker = ContinuousMemberTracker(1, strict_reentry=True, separate_identity=True)
    tracker.update(0., (det(.3),), (emb(0),))
    assert tracker.update(.1, (det(.31),), (None,)) == {}
    track = tracker.tracks[0]
    assert track.box == det(.3).box
    assert track.timestamp == 0.
    assert track.gallery == [emb(0)]
    assert track.motion_box == det(.31).box


def test_second_row_recovery_requires_three_clean_identity_observations():
    tracker = ContinuousMemberTracker(2, strict_reentry=True, separate_identity=True)
    tracker.update(0., (det(.3), det(.6)), (emb(0), emb(1)))
    assert 0 not in tracker.update(.1, (det(.31), det(.33)), (None, None))
    for t in (.2, .3):
        assert 0 not in tracker.update(t, (det(.32), det(.6)), (emb(0), emb(1)))
        assert tracker.reacquired == set()
    assert tracker.update(.4, (det(.32), det(.6)), (emb(0), emb(1)))[0] == det(.32).box
    assert 0 in tracker.reacquired


def test_missing_initial_template_needs_consistent_bootstrap():
    tracker = ContinuousMemberTracker(1, strict_reentry=True, separate_identity=True)
    assert tracker.update(0., (det(.3),), (None,)) == {}
    for t in (.1, .2):
        assert tracker.update(t, (det(.3),), (emb(0),)) == {}
        assert tracker.tracks[0].gallery == []
    assert tracker.update(.3, (det(.3),), (emb(0),)) == {0: det(.3).box}


def test_distinctive_overlapping_observation_tracks_without_template_learning():
    tracker = ContinuousMemberTracker(2, strict_reentry=True, separate_identity=True)
    tracker.update(0., (det(.3), det(.6)), (emb(0), emb(1)))
    before = tuple(tracker.tracks[0].gallery)
    result = tracker.update(.1, (det(.31), det(.33)), (emb(0), emb(1)))
    assert result[0] == det(.31).box
    assert tuple(tracker.tracks[0].gallery) == before
    assert tracker.reacquired == set()


def test_overlapping_recovery_never_becomes_a_mask_prompt():
    tracker = ContinuousMemberTracker(2, strict_reentry=True, separate_identity=True)
    tracker.update(0., (det(.3), det(.6)), (emb(0), emb(1)))
    tracker.update(.1, (), ())
    for t in (.2, .3):
        assert 0 not in tracker.update(t, (det(.31), det(.33)), (emb(0), emb(1)))
    assert 0 in tracker.update(.4, (det(.31), det(.33)), (emb(0), emb(1)))
    assert tracker.reacquired == set()
    assert tracker.tracks[0].gallery == [emb(0)]
    tracker.update(.5, (det(.31), det(.6)), (emb(0), emb(1)))
    assert 0 in tracker.reacquired


def test_overlap_cannot_bootstrap_identity_without_an_anchor():
    tracker = ContinuousMemberTracker(2, strict_reentry=True, separate_identity=True)
    tracker.update(0., (det(.3), det(.32)), (emb(0), emb(1)))
    for t in (.1, .2, .3, .4):
        assert tracker.update(t, (det(.3), det(.32)), (emb(0), emb(1))) == {}
    assert all(not track.gallery for track in tracker.tracks)


def test_provisional_motion_survives_without_refreshing_trusted_clock():
    tracker = ContinuousMemberTracker(1, strict_reentry=True, separate_identity=True)
    tracker.update(0., (det(.3),), (None,))
    for i in range(1, 12):
        assert tracker.update(i/10, (det(.3),), (None,)) == {}
    assert tracker.tracks[0].timestamp == 0.
    assert tracker.tracks[0].motion_timestamp == 1.1
    for t in (1.2, 1.3):
        assert tracker.update(t, (det(.3),), (emb(0),)) == {}
    assert 0 in tracker.update(1.4, (det(.3),), (emb(0),))


def test_short_motion_cannot_override_clear_other_member_appearance():
    tracker = ContinuousMemberTracker(2, strict_reentry=True)
    other = partial_emb(.4)
    tracker.update(0., (det(.3), det(.7)), (emb(0), other))
    before = tuple(tracker.tracks[0].gallery)
    # The other member enters the stale location; position alone looks perfect.
    result = tracker.update(.1, (det(.3),), (other,))
    assert 0 not in result
    assert tracker.tracks[0].timestamp == 0.
    assert tuple(tracker.tracks[0].gallery) == before


def test_close_member_appearance_is_not_a_clear_conflict():
    tracker = ContinuousMemberTracker(2, strict_reentry=True)
    similar = partial_emb(.96)
    tracker.update(0., (det(.3), det(.7)), (emb(0), similar))
    assert 0 in tracker.update(.1, (det(.3),), (similar,))


def test_short_motion_rejects_distinctive_competitor_below_exact_match():
    tracker = ContinuousMemberTracker(2, strict_reentry=True)
    tracker.update(0., (det(.3), det(.7)), (emb(0), emb(1)))
    # Real switch at 123.407s: own=.363, competitor=.748, not >=.9.
    candidate = PersonEmbedding((.363, .748, math.sqrt(1-.363**2-.748**2), 0., 0.), .1)
    before = tuple(tracker.tracks[0].gallery)
    assert 0 not in tracker.update(.1, (det(.3),), (candidate,))
    assert tuple(tracker.tracks[0].gallery) == before


def test_overlap_freezes_gallery_even_when_association_is_clear():
    tracker = ContinuousMemberTracker(2)
    tracker.update(0, (det(.3), det(.4)), (emb(0), emb(1)))
    before = [tuple(t.gallery) for t in tracker.tracks]
    result = tracker.update(.2, (det(.34), det(.36)), (emb(0), emb(1)))
    assert set(result) == {0, 1}
    assert [tuple(t.gallery) for t in tracker.tracks] == before


def test_motion_match_cannot_teach_gallery_a_more_likely_competing_identity():
    tracker = ContinuousMemberTracker(2, strict_reentry=True)
    tracker.update(0., (det(.3), det(.7)), (emb(0), emb(1)))
    # At 70.404s the crop passes quality checks, but own=.395 and B=.645.
    # A provisional motion association must not become identity evidence.
    candidate = PersonEmbedding((.395, .645, math.sqrt(1-.395**2-.645**2), 0., 0.), .1)
    before = tuple(tracker.tracks[0].gallery)
    tracker.update(.1, (det(.3),), (candidate,))
    assert tuple(tracker.tracks[0].gallery) == before


def test_low_quality_embedding_does_not_update_gallery():
    tracker = ContinuousMemberTracker(1)
    tracker.update(0, (det(.3),), (emb(0),))
    tracker.update(.2, (det(.31),), (PersonEmbedding(emb(0).values, .01),))
    assert tracker.tracks[0].gallery == [emb(0)]


def test_valid_reid_quality_uses_embedder_contract_not_probability_threshold():
    tracker = ContinuousMemberTracker(1)
    descriptor = PersonEmbedding(emb(0).values, .1)
    tracker.update(0, (det(.3),), (descriptor,))
    assert tracker.tracks[0].gallery == [descriptor]
    tracker.update(.2, (det(.31),), (descriptor,))
    assert len(tracker.tracks[0].gallery) == 2


def test_strict_reentry_requires_three_observations_even_for_exact_appearance():
    tracker = ContinuousMemberTracker(1, strict_reentry=True)
    tracker.update(0, (det(.3),), (emb(0),))
    assert tracker.update(4, (det(.7),), (emb(0),)) == {}
    assert tracker.update(4.1, (det(.71),), (emb(0),)) == {}
    assert tracker.tracks[0].timestamp == 0
    assert tracker.update(4.2, (det(.72),), (emb(0),)) == {0: det(.72).box}


def test_strict_reentry_preserves_strong_appearance_lead_rule():
    tracker = ContinuousMemberTracker(2, strict_reentry=True)
    tracker.update(0, (det(.1), det(.3)), (emb(0), partial_emb(.85)))
    assert tracker.update(4., (det(.7),), (emb(0),)) == {}
    assert tracker.update(4.1, (det(.71),), (emb(0),)) == {}
    assert tracker.update(4.2, (det(.72),), (emb(0),)) == {0: det(.72).box}


def test_overlapping_initial_crops_are_not_identity_templates():
    tracker = ContinuousMemberTracker(2)
    tracker.update(0, (det(.3), det(.32)), (emb(0), emb(1)))
    assert all(not t.gallery for t in tracker.tracks)


def test_strict_reentry_cannot_accumulate_contaminated_crops():
    tracker = ContinuousMemberTracker(2, strict_reentry=True)
    tracker.update(0, (det(.1), det(.3)), (emb(0), emb(1)))
    for t in (4., 4.1, 4.2, 4.3):
        assert tracker.update(t, (det(.7), det(.72)), (emb(0), emb(1))) == {}
    assert tracker.tracks[0].timestamp == 0


def test_initializes_once_left_to_right_and_ignores_detector_order():
    tracker = ContinuousMemberTracker(5)
    positions = [.1, .25, .4, .55, .7]
    first = tracker.update(0, tuple(det(x) for x in positions), tuple(emb(i) for i in range(5)))
    assert len(first) == 5
    second = tracker.update(.2, tuple(det(x+.01) for x in reversed(positions)), tuple(emb(i) for i in reversed(range(5))))
    assert second[1].x == pytest.approx(.26)
    assert len(second) == 5


def test_missing_features_do_not_break_clear_short_motion():
    tracker = ContinuousMemberTracker(2)
    tracker.update(0, (det(.1), det(.7)), (emb(0), emb(1)))
    result = tracker.update(.2, (det(.11), det(.69)), (None, None))
    assert set(result) == {0, 1}


def test_missing_person_does_not_force_other_person_to_drop():
    tracker = ContinuousMemberTracker(2)
    tracker.update(0, (det(.1), det(.7)), (emb(0), emb(1)))
    result = tracker.update(.2, (det(.11),), (emb(0),))
    assert set(result) == {0}


def test_appearance_preserves_crossing_identity():
    tracker = ContinuousMemberTracker(2)
    tracker.update(0, (det(.3), det(.5)), (emb(0), emb(1)))
    tracker.update(.2, (det(.34), det(.46)), (emb(0), emb(1)))
    result = tracker.update(.4, (det(.40), det(.39)), (emb(1), emb(0)))
    assert result[0].x == pytest.approx(.39)
    assert result[1].x == pytest.approx(.40)


def test_far_unknown_does_not_replace_missing_member():
    tracker = ContinuousMemberTracker(2)
    tracker.update(0, (det(.1), det(.3)), (emb(0), emb(1)))
    assert tracker.update(.2, (det(.8),), (emb(2),)) == {}


def test_ambiguous_identical_candidates_are_unassigned():
    tracker = ContinuousMemberTracker(2)
    tracker.update(0, (det(.3), det(.5)), (emb(0), emb(0)))
    assert tracker.update(.2, (det(.4), det(.4)), (emb(0), emb(0))) == {}


def test_does_not_seed_incomplete_scene_or_exceed_configured_members():
    tracker = ContinuousMemberTracker(2)
    assert tracker.update(0, (det(.1),), (emb(0),)) == {}
    assert len(tracker.update(.2, (det(.1), det(.4), det(.7)), (emb(0), emb(1), emb(2)))) == 2


def test_rejects_non_increasing_timestamps():
    tracker = ContinuousMemberTracker(1)
    tracker.update(0, (det(.1),), (emb(0),))
    with pytest.raises(ValueError):
        tracker.update(0, (det(.1),), (emb(0),))


def test_long_occlusion_recovers_only_with_distinctive_appearance():
    tracker = ContinuousMemberTracker(2)
    tracker.update(0, (det(.1), det(.3)), (emb(0), emb(1)))
    tracker.update(1, (), ())
    result = tracker.update(4, (det(.7), det(.8)), (emb(1), emb(0)))
    assert result[0].x == pytest.approx(.8)
    assert result[1].x == pytest.approx(.7)


def test_long_occlusion_cannot_recover_from_identical_appearance():
    tracker = ContinuousMemberTracker(2)
    tracker.update(0, (det(.1), det(.3)), (emb(0), emb(0)))
    assert tracker.update(4, (det(.7), det(.8)), (emb(0), emb(0))) == {}


def test_long_occlusion_requires_three_consistent_distinctive_observations_for_relaxed_reentry():
    tracker = ContinuousMemberTracker(2)
    tracker.update(0, (det(.1), det(.3)), (emb(0), emb(1)))
    candidate = partial_emb(.72)

    assert tracker.update(4., (det(.70),), (candidate,)) == {}
    assert tracker.update(4.2, (det(.71),), (candidate,)) == {}
    assert tracker.tracks[0].timestamp == 0
    assert tracker.update(4.4, (det(.72),), (candidate,)) == {0: det(.72).box}


@pytest.mark.parametrize("width_ratio,height_ratio", [
    (1., 1.758), (1., .594), (1.758, 1.), (.594, 1.),
])
def test_featureless_abrupt_size_change_does_not_mutate_track(width_ratio, height_ratio):
    tracker = ContinuousMemberTracker(1)
    tracker.update(0, (Detection(0, NormalizedBox(.3, .3, .1, .4), .95),), (emb(0),))
    tracker.update(1/6, (Detection(0, NormalizedBox(.305, .3, .1, .4), .95),), (emb(0),))
    track = tracker.tracks[0]
    before = (track.box, track.timestamp, track.velocity, tuple(track.gallery))
    predicted = track.predict(2/6)
    width, height = track.box.width*width_ratio, track.box.height*height_ratio
    wrong = NormalizedBox(predicted.x+(predicted.width-width)/2,
                          predicted.y+(predicted.height-height)/2, width, height)

    result = tracker.update(2/6, (Detection(0, wrong, .95),), (None,))

    assert (track.box, track.timestamp, track.velocity, tuple(track.gallery)) == before
    assert result == {}
    # The next consistent observation can still use the last trusted state.
    recovered = tracker.update(3/6, (Detection(0, track.predict(3/6), .95),), (None,))
    assert set(recovered) == {0}


def test_featureless_partial_body_with_center_jump_does_not_mutate_track():
    tracker = ContinuousMemberTracker(1)
    tracker.update(0, (Detection(0, NormalizedBox(.3, .27, .1, .7), .95),), (emb(0),))
    tracker.update(1/6, (Detection(0, NormalizedBox(.3, .20, .1, .7), .95),), (emb(0),))
    track = tracker.tracks[0]
    before = (track.box, track.timestamp, track.velocity, tuple(track.gallery))
    height = track.box.height*.594
    wrong = NormalizedBox(.3, track.box.y+track.box.height/2-.171-height/2, .1, height)
    # Existing velocity makes this .171 jump pass the old center-distance gate.
    result = tracker.update(.5, (Detection(0, wrong, .95),), (None,))

    assert (track.box, track.timestamp, track.velocity, tuple(track.gallery)) == before
    assert result == {}


@pytest.mark.parametrize("seed_embedding", [None, emb(0)])
def test_featureless_short_motion_allows_modest_size_change(seed_embedding):
    tracker = ContinuousMemberTracker(1)
    tracker.update(0, (Detection(0, NormalizedBox(.3, .3, .1, .4), .95),), (seed_embedding,))
    resized = NormalizedBox(.305, .28, .11, .44)
    assert tracker.update(1/6, (Detection(0, resized, .95),), (None,)) == {0: resized}


@pytest.mark.parametrize("gap", [.2, 1., 4.])
def test_distinctive_appearance_allows_size_change_including_long_gap(gap):
    tracker = ContinuousMemberTracker(1)
    tracker.update(0, (Detection(0, NormalizedBox(.3, .3, .1, .4), .95),), (emb(0),))
    resized = NormalizedBox(.25, .1, .2, .8)
    assert tracker.update(gap, (Detection(0, resized, .95),), (emb(0),)) == {0: resized}
