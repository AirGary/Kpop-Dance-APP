from __future__ import annotations

from dataclasses import replace

import pytest

from stage_lab_analysis.fancam_demo.components import ComponentCandidate, ComponentScore
from stage_lab_analysis.fancam_demo.evaluate import EvaluationResult
from stage_lab_analysis.fancam_demo.selection import select_candidate


def _candidate(
    name: str,
    *,
    cpu_ready: bool = True,
    supply_chain_reviewed: bool = True,
) -> ComponentCandidate:
    return ComponentCandidate(
        name=name,
        version="1.0",
        license_id="Apache-2.0",
        cpu_probe=lambda: cpu_ready,
        run=lambda: (),
        provenance="approved-manifest",
        supply_chain_reviewed=supply_chain_reviewed,
    )


def _score(
    candidate: ComponentCandidate,
    *,
    recall: float = 0.95,
    accuracy: float | None = 0.95,
    false_locks: int = 0,
    confirmations: int = 1,
    elapsed_seconds: float = 1.0,
    labelled_minutes: float = 1.0,
) -> ComponentScore:
    return ComponentScore(
        candidate=candidate,
        result=EvaluationResult(
            detection_recall=recall,
            identity_accuracy=accuracy,
            id_switches=0,
            false_locks=false_locks,
            confirmation_requests=confirmations,
        ),
        elapsed_seconds=elapsed_seconds,
        labelled_minutes=labelled_minutes,
        # Synthetic evidence only: these fixtures exercise selection gates.
        identity_evidence_verified=True,
    )


def test_selection_rejects_a_faster_candidate_that_has_a_false_lock() -> None:
    fast_but_wrong = _score(_candidate("fast"), false_locks=1, elapsed_seconds=0.1)
    safe_candidate = _score(_candidate("safe"), elapsed_seconds=1.0)

    assert select_candidate((fast_but_wrong, safe_candidate)) == safe_candidate


def test_selection_returns_none_when_no_candidate_meets_identity_gate() -> None:
    unsafe_candidate = _score(_candidate("unsafe"), accuracy=0.94)

    assert select_candidate((unsafe_candidate,)) is None


def test_selection_requires_supply_chain_and_cpu_evidence() -> None:
    unreviewed = _score(_candidate("unreviewed", supply_chain_reviewed=False))
    cpu_unready = _score(_candidate("cpu-unready", cpu_ready=False))

    assert select_candidate((unreviewed, cpu_unready)) is None


def test_selection_rejects_perfect_legacy_score_without_identity_evidence() -> None:
    score = ComponentScore(
        candidate=_candidate("legacy"),
        result=EvaluationResult(1.0, 1.0, 0, 0, 0),
        elapsed_seconds=0.1,
    )

    assert select_candidate((score,)) is None
    assert score.identity_evidence_verified is False


def test_selection_requires_explicit_verified_evidence_even_for_faster_score() -> None:
    verified = _score(_candidate("verified"))
    unverified = replace(verified, elapsed_seconds=0.01, identity_evidence_verified=False)

    assert select_candidate((unverified, verified)) is verified


@pytest.mark.parametrize("verified", (False, True))
def test_score_serializes_evidence_and_legacy_metric_scope(verified: bool) -> None:
    score = replace(_score(_candidate("synthetic")), identity_evidence_verified=verified)

    assert score.to_json() == {
        "metrics": score.result.to_json(),
        "elapsedSeconds": 1.0,
        "labelledMinutes": 1.0,
        "identityEvidenceVerified": verified,
        "metricScope": "member_set_consistency_only",
    }


@pytest.mark.parametrize("invalid", (None, 0, 1, "true", "false", (), {}))
def test_score_requires_boolean_identity_evidence(invalid: object) -> None:
    with pytest.raises(ValueError, match="identity_evidence_verified must be a boolean"):
        ComponentScore(
            candidate=_candidate("invalid"),
            result=EvaluationResult(1.0, 1.0, 0, 0, 0),
            elapsed_seconds=1.0,
            identity_evidence_verified=invalid,
        )
