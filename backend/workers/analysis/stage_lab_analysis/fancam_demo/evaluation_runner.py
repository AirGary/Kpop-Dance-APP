from __future__ import annotations

from pathlib import Path
import time
from typing import Any

from .benchmark import Detector, Embedder, FrameReader, _read_frame_with_opencv
from .components import ComponentScore, register_current_baseline
from .evaluate import evaluate_membership
from .proposal import HIGH_MARGIN, HIGH_SCORE, CandidateRegistry
from .truth import GroundTruthSet, PersonAssignment, SceneObservation


def _labelled_minutes(truth: GroundTruthSet) -> float:
    return (truth.scenes[-1].timestamp_seconds - truth.scenes[0].timestamp_seconds) / 60.0


def run_current_baseline(
    source: Path,
    truth: GroundTruthSet,
    detector: Detector,
    embedder: Embedder,
    *,
    reviewer: Any,
    reader: FrameReader | None = None,
) -> ComponentScore:
    """Evaluate direct source frames without retaining runtime media data."""

    source = Path(source)
    frame_reader = reader or _read_frame_with_opencv
    registry = CandidateRegistry()
    observations: list[SceneObservation] = []
    started = time.perf_counter()
    try:
        for scene in truth.scenes:
            frame: Any | None = None
            detections: tuple[Any, ...] = ()
            embeddings: tuple[Any | None, ...] = ()
            runtime_candidate_ids: list[str] = []
            assignments: list[PersonAssignment] = []
            try:
                frame = frame_reader(source, scene.timestamp_seconds)
                if frame is None:
                    raise ValueError("source timestamp could not be read")
                detections = tuple(detector.detect(frame))
                embeddings = tuple(
                    embedder.embed(frame, detection.box) for detection in detections
                )
                count_changed = registry.detection_count_changed(len(detections))
                for detection, embedding in zip(detections, embeddings):
                    runtime_id, score, margin, known = registry.assign_or_register(
                        embedding,
                        excluded_candidate_ids=frozenset(runtime_candidate_ids),
                    )
                    runtime_candidate_ids.append(runtime_id)
                    needs_review = (
                        not known
                        or embedding is None
                        or score < HIGH_SCORE
                        or margin < HIGH_MARGIN
                        or count_changed
                    )
                    stable_member_id = (
                        reviewer.review(
                            frame,
                            detection,
                            runtime_id,
                            force=True,
                        )
                        if needs_review
                        else reviewer.known(runtime_id)
                    )
                    assignments.append(
                        PersonAssignment(
                            runtime_id,
                            stable_member_id,
                            stable_member_id is not None,
                            needs_review,
                        )
                    )
                observations.append(
                    SceneObservation(scene.timestamp_seconds, tuple(assignments))
                )
            finally:
                del frame, detections, embeddings, runtime_candidate_ids, assignments

        elapsed_seconds = time.perf_counter() - started
        result = evaluate_membership(truth, tuple(observations))
        return ComponentScore(
            candidate=register_current_baseline(),
            result=result,
            elapsed_seconds=elapsed_seconds,
            labelled_minutes=_labelled_minutes(truth),
            # Scene member sets cannot verify person-level identity or detection.
            identity_evidence_verified=False,
        )
    finally:
        observations.clear()
        del registry
        reviewer.close()
