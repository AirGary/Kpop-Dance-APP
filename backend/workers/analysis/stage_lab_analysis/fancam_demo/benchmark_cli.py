from __future__ import annotations

import argparse
from contextlib import redirect_stdout
import json
import os
from pathlib import Path
import sys

from ..detection import RTMDetPersonDetector
from ..reid import OpenVINOReIDEmbedder
from ..runtime_probe import load_model_manifest
from .benchmark import run_native_benchmark


def _timestamps(value: str) -> tuple[float, ...]:
    try:
        values = tuple(float(item.strip()) for item in value.split(",") if item.strip())
    except ValueError as error:
        raise argparse.ArgumentTypeError("timestamps must be comma-separated numbers") from error
    if not values:
        raise argparse.ArgumentTypeError("timestamps must not be empty")
    return values


def _default_model_root() -> Path:
    configured = os.environ.get("STAGE_LAB_MODEL_ROOT")
    if configured:
        return Path(configured)
    return Path(__file__).resolve().parents[5] / ".local-ai" / "models"


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--timestamps", required=True, type=_timestamps)
    parser.add_argument(
        "--model-root",
        type=Path,
        default=_default_model_root(),
    )
    return parser.parse_args()


def _components(model_root: Path, *, detector_threshold: float = .35):
    manifest = load_model_manifest(Path(__file__).resolve().parents[2] / "model-manifest.json")
    detector_model = next(model for model in manifest["models"] if model["role"] == "detector")
    reid_model = next(model for model in manifest["models"] if model["role"] == "reid")
    detector = RTMDetPersonDetector(
        config=str(model_root / detector_model["configLocalPath"]),
        checkpoint=str(model_root / detector_model["localPath"]),
        device="cpu",
        threshold=detector_threshold,
    )
    assets = {asset["role"]: asset for asset in reid_model["assets"]}
    embedder = OpenVINOReIDEmbedder(
        model_xml=model_root / assets["xml"]["localPath"],
        model_bin=model_root / assets["bin"]["localPath"],
        expected_xml_sha256=str(assets["xml"]["sha256"]),
        expected_bin_sha256=str(assets["bin"]["sha256"]),
        device="CPU",
    )
    return detector, embedder


def main() -> None:
    args = _arguments()
    with redirect_stdout(sys.stderr):
        detector, embedder = _components(args.model_root)
        report = run_native_benchmark(args.source, args.timestamps, detector, embedder)
    print(json.dumps(report.to_json(), separators=(",", ":"), sort_keys=True))


if __name__ == "__main__":
    main()
