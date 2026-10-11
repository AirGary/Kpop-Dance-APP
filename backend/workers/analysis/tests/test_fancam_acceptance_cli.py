from __future__ import annotations

import builtins
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from stage_lab_analysis.fancam_demo import acceptance_cli
from stage_lab_analysis.fancam_demo.acceptance_cli import write_accepted_truth
from stage_lab_analysis.fancam_demo.proposal import (
    ProposalScene,
    ProposalSet,
    accepted_truth,
    apply_acceptance,
    load_proposal,
)
from stage_lab_analysis.fancam_demo.truth import load_ground_truth


def _proposal() -> ProposalSet:
    return ProposalSet(
        tuple(
            ProposalScene(
                float(index),
                ("candidate-01",),
                "review" if index == 0 else "high",
            )
            for index in range(30)
        )
    )


def test_apply_acceptance_preserves_provenance_and_requires_explicit_review() -> None:
    accepted = apply_acceptance(
        _proposal(), accept_high=True, accept_review_timestamps=(0.0,)
    )

    assert all(scene.accepted for scene in accepted.scenes)
    assert accepted.scenes[0].confidence == "review"
    assert accepted.scenes[1].confidence == "high"


def test_acceptance_cli_never_overwrites_existing_truth(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    truth = tmp_path / "docs" / "fancam-demo-ground-truth.local.json"
    truth.parent.mkdir()
    truth.write_text("existing", encoding="utf-8")
    monkeypatch.setattr(acceptance_cli, "_truth_path", lambda: truth)

    with pytest.raises(FileExistsError):
        write_accepted_truth(
            accepted_truth(
                apply_acceptance(
                    _proposal(), accept_high=True, accept_review_timestamps=(0.0,)
                ),
                {"candidate-01": "member-01"},
            ),
            truth,
        )


def test_cli_scrubs_candidate_ids_before_publishing_canonical_truth(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    proposal_path = tmp_path / "docs" / "fancam-demo-ground-truth.proposed.local.json"
    truth_path = tmp_path / "docs" / "fancam-demo-ground-truth.local.json"
    proposal_path.parent.mkdir()
    proposal_path.write_text(
        json.dumps(_proposal().to_json()), encoding="utf-8"
    )
    monkeypatch.setattr(acceptance_cli, "_proposal_path", lambda: proposal_path)
    monkeypatch.setattr(acceptance_cli, "_truth_path", lambda: truth_path)
    monkeypatch.setattr(
        acceptance_cli,
        "_arguments",
        lambda: SimpleNamespace(
            proposal=proposal_path,
            truth=truth_path,
            accept_high=True,
            accept_review=(0.0,),
        ),
    )
    stable_ids = iter(("member-01",))
    monkeypatch.setattr(builtins, "input", lambda: next(stable_ids))

    acceptance_cli.main()

    assert all(scene.accepted for scene in load_proposal(proposal_path).scenes)
    truth = load_ground_truth(truth_path)
    output = capsys.readouterr()
    assert len(truth.scenes) == 30
    assert truth.scenes[0].visible_member_ids == ("member-01",)
    assert json.loads(output.out) == {"acceptedSceneCount": 30}
    assert "member-01" not in output.out
    assert "candidate-01" not in truth_path.read_text(encoding="utf-8")
    persisted_proposal = json.loads(proposal_path.read_text(encoding="utf-8"))
    assert all(scene["candidateIds"] == [] for scene in persisted_proposal["scenes"])
    assert "candidate-01" not in proposal_path.read_text(encoding="utf-8")


def test_cli_scrubs_proposal_before_a_late_truth_publication_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    proposal_path = tmp_path / "docs" / "fancam-demo-ground-truth.proposed.local.json"
    truth_path = tmp_path / "docs" / "fancam-demo-ground-truth.local.json"
    proposal_path.parent.mkdir()
    proposal_path.write_text(json.dumps(_proposal().to_json()), encoding="utf-8")
    monkeypatch.setattr(acceptance_cli, "_proposal_path", lambda: proposal_path)
    monkeypatch.setattr(acceptance_cli, "_truth_path", lambda: truth_path)
    monkeypatch.setattr(
        acceptance_cli,
        "_arguments",
        lambda: SimpleNamespace(
            proposal=proposal_path,
            truth=truth_path,
            accept_high=True,
            accept_review=(0.0,),
        ),
    )
    monkeypatch.setattr(builtins, "input", lambda: "member-01")

    def fail_to_publish_truth(*_args: object, **_kwargs: object) -> GroundTruthSet:
        raise OSError("simulated late truth publication failure")

    monkeypatch.setattr(acceptance_cli, "write_accepted_truth", fail_to_publish_truth)

    with pytest.raises(OSError, match="late truth publication failure"):
        acceptance_cli.main()

    assert not truth_path.exists()
    persisted_proposal = json.loads(proposal_path.read_text(encoding="utf-8"))
    assert all(scene["candidateIds"] == [] for scene in persisted_proposal["scenes"])


def test_cli_rejects_noncanonical_input_paths(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    proposal_path = tmp_path / "docs" / "fancam-demo-ground-truth.proposed.local.json"
    truth_path = tmp_path / "docs" / "fancam-demo-ground-truth.local.json"
    proposal_path.parent.mkdir()
    alternate = tmp_path / "alternate" / proposal_path.name
    alternate.parent.mkdir()
    monkeypatch.setattr(acceptance_cli, "_proposal_path", lambda: proposal_path)
    monkeypatch.setattr(acceptance_cli, "_truth_path", lambda: truth_path)
    monkeypatch.setattr(
        acceptance_cli,
        "_arguments",
        lambda: SimpleNamespace(
            proposal=alternate,
            truth=truth_path,
            accept_high=True,
            accept_review=(0.0,),
        ),
    )

    with pytest.raises(ValueError, match="canonical ignored proposal path"):
        acceptance_cli.main()
