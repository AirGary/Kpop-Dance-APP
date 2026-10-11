from __future__ import annotations

import json
from pathlib import Path

import pytest

from stage_lab_analysis.fancam_demo.evaluate import evaluate_membership
from stage_lab_analysis.fancam_demo.truth import (
    GroundTruthScene,
    GroundTruthSet,
    PersonAssignment,
    SceneObservation,
    load_ground_truth,
)


def _truth(visible_member_ids: tuple[str, ...] = ("member-01",)) -> GroundTruthSet:
    return GroundTruthSet(
        tuple(
            GroundTruthScene(float(timestamp), visible_member_ids)
            for timestamp in range(30)
        )
    )


def test_ground_truth_scene_rejects_duplicate_member_ids() -> None:
    with pytest.raises(ValueError):
        GroundTruthScene(0.0, ("member-01", "member-01"))


def test_truth_rejects_runtime_candidate_id() -> None:
    with pytest.raises(ValueError, match="stable anonymous"):
        GroundTruthScene(0.0, ("candidate-01",))


def test_person_assignment_rejects_non_stable_member_ids() -> None:
    with pytest.raises(ValueError, match="stable anonymous"):
        PersonAssignment("runtime-a", "candidate-01", True, False)


def test_scene_observation_rejects_duplicate_runtime_candidates() -> None:
    with pytest.raises(ValueError, match="runtime candidate IDs"):
        SceneObservation(
            0.0,
            (
                PersonAssignment("runtime-a", "member-01", True, False),
                PersonAssignment("runtime-a", "member-02", True, False),
            ),
        )


def test_ground_truth_set_requires_between_30_and_50_scenes() -> None:
    with pytest.raises(ValueError):
        GroundTruthSet(
            tuple(GroundTruthScene(float(index), ("member-01",)) for index in range(29))
        )


def test_evaluator_counts_a_missing_scene_observation_as_missed_detection() -> None:
    truth = _truth()
    observations = tuple(
        SceneObservation(
            float(timestamp),
            (PersonAssignment(f"runtime-{timestamp}", "member-01", True, False),),
        )
        for timestamp in range(29)
    )

    result = evaluate_membership(truth, observations)

    assert result.detection_recall == pytest.approx(29 / 30)
    assert result.identity_accuracy == 1.0


def test_evaluator_calculates_detection_recall_for_visible_members() -> None:
    truth = _truth(("member-01", "member-02"))
    observations = tuple(
        SceneObservation(
            float(timestamp),
            (
                (
                    PersonAssignment("runtime-a", "member-01", True, False),
                    PersonAssignment("runtime-b", "member-02", True, False),
                )
                if timestamp < 15
                else (PersonAssignment("runtime-a", "member-01", True, False),)
            ),
        )
        for timestamp in range(30)
    )

    result = evaluate_membership(truth, observations)

    assert result.detection_recall == pytest.approx(45 / 60)


def test_evaluator_counts_wrong_identity_as_a_false_lock() -> None:
    result = evaluate_membership(
        _truth(("member-01",)),
        (
            SceneObservation(
                0.0,
                (PersonAssignment("runtime-a", "member-02", True, False),),
            ),
        ),
    )

    assert result.false_locks == 1
    assert result.identity_accuracy == 0.0


def test_evaluation_counts_unconfirmed_assignments_as_confirmations_only() -> None:
    result = evaluate_membership(
        _truth(("member-01",)),
        (
            SceneObservation(
                0.0,
                (PersonAssignment("runtime-a", "member-99", False, False),),
            ),
        ),
    )

    assert result.confirmation_requests == 1
    assert result.identity_accuracy is None
    assert result.false_locks == 0


def test_evaluation_counts_a_confirmed_runtime_identity_change_as_an_id_switch() -> None:
    result = evaluate_membership(
        _truth(("member-01", "member-02")),
        (
            SceneObservation(
                0.0,
                (PersonAssignment("runtime-a", "member-01", True, False),),
            ),
            SceneObservation(
                1.0,
                (PersonAssignment("runtime-a", "member-02", True, False),),
            ),
        ),
    )

    assert result.id_switches == 1


def test_evaluation_counts_a_stable_member_reassigned_to_a_runtime_candidate_as_an_id_switch() -> None:
    result = evaluate_membership(
        _truth(),
        (
            SceneObservation(
                0.0,
                (PersonAssignment("runtime-a", "member-01", True, False),),
            ),
            SceneObservation(
                1.0,
                (PersonAssignment("runtime-b", "member-01", True, False),),
            ),
        ),
    )

    assert result.id_switches == 1


def test_evaluation_requires_an_exact_truth_scene_timestamp() -> None:
    result = evaluate_membership(
        _truth(),
        (
            SceneObservation(
                0.0005,
                (PersonAssignment("runtime-a", "member-01", True, False),),
            ),
        ),
    )

    assert result.detection_recall == 0.0


def test_evaluation_counts_one_wrong_person_in_a_multi_person_scene_as_false_lock() -> None:
    result = evaluate_membership(
        _truth(("member-01", "member-02")),
        (
            SceneObservation(
                0.0,
                (
                    PersonAssignment("runtime-a", "member-01", True, False),
                    PersonAssignment("runtime-b", "member-99", True, False),
                ),
            ),
        ),
    )

    assert result.false_locks == 1


def test_ground_truth_loader_rejects_source_path_fields(tmp_path: Path) -> None:
    path = tmp_path / "fancam-demo-ground-truth.local.json"
    path.write_text(
        json.dumps(
            {
                "schemaVersion": 1,
                "sourcePath": "/private/video.mp4",
                "scenes": [],
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError):
        load_ground_truth(path)
