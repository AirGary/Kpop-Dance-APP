from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys

from .benchmark_cli import _timestamps
from .proposal import (
    PROPOSAL_FILE_NAME,
    ProposalSet,
    accepted_truth,
    apply_acceptance,
    load_proposal,
    scrub_candidate_ids,
)
from .truth import GROUND_TRUTH_FILE_NAME, GroundTruthSet


def _project_root() -> Path:
    return Path(__file__).resolve().parents[5]


def _proposal_path() -> Path:
    return _project_root() / "docs" / PROPOSAL_FILE_NAME


def _truth_path() -> Path:
    return _project_root() / "docs" / GROUND_TRUTH_FILE_NAME


def _canonical_path(path: Path, expected: Path, description: str) -> Path:
    path = Path(path)
    if path.resolve() != expected.resolve():
        raise ValueError(f"{description} must use the canonical ignored {description} path")
    return path


def _atomic_replace(path: Path, payload: dict[str, object]) -> None:
    temporary = path.with_suffix(".tmp")
    try:
        temporary.write_text(
            json.dumps(payload, separators=(",", ":"), sort_keys=True),
            encoding="utf-8",
        )
        temporary.replace(path)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise


def _truth_json(truth: GroundTruthSet) -> dict[str, object]:
    return {
        "schemaVersion": 1,
        "scenes": [
            {
                "timestampSeconds": scene.timestamp_seconds,
                "visibleMemberIds": list(scene.visible_member_ids),
            }
            for scene in truth.scenes
        ],
    }


def _read_stable_member_ids(proposal: ProposalSet) -> dict[str, str]:
    """Read local-only mappings without serializing or displaying their values."""
    stable_member_ids_by_candidate: dict[str, str] = {}
    for candidate_id in dict.fromkeys(
        candidate_id
        for scene in proposal.scenes
        for candidate_id in scene.candidate_ids
    ):
        print(
            f"Stable anonymous ID for {candidate_id}: ",
            end="",
            file=sys.stderr,
            flush=True,
        )
        stable_member_ids_by_candidate[candidate_id] = input()
    return stable_member_ids_by_candidate


def write_accepted_truth(
    truth: GroundTruthSet,
    destination: Path,
) -> GroundTruthSet:
    destination = _canonical_path(destination, _truth_path(), "truth")
    if destination.exists():
        raise FileExistsError("local truth already exists")
    temporary = destination.with_suffix(".tmp")
    try:
        temporary.write_text(
            json.dumps(_truth_json(truth), separators=(",", ":"), sort_keys=True),
            encoding="utf-8",
        )
        os.link(temporary, destination)
        temporary.unlink()
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise
    return truth


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--proposal", required=True, type=Path)
    parser.add_argument("--truth", required=True, type=Path)
    parser.add_argument("--accept-high", action="store_true")
    parser.add_argument("--accept-review", type=_timestamps, default=())
    return parser.parse_args()


def main() -> None:
    args = _arguments()
    proposal_path = _canonical_path(args.proposal, _proposal_path(), "proposal")
    truth_path = _canonical_path(args.truth, _truth_path(), "truth")
    proposal = apply_acceptance(
        load_proposal(proposal_path),
        accept_high=args.accept_high,
        accept_review_timestamps=args.accept_review,
    )
    truth = accepted_truth(proposal, _read_stable_member_ids(proposal))
    _atomic_replace(proposal_path, scrub_candidate_ids(proposal).to_json())
    truth = write_accepted_truth(
        truth,
        truth_path,
    )
    print(json.dumps({"acceptedSceneCount": len(truth.scenes)}, separators=(",", ":"), sort_keys=True))


if __name__ == "__main__":
    main()
