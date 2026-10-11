from __future__ import annotations

import argparse
from contextlib import redirect_stdout
import json
from pathlib import Path
import sys

from .benchmark_cli import _components, _default_model_root
from .components import ComponentCandidate, ComponentScore, register_current_baseline
from .local_review import LocalReviewSession, ReviewCancelled
from .selection import select_candidate
from .truth import GROUND_TRUTH_FILE_NAME, load_ground_truth


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--model-root", type=Path, default=_default_model_root())
    return parser.parse_args()


def _truth_path() -> Path:
    return Path(__file__).resolve().parents[5] / "docs" / GROUND_TRUTH_FILE_NAME


def _candidate_metadata(candidate: ComponentCandidate) -> dict[str, object]:
    return {
        "name": candidate.name,
        "version": candidate.version,
        "licenseId": candidate.license_id,
        "supplyChainReviewed": candidate.supply_chain_reviewed,
    }


def _output(score: ComponentScore, selected: bool) -> dict[str, object]:
    return {
        "candidate": _candidate_metadata(score.candidate),
        **score.to_json(),
        "selected": selected,
    }


def main() -> None:
    args = _arguments()
    try:
        with redirect_stdout(sys.stderr):
            detector, embedder = _components(args.model_root)
            truth = load_ground_truth(_truth_path())
            reviewer = LocalReviewSession()
            score = register_current_baseline().run(
                args.source,
                truth,
                detector,
                embedder,
                reviewer=reviewer,
            )
            selected = select_candidate((score,)) is not None
    except ReviewCancelled:
        raise SystemExit(1) from None
    print(json.dumps(_output(score, selected), separators=(",", ":"), sort_keys=True))


if __name__ == "__main__":
    main()
