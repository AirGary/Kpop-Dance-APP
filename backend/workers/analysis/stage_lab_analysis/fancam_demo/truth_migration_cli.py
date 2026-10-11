from __future__ import annotations

import argparse
from contextlib import redirect_stdout
import json
from pathlib import Path
import sys
from typing import Any
from dataclasses import dataclass

from ..reid import PersonEmbedding
from .benchmark import Detector, Embedder, _read_frame_with_opencv
from .benchmark_cli import _components, _default_model_root
from .fallback_appearance import expanded_retry_box
from .global_clustering import FIXED_MEMBER_COUNT, cluster_fixed_group_member_ids
from .truth_migration import (
    LegacyTruthScene,
    convert_scene_member_ids,
    load_legacy_truth,
    migrate_legacy_truth,
)


_LEGACY_TRUTH_FILE_NAME = "fancam-demo-ground-truth.local.json"
_LEGACY_BACKUP_FILE_NAME = "fancam-demo-ground-truth.legacy.local.json"
_NEIGHBOR_FRAME_STEP_SECONDS = 0.25
_NEIGHBOR_FRAME_STEPS = 8
_TRACK_MATCH_IOU = 0.3
_read_frame = _read_frame_with_opencv


class MigrationRejected(Exception):
    """A legacy candidate was not assigned a unique stable member ID."""


@dataclass(frozen=True, slots=True)
class CollectedMigrationAssignments:
    legacy_scenes: tuple[LegacyTruthScene, ...]
    scene_member_ids: tuple[tuple[str, ...], ...]


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--model-root", type=Path, default=_default_model_root())
    return parser.parse_args()


def _docs_directory() -> Path:
    return Path(__file__).resolve().parents[5] / "docs"


def _legacy_path() -> Path:
    return _docs_directory() / _LEGACY_TRUTH_FILE_NAME


def _backup_path() -> Path:
    return _docs_directory() / _LEGACY_BACKUP_FILE_NAME


def _canonical_path() -> Path:
    return _docs_directory() / _LEGACY_TRUTH_FILE_NAME


def collect_complete_assignments(
    source: Path,
    legacy_scenes: tuple[LegacyTruthScene, ...],
    detector: Detector,
    embedder: Embedder,
) -> CollectedMigrationAssignments:
    """Collect complete scenes, then cluster the fixed group in memory."""

    scene_embeddings: list[tuple[PersonEmbedding, ...]] = []
    selected_legacy_scenes: list[LegacyTruthScene] = []
    for scene in legacy_scenes:
        frame: Any | None = None
        detections: tuple[Any, ...] = ()
        embeddings: tuple[PersonEmbedding | None, ...] = ()
        try:
            frame = _read_frame(source, scene.timestamp_seconds)
            if frame is None:
                raise ValueError("source timestamp could not be read")
            detections = tuple(detector.detect(frame))
            if len(detections) != len(scene.candidate_ids):
                raise MigrationRejected()
            selected_indices = _fixed_group_detection_indices(detections)
            detections = tuple(detections[index] for index in selected_indices)
            selected_legacy_scenes.append(
                LegacyTruthScene(
                    scene.timestamp_seconds,
                    tuple(scene.candidate_ids[index] for index in selected_indices),
                )
            )
            embeddings = tuple(
                _embedding_with_temporal_recovery(
                    source,
                    scene.timestamp_seconds,
                    frame,
                    detection.box,
                    detector,
                    embedder,
                )
                for detection in detections
            )
            if any(embedding is None for embedding in embeddings):
                raise MigrationRejected()
            scene_embeddings.append(tuple(embedding for embedding in embeddings if embedding is not None))
        finally:
            del frame, detections, embeddings
    try:
        return CollectedMigrationAssignments(
            tuple(selected_legacy_scenes),
            cluster_fixed_group_member_ids(tuple(scene_embeddings)),
        )
    except ValueError as error:
        raise MigrationRejected() from error


def _fixed_group_detection_indices(detections: tuple[Any, ...]) -> tuple[int, ...]:
    if len(detections) <= FIXED_MEMBER_COUNT:
        return tuple(range(len(detections)))
    highest_confidence = sorted(
        range(len(detections)),
        key=lambda index: (-detections[index].confidence, index),
    )[:FIXED_MEMBER_COUNT]
    return tuple(sorted(highest_confidence))


def _embedding_with_expanded_retry(
    frame: Any, box: Any, embedder: Embedder
) -> PersonEmbedding | None:
    primary_embedding = embedder.embed(frame, box)
    if primary_embedding is not None:
        return primary_embedding
    return embedder.embed(frame, expanded_retry_box(box))


def _embedding_with_temporal_recovery(
    source: Path,
    timestamp_seconds: float,
    frame: Any,
    box: Any,
    detector: Detector,
    embedder: Embedder,
) -> PersonEmbedding | None:
    embedding = _embedding_with_expanded_retry(frame, box, embedder)
    if embedding is not None:
        return embedding

    for direction in (1.0, -1.0):
        tracked_box = box
        for step in range(1, _NEIGHBOR_FRAME_STEPS + 1):
            neighbor_timestamp = timestamp_seconds + direction * step * _NEIGHBOR_FRAME_STEP_SECONDS
            if neighbor_timestamp < 0:
                break
            neighbor_frame = _read_frame(source, neighbor_timestamp)
            if neighbor_frame is None:
                raise ValueError("source timestamp could not be read")
            try:
                tracked_detection = _tracked_neighbor_detection(
                    tracked_box,
                    tuple(detector.detect(neighbor_frame)),
                )
                if tracked_detection is None:
                    break
                tracked_box = tracked_detection.box
                embedding = _embedding_with_expanded_retry(
                    neighbor_frame,
                    tracked_box,
                    embedder,
                )
                if embedding is not None:
                    return embedding
            finally:
                del neighbor_frame
    return None


def _tracked_neighbor_detection(box: Any, detections: tuple[Any, ...]) -> Any | None:
    candidates = sorted(
        (
            (box.iou(detection.box), detection_index, detection)
            for detection_index, detection in enumerate(detections)
        ),
        key=lambda item: (-item[0], item[1]),
    )
    if not candidates or candidates[0][0] < _TRACK_MATCH_IOU:
        return None
    return candidates[0][2]


def main() -> None:
    args = _arguments()
    collected: CollectedMigrationAssignments | None = None
    try:
        with redirect_stdout(sys.stderr):
            legacy_path = _legacy_path()
            legacy_scenes = load_legacy_truth(legacy_path)
            detector, embedder = _components(args.model_root)
            collected = collect_complete_assignments(
                args.source, legacy_scenes, detector, embedder
            )
            truth = convert_scene_member_ids(
                collected.legacy_scenes,
                collected.scene_member_ids,
            )
            truth = migrate_legacy_truth(
                legacy_path,
                _backup_path(),
                _canonical_path(),
                truth,
            )
    except (MigrationRejected, OSError, ValueError):
        raise SystemExit(1) from None
    print(json.dumps({"migratedSceneCount": len(truth.scenes)}, separators=(",", ":")))


if __name__ == "__main__":
    main()
