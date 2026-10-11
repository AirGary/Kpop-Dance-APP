from __future__ import annotations

import argparse
from contextlib import redirect_stdout
import json
from pathlib import Path
import sys
from typing import Any

from .benchmark import Detector, Embedder, FrameReader, _read_frame_with_opencv, _validate_timestamps
from .benchmark_cli import _components, _default_model_root, _timestamps
from .proposal import CandidateRegistry, PROPOSAL_FILE_NAME, ProposalSet, propose_scene


def run_native_proposal(
    source: Path,
    timestamps: tuple[float, ...],
    detector: Detector,
    embedder: Embedder,
    destination: Path,
    *,
    reader: FrameReader | None = None,
) -> ProposalSet:
    """Create an anonymous, local-only proposal from direct source frames."""

    source = Path(source)
    destination = Path(destination)
    if destination.resolve() != _destination().resolve():
        raise ValueError("destination must use the canonical ignored proposal path")
    _validate_timestamps(timestamps)
    frame_reader = reader or _read_frame_with_opencv
    registry = CandidateRegistry()
    scenes = []
    temporary = destination.with_suffix(".tmp")

    try:
        for timestamp in timestamps:
            frame: Any | None = None
            detections: tuple[Any, ...] = ()
            embeddings: tuple[Any | None, ...] = ()
            try:
                frame = frame_reader(source, timestamp)
                if frame is None:
                    raise ValueError("source timestamp could not be read")
                detections = tuple(detector.detect(frame))
                embeddings = tuple(
                    embedder.embed(frame, detection.box) for detection in detections
                )
                scenes.append(propose_scene(timestamp, detections, embeddings, registry))
            finally:
                del frame, detections, embeddings

        proposal = ProposalSet(tuple(scenes))
        temporary.write_text(
            json.dumps(proposal.to_json(), separators=(",", ":"), sort_keys=True),
            encoding="utf-8",
        )
        temporary.replace(destination)
        return proposal
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--timestamps", required=True, type=_timestamps)
    parser.add_argument("--model-root", type=Path, default=_default_model_root())
    return parser.parse_args()


def _destination() -> Path:
    return Path(__file__).resolve().parents[5] / "docs" / PROPOSAL_FILE_NAME


def main() -> None:
    args = _arguments()
    with redirect_stdout(sys.stderr):
        detector, embedder = _components(args.model_root)
        proposal = run_native_proposal(
            args.source,
            args.timestamps,
            detector,
            embedder,
            _destination(),
        )
    print(
        json.dumps(
            {
                "sceneCount": len(proposal.scenes),
                "highCount": sum(scene.confidence == "high" for scene in proposal.scenes),
                "reviewCount": sum(scene.confidence == "review" for scene in proposal.scenes),
            },
            separators=(",", ":"),
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
