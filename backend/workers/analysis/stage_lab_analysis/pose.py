from __future__ import annotations

from dataclasses import dataclass
import math
from pathlib import Path
from typing import Any, Protocol

from .runtime_probe import trusted_checkpoint_loading


@dataclass(frozen=True, slots=True)
class PoseKeypoint:
    name: str
    x: float
    y: float
    confidence: float

    def __post_init__(self) -> None:
        if not self.name or not all(math.isfinite(value) for value in (self.x, self.y, self.confidence)):
            raise ValueError("pose keypoint values must be finite")
        if not 0 <= self.x <= 1 or not 0 <= self.y <= 1:
            raise ValueError("pose keypoint coordinates must be normalized")
        if not 0 <= self.confidence <= 1:
            raise ValueError("pose keypoint confidence must be between 0 and 1")


@dataclass(frozen=True, slots=True)
class PoseFrame:
    time_seconds: float
    box: tuple[float, float, float, float]
    keypoints: tuple[PoseKeypoint, ...]
    confidence: float

    def __post_init__(self) -> None:
        if not math.isfinite(self.time_seconds) or self.time_seconds < 0:
            raise ValueError("pose timestamp must be finite and non-negative")
        if len(self.box) != 4 or not all(math.isfinite(value) for value in self.box):
            raise ValueError("pose box must be finite")
        x, y, width, height = self.box
        if x < 0 or y < 0 or width <= 0 or height <= 0 or x + width > 1 or y + height > 1:
            raise ValueError("pose box must be normalized")
        if not 0 <= self.confidence <= 1:
            raise ValueError("pose confidence must be between 0 and 1")


@dataclass(frozen=True, slots=True)
class SpotlightKeyframe:
    time_seconds: float
    box: tuple[float, float, float, float]
    confidence: float


class PoseEstimator(Protocol):
    def estimate(self, frame: Any, box: tuple[float, float, float, float], time_seconds: float) -> PoseFrame: ...


_KEYPOINT_NAMES = (
    "nose", "left_eye", "right_eye", "left_ear", "right_ear",
    "left_shoulder", "right_shoulder", "left_elbow", "right_elbow",
    "left_wrist", "right_wrist", "left_hip", "right_hip",
    "left_knee", "right_knee", "left_ankle", "right_ankle",
)


class RTMPoseEstimator:
    def __init__(
        self,
        *,
        config: str,
        checkpoint: str,
        expected_sha256: str,
        device: str = "cpu",
    ) -> None:
        self._config = config
        self._checkpoint = checkpoint
        self._expected_sha256 = expected_sha256
        self._device = device
        self._model = None

    def _load(self):
        if self._model is None:
            from mmpose.apis import init_model

            with trusted_checkpoint_loading(
                Path(self._checkpoint), self._expected_sha256
            ):
                self._model = init_model(self._config, self._checkpoint, device=self._device)
        return self._model

    def estimate(self, frame: Any, box: tuple[float, float, float, float], time_seconds: float) -> PoseFrame:
        try:
            return self._estimate(frame, box, time_seconds)
        except Exception as error:
            if self._device != "mps" or not _is_mps_failure(error):
                raise
            self._device = "cpu"
            self._model = None
            return self._estimate(frame, box, time_seconds)

    def _estimate(self, frame: Any, box: tuple[float, float, float, float], time_seconds: float) -> PoseFrame:
        import numpy as np
        from mmpose.apis import inference_topdown

        height, width = frame.shape[:2]
        x, y, box_width, box_height = box
        bbox = np.array([[x * width, y * height, (x + box_width) * width, (y + box_height) * height]], dtype=np.float32)
        results = inference_topdown(self._load(), frame, bbox, bbox_format="xyxy")
        if not results:
            return PoseFrame(time_seconds, box, (), 0.0)
        instances = results[0].pred_instances
        points = np.asarray(instances.keypoints)[0]
        scores = np.asarray(getattr(instances, "keypoint_scores", np.ones(points.shape[:1])))[0]
        keypoints = tuple(
            PoseKeypoint(
                _KEYPOINT_NAMES[index] if index < len(_KEYPOINT_NAMES) else f"joint-{index}",
                _clamp_normalized(float(point[0]) / width),
                _clamp_normalized(float(point[1]) / height),
                _clamp_normalized(float(scores[index])),
            )
            for index, point in enumerate(points)
        )
        confidence = sum(point.confidence for point in keypoints) / max(1, len(keypoints))
        return PoseFrame(time_seconds, box, keypoints, confidence)


def _clamp_normalized(value: float) -> float:
    if not math.isfinite(value):
        raise ValueError("pose keypoint values must be finite")
    return min(1.0, max(0.0, value))


def _is_mps_failure(error: Exception) -> bool:
    message = str(error).lower()
    return any(marker in message for marker in (
        "mps", "not implemented", "nms_impl",
    ))


def validate_pose_track(frames: list[PoseFrame] | tuple[PoseFrame, ...]) -> tuple[PoseFrame, ...]:
    track = tuple(frames)
    if any(current.time_seconds <= previous.time_seconds for previous, current in zip(track, track[1:])):
        raise ValueError("pose timestamps must be monotonic")
    return track


def build_spotlight_track(frames: list[PoseFrame] | tuple[PoseFrame, ...]) -> tuple[SpotlightKeyframe, ...]:
    validated = validate_pose_track(frames)
    return tuple(
        SpotlightKeyframe(
            time_seconds=frame.time_seconds,
            box=frame.box,
            confidence=frame.confidence if frame.confidence >= 0.5 else frame.confidence * 0.5,
        )
        for frame in validated
    )
