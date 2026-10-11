from __future__ import annotations

import json
import math
from pathlib import Path

import pytest

from stage_lab_analysis.fancam_demo.proposal import (
    CandidateRegistry,
    ProposalScene,
    ProposalSet,
    accepted_truth,
    apply_acceptance,
    load_proposal,
    load_local_proposal,
    propose_scene,
)
from stage_lab_analysis.detection import Detection, NormalizedBox
from stage_lab_analysis.reid import PersonEmbedding


def embedding(values: tuple[float, ...]) -> PersonEmbedding:
    norm = math.sqrt(sum(value * value for value in values))
    return PersonEmbedding(tuple(value / norm for value in values), quality=1.0)


def detection() -> Detection:
    return Detection(
        time_seconds=0.0,
        box=NormalizedBox(0.1, 0.1, 0.2, 0.2),
        confidence=1.0,
    )


def _proposal(count: int = 30, confidence: str = "high") -> ProposalSet:
    return ProposalSet(
        tuple(
            ProposalScene(float(index), ("candidate-01",), confidence)
            for index in range(count)
        )
    )


def test_proposal_loader_rejects_private_or_visual_fields(tmp_path: Path) -> None:
    path = tmp_path / "fancam-demo-ground-truth.proposed.local.json"
    path.write_text(
        json.dumps({
            "schemaVersion": 1,
            "sourcePath": "/private/video.mp4",
            "scenes": [],
        }),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="unsupported fields"):
        load_proposal(path)


def test_acceptance_refuses_unaccepted_review_scene_as_truth() -> None:
    proposal = _proposal(confidence="review")

    with pytest.raises(ValueError, match="accepted"):
        accepted_truth(proposal, {"candidate-01": "member-01"})


def test_accepted_truth_requires_a_mapping_for_every_candidate() -> None:
    accepted_proposal = apply_acceptance(
        ProposalSet(
            tuple(
                ProposalScene(
                    float(index),
                    ("candidate-01", "candidate-02") if index == 0 else ("candidate-01",),
                    "high",
                )
                for index in range(30)
            )
        ),
        accept_high=True,
        accept_review_timestamps=(),
    )

    with pytest.raises(ValueError, match="missing stable mapping"):
        accepted_truth(accepted_proposal, {"candidate-01": "member-01"})


@pytest.mark.parametrize(
    "mapping, message",
    (
        ({"candidate-01": "member-01", "candidate-02": "member-01"}, "unique"),
        ({"candidate-01": "candidate-01", "candidate-02": "member-02"}, "stable anonymous"),
        ({"candidate-01": "member-01", "candidate-02": "member-02", "candidate-03": "member-03"}, "unknown"),
    ),
)
def test_accepted_truth_rejects_invalid_stable_mapping(
    mapping: dict[str, str], message: str
) -> None:
    accepted_proposal = apply_acceptance(
        ProposalSet(
            tuple(
                ProposalScene(
                    float(index),
                    ("candidate-01", "candidate-02"),
                    "high",
                )
                for index in range(30)
            )
        ),
        accept_high=True,
        accept_review_timestamps=(),
    )

    with pytest.raises(ValueError, match=message):
        accepted_truth(accepted_proposal, mapping)


def test_proposal_set_requires_between_30_and_50_strictly_increasing_scenes() -> None:
    with pytest.raises(ValueError):
        _proposal(29)
    with pytest.raises(ValueError):
        _proposal(51)
    with pytest.raises(ValueError):
        ProposalSet(tuple(ProposalScene(1.0, ("candidate-01",), "high") for _ in range(30)))


def test_proposal_scene_rejects_non_opaque_candidate_ids() -> None:
    for candidate_id in (
        "Lisa",
        "/private/crop.jpg",
        "frame-01.jpg",
        "candidate-1",
        "candidate-00",
    ):
        with pytest.raises(ValueError):
            ProposalScene(0.0, (candidate_id,), "high")


def test_proposal_scene_accepts_registry_ids_after_single_digits() -> None:
    scene = ProposalScene(0.0, ("candidate-10",), "high")

    assert scene.candidate_ids == ("candidate-10",)


def test_proposal_scene_rejects_duplicate_candidate_ids() -> None:
    with pytest.raises(ValueError):
        ProposalScene(0.0, ("candidate-01", "candidate-01"), "high")


def test_loader_accepts_exact_schema_and_preserves_review_acceptance(tmp_path: Path) -> None:
    path = tmp_path / "fancam-demo-ground-truth.proposed.local.json"
    path.write_text(
        json.dumps({
            "schemaVersion": 1,
            "scenes": [
                {
                    "timestampSeconds": index,
                    "candidateIds": ["candidate-01"],
                    "confidence": "review",
                    "accepted": True,
                }
                for index in range(30)
            ],
        }),
        encoding="utf-8",
    )

    loaded = load_proposal(path)

    assert loaded.scenes[0].accepted is True
    truth = accepted_truth(loaded, {"candidate-01": "member-01"})
    assert truth.scenes[0].visible_member_ids == ("member-01",)


def test_canonical_loader_reads_only_project_docs_proposal(tmp_path: Path) -> None:
    canonical_path = tmp_path / "docs" / "fancam-demo-ground-truth.proposed.local.json"
    canonical_path.parent.mkdir()
    canonical_path.write_text(
        json.dumps({
            "schemaVersion": 1,
            "scenes": [
                {
                    "timestampSeconds": index,
                    "candidateIds": ["candidate-01"],
                    "confidence": "high",
                    "accepted": False,
                }
                for index in range(30)
            ],
        }),
        encoding="utf-8",
    )
    alternate_path = tmp_path / "alternate" / "fancam-demo-ground-truth.proposed.local.json"
    alternate_path.parent.mkdir()
    alternate_path.write_text("{}", encoding="utf-8")

    loaded = load_local_proposal(tmp_path)

    assert loaded.scenes[0].candidate_ids == ("candidate-01",)
    with pytest.raises(TypeError):
        load_local_proposal(tmp_path, alternate_path)  # type: ignore[call-arg]


def test_low_similarity_margin_marks_scene_for_review() -> None:
    registry = CandidateRegistry()
    registry.register("candidate-01", embedding((1.0, 0.0)))
    registry.register("candidate-02", embedding((0.99, 0.1)))

    scene = propose_scene(
        0.0,
        (detection(),),
        (embedding((1.0, 0.01)),),
        registry,
    )

    assert scene.confidence == "review"


def test_missing_embedding_never_creates_high_confidence_lock() -> None:
    scene = propose_scene(0.0, (detection(),), (None,), CandidateRegistry())

    assert scene.confidence == "review"


def test_scene_with_changed_detection_count_requires_review() -> None:
    registry = CandidateRegistry()

    first = propose_scene(
        0.0,
        (detection(),),
        (embedding((1.0, 0.0)),),
        registry,
    )
    second = propose_scene(
        1.0,
        (detection(), detection()),
        (embedding((1.0, 0.0)), embedding((0.0, 1.0))),
        registry,
    )

    assert first.confidence == "review"
    assert second.confidence == "review"
