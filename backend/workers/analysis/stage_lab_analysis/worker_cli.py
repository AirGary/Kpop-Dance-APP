from __future__ import annotations

import argparse
from contextlib import redirect_stdout
import json
import sys
from pathlib import Path

from .candidates import Candidate
from .detection import RTMDetPersonDetector
from .audio import extract_beats
from .media import create_proxy
from .package import PackageInputs, write_analysis_package
from .pose import RTMPoseEstimator
from .reid import OpenVINOReIDEmbedder
from .runtime_probe import load_model_manifest, resolve_model_checkpoint, resolve_model_config
from .worker import AnalysisWorker, TargetAnalysisAwaitingConfirmation


def _positive_int(value: str) -> int:
    parsed = int(value)
    if parsed < 1:
        raise argparse.ArgumentTypeError("frame stride must be positive")
    return parsed


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("operation", choices=("detect", "target"))
    parser.add_argument("--workspace", required=True, type=Path)
    parser.add_argument("--model-root", required=True, type=Path)
    parser.add_argument("--candidate-id")
    parser.add_argument("--frame-stride", type=_positive_int, default=6)
    parser.add_argument("--candidate-frame-stride", type=_positive_int, default=6)
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
    source = args.workspace / "source.mp4"
    proxy = args.workspace / "analysis" / "proxy.mp4"
    with redirect_stdout(sys.stderr):
        create_proxy(source, proxy)
        model_root = args.model_root
        detector = RTMDetPersonDetector(
            config=str(model_root / "rtmdet-m-person.py"),
            checkpoint=str(model_root / "rtmdet-m-person.pth"),
            device="cpu",
        )
        worker = AnalysisWorker(
            detector=detector,
            reid_embedder=_reid_embedder(model_root),
            frame_stride=args.frame_stride,
            candidate_frame_stride=getattr(args, "candidate_frame_stride", None),
        )
        if args.operation == "detect":
            candidates = worker.detect_candidates(proxy.parent).candidates
            response = {"candidates": [_candidate_json(candidate) for candidate in candidates]}
        else:
            if not args.candidate_id:
                raise ValueError("target analysis requires a candidate id")
            response = _target_response(worker, proxy, args.candidate_id, model_root)
    print(json.dumps(response, separators=(",", ":")))


def _target_response(worker: AnalysisWorker, proxy: Path, candidate_id: str, model_root: Path) -> dict:
    """Run target work with stdout already redirected to diagnostics-only stderr."""
    import mmpose

    manifest = load_model_manifest(Path(__file__).resolve().parents[1] / "model-manifest.json")
    pose_model = next(model for model in manifest["models"] if model["role"] == "pose")
    pose_config = resolve_model_config(
        pose_model,
        model_root=model_root,
        package_root=Path(mmpose.__file__).resolve().parent,
    )
    pose_checkpoint = resolve_model_checkpoint(pose_model, model_root=model_root)
    pose_estimator = RTMPoseEstimator(
        config=str(pose_config),
        checkpoint=str(pose_checkpoint),
        expected_sha256=str(pose_model["sha256"]),
        device="cpu",
    )
    beats = extract_beats(proxy, proxy.parent).beats
    outcome = worker.analyze_target(proxy.parent, candidate_id, pose_estimator, beats=beats)
    return _target_outcome_payload(outcome, proxy)


def _reid_embedder(model_root: Path) -> OpenVINOReIDEmbedder:
    """Construct the verified local CPU Re-ID adapter from the pinned manifest."""
    manifest = load_model_manifest(Path(__file__).resolve().parents[1] / "model-manifest.json")
    reid = next(model for model in manifest["models"] if model["role"] == "reid")
    assets = {asset["role"]: asset for asset in reid["assets"]}
    xml, binary = assets["xml"], assets["bin"]
    return OpenVINOReIDEmbedder(
        model_xml=model_root / str(xml["localPath"]),
        model_bin=model_root / str(binary["localPath"]),
        expected_xml_sha256=str(xml["sha256"]),
        expected_bin_sha256=str(binary["sha256"]),
        device="CPU",
    )


def _target_outcome_payload(outcome, proxy: Path) -> dict:
    """Serialize only a target outcome; this remains testable without models or media."""
    if isinstance(outcome, TargetAnalysisAwaitingConfirmation):
        confirmation = outcome.confirmation
        return {
            "outcome": "awaitingConfirmation",
            "confirmation": {
                "confirmationId": confirmation.confirmation_id,
                "previousImagePath": confirmation.previous_image_path,
                "candidateImagePath": confirmation.candidate_image_path,
                "previousInterval": {
                    "startSeconds": confirmation.previous_interval[0],
                    "endSeconds": confirmation.previous_interval[1],
                },
                "candidateInterval": {
                    "startSeconds": confirmation.candidate_interval[0],
                    "endSeconds": confirmation.candidate_interval[1],
                },
                "candidateClusterId": confirmation.candidate_cluster_id,
            },
        }
    analysis = outcome.result
    if not analysis.pose_frames:
        raise RuntimeError("selected candidate has no valid pose frames")
    result_path = proxy.parent / "result-v1.zip"
    artifact = write_analysis_package(
        result_path,
        PackageInputs(
            manifest={"schemaVersion": 1, "candidateId": analysis.candidate_id, "modelVersion": "rtmdet-m+rtmpose-m-coco-wholebody"},
            spotlight=[_spotlight_json(item) for item in analysis.spotlight],
            pose=[_pose_json(item) for item in analysis.pose_frames],
            timeline=[_timeline_json(item) for item in analysis.timeline],
            confidence=[{"startSeconds": analysis.pose_frames[0].time_seconds, "endSeconds": analysis.pose_frames[-1].time_seconds, "confidence": min(item.confidence for item in analysis.pose_frames)}],
        ),
    )
    return {"outcome": "completed", "result": {"schemaVersion": 1, "sha256": artifact.sha256, "byteCount": artifact.byte_count, "contentPath": "analysis/result-v1.zip"}}


def _spotlight_json(item) -> dict:
    x, y, width, height = item.box
    return {"timeSeconds": item.time_seconds, "x": x, "y": y, "width": width, "height": height, "confidence": item.confidence}


def _pose_json(item) -> dict:
    return {"timeSeconds": item.time_seconds, "confidence": item.confidence, "keypoints": [{"name": point.name, "x": point.x, "y": point.y, "confidence": point.confidence} for point in item.keypoints]}


def _timeline_json(item) -> dict:
    return {"startSeconds": item.start_seconds, "endSeconds": item.end_seconds, "difficulty": item.difficulty, "repeatGroupId": item.repeat_group_id, "reasons": [{"code": reason.code, "label": reason.label} for reason in item.reasons]}


if __name__ == "__main__":
    main()
