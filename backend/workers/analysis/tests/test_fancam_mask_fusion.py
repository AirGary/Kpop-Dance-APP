from stage_lab_analysis.detection import NormalizedBox
from stage_lab_analysis.fancam_demo.mask_fusion import validated_body_box


def test_partial_mask_does_not_remove_detected_feet():
    body = NormalizedBox(.3, .2, .1, .6)
    mask = NormalizedBox(.31, .21, .08, .3)
    assert validated_body_box(mask, body) == body


def test_full_frame_mask_cannot_expand_trusted_detection():
    body = NormalizedBox(.3, .2, .1, .6)
    assert validated_body_box(NormalizedBox(0, 0, 1, 1), body) == body


def test_mask_alone_is_not_identity_evidence():
    assert validated_body_box(NormalizedBox(.3, .2, .1, .6), None) is None


def test_compatible_mask_preserves_outside_head_and_feet():
    body = NormalizedBox(.3, .2, .1, .6)
    mask = NormalizedBox(.3, .19, .1, .62)
    result = validated_body_box(mask, body)
    assert result.y == .19
    assert result.y + result.height >= .81


def test_wrong_person_mask_is_ignored():
    body = NormalizedBox(.3, .2, .1, .6)
    assert validated_body_box(NormalizedBox(.7, .2, .1, .6), body) == body


def test_missing_mask_keeps_identity_detection():
    body = NormalizedBox(.3, .2, .1, .6)
    assert validated_body_box(None, body) == body


def continuity():
    from stage_lab_analysis.fancam_demo import mask_fusion
    assert hasattr(mask_fusion, 'MaskContinuity'), 'bounded mask continuity missing'
    return mask_fusion.MaskContinuity()


def test_mask_continuity_requires_trusted_anchor():
    fusion = continuity()
    body = NormalizedBox(.3, .2, .1, .6)
    assert fusion.update(0., body, None) == (None, False)
    assert fusion.update(.1, body, body) == (body, False)
    shifted = NormalizedBox(.31, .2, .1, .6)
    result, inferred = fusion.update(.2, shifted, None)
    assert inferred and abs(result.x-.31) < 1e-9
    assert result.height == body.height


def test_propagation_does_not_extend_identity_deadline():
    fusion = continuity()
    body = NormalizedBox(.3, .2, .1, .6)
    fusion.update(0., body, body)
    for i in range(1, 11):
        assert fusion.update(i/10, body, None)[1]
    assert fusion.update(1.1, body, None) == (None, False)


def test_bad_mask_breaks_chain_until_identity_revalidates():
    for bad in (None, NormalizedBox(0, 0, 1, 1), NormalizedBox(.7, .2, .1, .6)):
        fusion = continuity()
        body = NormalizedBox(.3, .2, .1, .6)
        fusion.update(0., body, body)
        assert fusion.update(.1, bad, None) == (None, False)
        assert fusion.update(.2, body, None) == (None, False)
        assert fusion.update(.3, body, body) == (body, False)
        assert fusion.update(.4, body, None)[1]


def test_mismatched_identity_mask_cannot_seed_continuity():
    fusion = continuity()
    body = NormalizedBox(.3, .2, .1, .6)
    wrong = NormalizedBox(.7, .2, .1, .6)
    assert fusion.update(0., wrong, body) == (body, False)
    assert fusion.update(.1, wrong, None) == (None, False)


def test_sparse_mask_and_partial_body_are_not_followed():
    for time, mask in ((.4, NormalizedBox(.3, .2, .1, .6)),
                       (.1, NormalizedBox(.3, .2, .1, .2))):
        fusion = continuity()
        body = NormalizedBox(.3, .2, .1, .6)
        fusion.update(0., body, body)
        assert fusion.update(time, mask, None) == (None, False)
