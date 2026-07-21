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
from .runtime_probe import load_model_manifest, resolve_model_checkpoint, resolve_model_config
from .worker import AnalysisWorker


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("operation", choices=("detect", "target"))
    parser.add_argument("--workspace", required=True, type=Path)
    parser.add_argument("--model-root", required=True, type=Path)
    parser.add_argument("--candidate-id")
    parser.add_argument("--frame-stride", type=int, default=6)
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
    create_proxy(source, proxy)
    model_root = args.model_root
    detector = RTMDetPersonDetector(
        config=str(model_root / "rtmdet-m-person.py"),
        checkpoint=str(model_root / "rtmdet-m-person.pth"),
        device="cpu",
    )
    worker = AnalysisWorker(detector=detector, frame_stride=args.frame_stride)
    if args.operation == "detect":
        with redirect_stdout(sys.stderr):
            candidates = worker.detect_candidates(proxy.parent).candidates
        print(json.dumps({"candidates": [_candidate_json(candidate) for candidate in candidates]}, separators=(",", ":")))
        return
    if not args.candidate_id:
        raise ValueError("target analysis requires a candidate id")
    with redirect_stdout(sys.stderr):
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
        analysis = worker.analyze_target(proxy.parent, args.candidate_id, pose_estimator, beats=beats)
    if not analysis.pose_frames:
        raise RuntimeError("selected candidate has no valid pose frames")
    result_path = proxy.parent / "result-v1.zip"
    artifact = write_analysis_package(
        result_path,
        PackageInputs(
            manifest={"schemaVersion": 1, "candidateId": analysis.candidate_id, "modelVersion": "rtmdet-m+rtmpose-m"},
            spotlight=[_spotlight_json(item) for item in analysis.spotlight],
            pose=[_pose_json(item) for item in analysis.pose_frames],
            timeline=[_timeline_json(item) for item in analysis.timeline],
            confidence=[{"startSeconds": analysis.pose_frames[0].time_seconds, "endSeconds": analysis.pose_frames[-1].time_seconds, "confidence": min(item.confidence for item in analysis.pose_frames)}],
        ),
    )
    print(json.dumps({"result": {"schemaVersion": 1, "sha256": artifact.sha256, "byteCount": artifact.byte_count, "contentPath": "analysis/result-v1.zip"}}, separators=(",", ":")))


def _spotlight_json(item) -> dict:
    x, y, width, height = item.box
    return {"timeSeconds": item.time_seconds, "x": x, "y": y, "width": width, "height": height, "confidence": item.confidence}


def _pose_json(item) -> dict:
    return {"timeSeconds": item.time_seconds, "confidence": item.confidence, "keypoints": [{"name": point.name, "x": point.x, "y": point.y, "confidence": point.confidence} for point in item.keypoints]}


def _timeline_json(item) -> dict:
    return {"startSeconds": item.start_seconds, "endSeconds": item.end_seconds, "difficulty": item.difficulty, "repeatGroupId": item.repeat_group_id, "reasons": [{"code": reason.code, "label": reason.label} for reason in item.reasons]}


if __name__ == "__main__":
    main()
