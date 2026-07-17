from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


@dataclass(frozen=True, slots=True)
class NormalizedBox:
    x: float
    y: float
    width: float
    height: float

    def __post_init__(self) -> None:
        values = (self.x, self.y, self.width, self.height)
        if any(value != value or value in (float("inf"), float("-inf")) for value in values):
            raise ValueError("box coordinates must be finite")
        if self.x < 0 or self.y < 0 or self.width <= 0 or self.height <= 0:
            raise ValueError("box coordinates must be normalized")
        if self.x + self.width > 1 or self.y + self.height > 1:
            raise ValueError("box coordinates must be normalized")

    @property
    def area(self) -> float:
        return self.width * self.height

    def iou(self, other: "NormalizedBox") -> float:
        left = max(self.x, other.x)
        top = max(self.y, other.y)
        right = min(self.x + self.width, other.x + other.width)
        bottom = min(self.y + self.height, other.y + other.height)
        intersection = max(0.0, right - left) * max(0.0, bottom - top)
        union = self.area + other.area - intersection
        return intersection / union if union else 0.0

    @classmethod
    def from_pixels(
        cls, left: float, top: float, right: float, bottom: float, *, width: int, height: int
    ) -> "NormalizedBox":
        if width <= 0 or height <= 0:
            raise ValueError("frame dimensions must be positive")
        clipped_left = max(0.0, min(float(width), left))
        clipped_top = max(0.0, min(float(height), top))
        clipped_right = max(clipped_left, min(float(width), right))
        clipped_bottom = max(clipped_top, min(float(height), bottom))
        return cls(
            x=clipped_left / width,
            y=clipped_top / height,
            width=(clipped_right - clipped_left) / width,
            height=(clipped_bottom - clipped_top) / height,
        )


@dataclass(frozen=True, slots=True)
class Detection:
    time_seconds: float
    box: NormalizedBox
    confidence: float

    def __post_init__(self) -> None:
        if self.time_seconds < 0 or self.time_seconds != self.time_seconds:
            raise ValueError("detection time must be non-negative")
        if not 0 <= self.confidence <= 1:
            raise ValueError("detection confidence must be between 0 and 1")


class PersonDetector(Protocol):
    def detect(self, frame: Any) -> tuple[Detection, ...]: ...


class RTMDetPersonDetector:
    """Small adapter that keeps OpenMMLab tensors out of the worker contract."""

    def __init__(self, *, config: str, checkpoint: str, device: str = "cpu", threshold: float = 0.35) -> None:
        self._config = config
        self._checkpoint = checkpoint
        self._device = device
        self._threshold = threshold
        self._model = None

    def _load(self) -> Any:
        if self._model is None:
            try:
                from mmdet.apis import init_detector
            except ImportError as error:
                raise RuntimeError("RTMDet dependencies are not installed") from error
            self._model = init_detector(self._config, self._checkpoint, device=self._device)
        return self._model

    def detect(self, frame: Any) -> tuple[Detection, ...]:
        try:
            from mmdet.apis import inference_detector
        except ImportError as error:
            raise RuntimeError("RTMDet dependencies are not installed") from error

        try:
            result = inference_detector(self._load(), frame)
        except Exception as error:
            if self._device != "mps" or not _is_mps_backend_failure(error):
                raise
            self._device = "cpu"
            self._model = None
            result = inference_detector(self._load(), frame)
        instances = result.pred_instances
        boxes = instances.bboxes.detach().cpu().numpy()
        scores = instances.scores.detach().cpu().numpy()
        labels = instances.labels.detach().cpu().numpy()
        height, width = frame.shape[:2]
        detections: list[Detection] = []
        for box, score, label in zip(boxes, scores, labels):
            if int(label) != 0 or float(score) < self._threshold:
                continue
            detections.append(
                Detection(
                    time_seconds=0.0,
                    box=NormalizedBox.from_pixels(*box, width=width, height=height),
                    confidence=float(score),
                )
            )
        return tuple(detections)


def _is_mps_backend_failure(error: Exception) -> bool:
    message = str(error).lower()
    return any(
        marker in message
        for marker in (
            "mps backend",
            "not implemented for 'mps'",
            "not currently implemented for the mps device",
            "placeholder storage has not been allocated on mps",
        )
    )
