from __future__ import annotations

from .components import APPROVED_LICENSE_ID, ComponentScore


MIN_DETECTION_RECALL = 0.95
MIN_IDENTITY_ACCURACY = 0.95
MAX_CONFIRMATIONS_PER_LABELLED_MINUTE = 1.0


def _passes_safety_gate(score: ComponentScore) -> bool:
    result = score.result
    if (
        score.identity_evidence_verified is not True
        or score.candidate.license_id != APPROVED_LICENSE_ID
        or not score.candidate.supply_chain_reviewed
        or result.id_switches != 0
        or result.false_locks != 0
        or result.identity_accuracy is None
        or result.identity_accuracy < MIN_IDENTITY_ACCURACY
        or result.detection_recall < MIN_DETECTION_RECALL
        or result.confirmation_requests / score.labelled_minutes
        > MAX_CONFIRMATIONS_PER_LABELLED_MINUTE
    ):
        return False
    try:
        return score.candidate.cpu_probe() is True
    except Exception:
        return False


def select_candidate(scores: tuple[ComponentScore, ...]) -> ComponentScore | None:
    safe_scores = tuple(score for score in scores if _passes_safety_gate(score))
    if not safe_scores:
        return None
    return min(
        safe_scores,
        key=lambda score: (
            score.elapsed_seconds,
            score.candidate.name,
            score.candidate.version,
        ),
    )
