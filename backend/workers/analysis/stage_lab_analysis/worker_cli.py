from __future__ import annotations

import argparse
import json
from pathlib import Path

from .candidates import Candidate
from .detection import RTMDetPersonDetector
from .media import create_proxy
from .worker import AnalysisWorker


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("operation", choices=("detect", "target"))
    parser.add_argument("--workspace", required=True, type=Path)
    parser.add_argument("--model-root", required=True, type=Path)
    parser.add_argument("--candidate-id")
    return parser.parse_args()


def _candidate_json(candidate: Candidate) -> dict:
    box = candidate.box_summary
    return {
        "candidateId": candidate.candidate_id,
        "representativeImagePaths": list(candidate.representative_image_paths),
        "appearanceIntervals": [
            {"startSeconds": start, "endSeconds": end}
            for start, end in candidate.appearance_intervals
        ],
        "boxSummary": {"x": box.x, "y": box.y, "width": box.width, "height": box.height},
        "confidence": candidate.confidence,
    }


def main() -> None:
    args = _arguments()
    if args.operation == "target":
        raise RuntimeError("target analysis is reserved for Stage 7")
    source = args.workspace / "source.mp4"
    proxy = args.workspace / "analysis" / "proxy.mp4"
    create_proxy(source, proxy)
    model_root = args.model_root
    detector = RTMDetPersonDetector(
        config=str(model_root / "rtmdet-m-person.py"),
        checkpoint=str(model_root / "rtmdet-m-person.pth"),
        device="cpu",
    )
    candidates = AnalysisWorker(detector=detector).detect_candidates(proxy.parent).candidates
    print(json.dumps({"candidates": [_candidate_json(candidate) for candidate in candidates]}, separators=(",", ":")))


if __name__ == "__main__":
    main()

