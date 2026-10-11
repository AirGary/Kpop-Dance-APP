from __future__ import annotations

import math
import random

import pytest

from stage_lab_analysis.fancam_demo import global_clustering
from stage_lab_analysis.fancam_demo.global_clustering import (
    _recompute_normalized_centroids,
    cluster_fixed_group_member_ids,
)
from stage_lab_analysis.reid import PersonEmbedding


def _basis(index: int) -> PersonEmbedding:
    return PersonEmbedding(
        tuple(1.0 if dimension == index else 0.0 for dimension in range(5)),
        quality=1.0,
    )


def _greedy_dead_end_scenes() -> tuple[tuple[PersonEmbedding, ...], ...]:
    randomizer = random.Random(1)
    scenes = []
    for _ in range(3):
        scene = []
        for _ in range(5):
            values = tuple(randomizer.uniform(-1.0, 1.0) for _ in range(4))
            norm = math.sqrt(sum(value * value for value in values))
            scene.append(
                PersonEmbedding(tuple(value / norm for value in values), quality=1.0)
            )
        scenes.append(tuple(scene))
    return tuple(scenes)


def test_greedy_dead_end_uses_complete_seed_for_legal_assignment() -> None:
    result = cluster_fixed_group_member_ids(_greedy_dead_end_scenes())

    assert {member_id for scene in result for member_id in scene} == {
        f"member-{member_index:02d}" for member_index in range(1, 6)
    }
    assert all(len(scene) == len(set(scene)) for scene in result)


def test_fewer_person_scene_uses_distinct_optimal_member_subset() -> None:
    result = cluster_fixed_group_member_ids(
        (
            tuple(_basis(index) for index in range(5)),
            (_basis(4), _basis(1)),
        )
    )

    assert result == (
        ("member-01", "member-02", "member-03", "member-04", "member-05"),
        ("member-05", "member-02"),
    )


def test_same_scene_lookalikes_remain_distinct() -> None:
    norm = math.sqrt(0.99 * 0.99 + 0.1 * 0.1)
    lookalike = PersonEmbedding(
        (0.99 / norm, 0.1 / norm, 0.0, 0.0, 0.0), quality=0.8
    )
    result = cluster_fixed_group_member_ids(
        (tuple(_basis(index) for index in range(5)), (lookalike, lookalike))
    )

    assert len(set(result[1])) == 2


def test_rejects_empty_scene_embeddings() -> None:
    with pytest.raises(ValueError, match="at least one scene is required"):
        cluster_fixed_group_member_ids(())


def test_equal_score_repeated_runs_are_identical() -> None:
    repeated = PersonEmbedding((1.0, 0.0, 0.0, 0.0, 0.0), quality=1.0)
    scenes = ((repeated,) * 5, (repeated,) * 3)

    expected = (
        ("member-01", "member-02", "member-03", "member-04", "member-05"),
        ("member-01", "member-02", "member-03"),
    )

    assert cluster_fixed_group_member_ids(scenes) == expected
    assert cluster_fixed_group_member_ids(scenes) == expected


def test_equal_objective_prefers_earlier_seed() -> None:
    scenes = (
        tuple(_basis(index) for index in range(5)),
        tuple(_basis(index) for index in reversed(range(5))),
    )

    assert cluster_fixed_group_member_ids(scenes) == (
        ("member-01", "member-02", "member-03", "member-04", "member-05"),
        ("member-05", "member-04", "member-03", "member-02", "member-01"),
    )


def test_rejects_more_than_five_detections_in_a_scene() -> None:
    with pytest.raises(ValueError, match="at most 5 detections"):
        cluster_fixed_group_member_ids(
            (tuple(_basis(index % 5) for index in range(6)),)
        )


def test_dimension_mismatch_is_rejected_before_any_candidate_runs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mismatched = PersonEmbedding((1.0, 0.0), quality=1.0)

    def unexpected_candidate(*_args: object) -> None:
        raise AssertionError("candidate convergence must not run")

    monkeypatch.setattr(global_clustering, "_converge_candidate", unexpected_candidate)

    with pytest.raises(ValueError, match="embedding dimensions must match"):
        cluster_fixed_group_member_ids(
            ((mismatched, _basis(1), _basis(2), _basis(3), _basis(4)),)
        )


def test_candidate_zero_norm_is_rejected_and_later_seed_can_succeed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scenes = (
        tuple(_basis(index) for index in range(5)),
        tuple(_basis(index) for index in range(5)),
    )
    successful = (((0, 1, 2, 3, 4), (0, 1, 2, 3, 4)), scenes[1])
    calls = 0

    def converge(*_args: object):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise global_clustering._CandidateRejected("centroid norm must be non-zero")
        return successful

    monkeypatch.setattr(global_clustering, "_converge_candidate", converge)

    assert cluster_fixed_group_member_ids(scenes) == (
        ("member-01", "member-02", "member-03", "member-04", "member-05"),
        ("member-01", "member-02", "member-03", "member-04", "member-05"),
    )
    assert calls == 2


def test_zero_norm_centroid_rejects_only_the_candidate() -> None:
    positive = PersonEmbedding((1.0, 0.0), quality=1.0)
    negative = PersonEmbedding((-1.0, 0.0), quality=1.0)
    scenes = ((positive,), (negative,))

    with pytest.raises(global_clustering._CandidateRejected, match="non-zero"):
        _recompute_normalized_centroids(scenes, ((0,), (0,)), 1)


def test_empty_member_centroid_guard_rejects_only_the_candidate() -> None:
    with pytest.raises(global_clustering._CandidateRejected, match="empty member"):
        _recompute_normalized_centroids(((_basis(0),),), ((0,),), 2)


def test_rejects_when_all_candidates_fail_to_converge(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(global_clustering, "_MAX_CONVERGENCE_ITERATIONS", 0)

    with pytest.raises(ValueError, match="no candidate converged"):
        cluster_fixed_group_member_ids((tuple(_basis(index) for index in range(5)),))


def test_rejects_when_no_complete_seed_scene_exists() -> None:
    with pytest.raises(ValueError, match="complete seed"):
        cluster_fixed_group_member_ids(
            (
                (_basis(0), _basis(1), _basis(2)),
                (_basis(3), _basis(4)),
            )
        )


def test_defaults_to_a_fixed_five_member_group() -> None:
    scene = (
        _basis(0),
        _basis(1),
        _basis(2),
        _basis(3),
        _basis(4),
    )

    result = cluster_fixed_group_member_ids((scene,))

    assert result == (("member-01", "member-02", "member-03", "member-04", "member-05"),)


def test_rejects_fewer_total_detections_than_fixed_member_count() -> None:
    with pytest.raises(ValueError, match="at least 5 detections are required"):
        cluster_fixed_group_member_ids(
            (
                (
                    _basis(0),
                    _basis(1),
                    _basis(2),
                    _basis(3),
                ),
            )
        )


@pytest.mark.parametrize("member_count", (0, 4, 6))
def test_rejects_invalid_member_count(member_count: int) -> None:
    with pytest.raises(ValueError, match="member_count must be 5"):
        cluster_fixed_group_member_ids(
            (tuple(_basis(index) for index in range(5)),),
            member_count=member_count,
        )
