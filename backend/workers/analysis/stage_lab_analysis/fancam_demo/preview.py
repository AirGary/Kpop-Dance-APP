"""Noninteractive continuous preview; independent identity accuracy is unknown."""
from __future__ import annotations

from collections.abc import Callable, Iterable
from collections import Counter
from pathlib import Path
from typing import Any
import math

from ..detection import NormalizedBox
from .continuous_tracker import ContinuousMemberTracker
from .body_bounds import visible_body_box


def native_samples(source: Path, duration: float, sample_fps: float):
    import cv2
    if not math.isfinite(duration) or duration <= 0 or not 2 <= sample_fps <= 30:
        raise ValueError("invalid preview duration or sample rate")
    capture = cv2.VideoCapture(str(source))
    try:
        fps = capture.get(cv2.CAP_PROP_FPS)
        if not capture.isOpened() or not math.isfinite(fps) or fps <= 0:
            raise ValueError("source cannot be decoded")
        index, next_sample = 0, 0.
        while index/fps < duration and capture.grab():
            timestamp = index/fps
            if timestamp+1e-9 >= next_sample:
                ok, frame = capture.retrieve()
                if not ok:
                    raise ValueError("source frame could not be decoded")
                yield timestamp, frame
                del frame
                next_sample += 1/sample_fps
            index += 1
    finally:
        capture.release()


def analyze_samples(frames: Iterable[tuple[float, Any]], detector, embedder, *,
                    member_count: int, member_index: int,
                    pose_estimator=None, strict_reentry: bool = False,
                    separate_identity: bool = False,
                    offline_trajectories: bool = False,
                    replay_frames: Callable[[], Iterable[tuple[float, Any]]] | None = None,
                    on_inferred: Callable[[float], None] | None = None,
                    on_reacquired: Callable[[float, NormalizedBox], None] | None = None,
                    progress: Callable[[float, int], None] | None = None):
    if not 0 <= member_index < member_count:
        raise ValueError("member index is outside configured group")
    if offline_trajectories and pose_estimator is not None and replay_frames is None:
        raise ValueError('offline pose bounds require replay_frames')
    if offline_trajectories:
        strict_reentry = separate_identity = True
    tracker = ContinuousMemberTracker(member_count, strict_reentry=strict_reentry,
                                      separate_identity=separate_identity)
    observations, anchors = [], []
    camera_transforms, previous_camera_frame = [], None
    previous_camera_boxes = ()
    if offline_trajectories:
        import cv2
        from .offline_tracker import frame_camera_transform, stitch_trajectories
    reacquisitions = 0
    pose_samples = 0
    samples: list[tuple[float, NormalizedBox | None]] = []
    missing, total, last_report = 0, 0, -5.
    for timestamp, frame in frames:
        detections = tuple(detector.detect(frame))
        embeddings = tuple(embedder.embed(frame, d.box) for d in detections)
        missing += sum(e is None for e in embeddings)
        total += len(detections)
        if offline_trajectories:
            strong = tuple(i for i, detection in enumerate(detections)
                           if detection.confidence >= .35)
            tracker_detections = tuple(detections[i] for i in strong)
            tracker_embeddings = tuple(embeddings[i] for i in strong)
        else:
            tracker_detections, tracker_embeddings = detections, embeddings
        boxes = tracker.update(timestamp, tracker_detections, tracker_embeddings)
        if offline_trajectories:
            observations.append((timestamp, detections, embeddings))
            anchors.append(boxes)
            camera_frame = None
            if getattr(frame, 'ndim', 0) in (2, 3):
                camera_frame = (cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                                if frame.ndim == 3 else frame)
                camera_frame = cv2.resize(camera_frame, (160, 90),
                                          interpolation=cv2.INTER_AREA)
            camera_transforms.append(
                None if previous_camera_frame is None or camera_frame is None
                else frame_camera_transform(previous_camera_frame, camera_frame,
                    previous_boxes=previous_camera_boxes,
                    current_boxes=tuple(d.box for d in detections)))
            previous_camera_frame = camera_frame
            previous_camera_boxes = tuple(d.box for d in detections)
        selected = boxes.get(member_index)
        if selected is not None and member_index in tracker.reacquired:
            reacquisitions += 1
            if on_reacquired:
                on_reacquired(timestamp, selected)
        if selected is not None and pose_estimator is not None:
            pose = pose_estimator.estimate(frame,
                (selected.x, selected.y, selected.width, selected.height), timestamp)
            selected = visible_body_box(selected, pose.keypoints)
            pose_samples += 1
        samples.append((timestamp, selected))
        del frame, detections, embeddings, boxes
        if progress and timestamp-last_report >= 5:
            progress(timestamp, len(samples))
            last_report = timestamp
    if not samples:
        raise ValueError("source produced no samples")
    observed = sum(box is not None for _, box in samples)
    stitched_indices = set()
    visibility_counts = None
    if offline_trajectories:
        from .offline_tracker import visibility_states
        paths, inferred = stitch_trajectories(
            observations, anchors, member_count=member_count,
            camera_transforms=tuple(camera_transforms))
        counts = Counter(visibility_states(
            observations, paths, inferred, member_index=member_index))
        visibility_counts = {state: counts[state] for state in (
            'visible', 'partially_occluded', 'fully_occluded', 'out_of_frame', 'unknown')}
        for i, members in enumerate(inferred):
            if member_index in members:
                samples[i] = (samples[i][0], paths[i][member_index])
                stitched_indices.add(i)
        # Keep only lightweight geometry for the sequential source replay.
        del observations, anchors, paths, inferred, tracker
        if pose_estimator is not None and stitched_indices:
            replayed = 0
            for i, (timestamp, frame) in enumerate(replay_frames()):
                if i >= len(samples) or timestamp != samples[i][0]:
                    raise ValueError('replay timestamps must match the analyzed source')
                replayed += 1
                if i in stitched_indices:
                    box = samples[i][1]
                    pose = pose_estimator.estimate(frame,
                        (box.x, box.y, box.width, box.height), timestamp)
                    samples[i] = (timestamp, visible_body_box(box, pose.keypoints))
                    pose_samples += 1
                del frame
            if replayed != len(samples):
                raise ValueError('replay ended before the analyzed source')
        if on_inferred:
            for i in sorted(stitched_indices):
                on_inferred(samples[i][0])
    tracked = sum(box is not None for _, box in samples)
    return tuple(samples), {
        "sampleCount": len(samples), "trackedSamples": tracked,
        "fallbackSamples": len(samples)-tracked,
        "trackingCoverage": tracked/len(samples),
        "detectedBoxes": total, "missingEmbeddings": missing,
        "poseSamples": pose_samples, "fullBodyVerified": False,
        "reacquisitions": reacquisitions,
        "identityObservedSamples": observed,
        "trajectoryInferredSamples": len(stitched_indices),
        **({"cameraMotionSamples": sum(isinstance(item, tuple) for item in camera_transforms),
            "sceneCutSamples": sum(item is False for item in camera_transforms)}
           if offline_trajectories else {}),
        **({"visibilityStateCounts": visibility_counts} if visibility_counts else {}),
        "reviewPrompts": 0, "identityAccuracy": None,
        "validationStatus": ("offline_trajectory_unvalidated" if offline_trajectories
                             else "preview_unvalidated"), "selected": False,
    }
