from __future__ import annotations

from collections import Counter
from collections.abc import Callable, Iterable
from dataclasses import dataclass
import json
import math
from pathlib import Path
import time
from typing import Any, Protocol


class Detector(Protocol):
    def detect(self, frame: Any) -> Iterable[Any]: ...


class Embedder(Protocol):
    def embed(self, frame: Any, box: Any) -> Any | None: ...


FrameReader = Callable[[Path, float], Any | None]


def _finite_non_negative(value: object, name: str) -> float:
    if isinstance(value, bool):
        raise ValueError(f"{name} must be finite and non-negative")
    try:
        result = float(value)
    except (TypeError, ValueError, OverflowError) as error:
        raise ValueError(f"{name} must be finite and non-negative") from error
    if not math.isfinite(result) or result < 0:
        raise ValueError(f"{name} must be finite and non-negative")
    return result


def _non_negative_count(value: object, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{name} must be a non-negative integer")
    return value


@dataclass(frozen=True, slots=True)
class BenchmarkSample:
    timestamp_seconds: float
    detected_people: int
    usable_embeddings: int
    elapsed_seconds: float

    def __post_init__(self) -> None:
        _finite_non_negative(self.timestamp_seconds, "timestamp_seconds")
        _non_negative_count(self.detected_people, "detected_people")
        _non_negative_count(self.usable_embeddings, "usable_embeddings")
        _finite_non_negative(self.elapsed_seconds, "elapsed_seconds")


@dataclass(frozen=True, slots=True)
class BenchmarkReport:
    samples: tuple[BenchmarkSample, ...]

    def __post_init__(self) -> None:
        samples = tuple(self.samples)
        if not all(isinstance(sample, BenchmarkSample) for sample in samples):
            raise TypeError("samples must contain BenchmarkSample values")
        object.__setattr__(self, "samples", samples)

    def to_json(self) -> dict[str, object]:
        detected = Counter(sample.detected_people for sample in self.samples)
        embeddings = Counter(sample.usable_embeddings for sample in self.samples)
        elapsed = sum(sample.elapsed_seconds for sample in self.samples)
        frames_per_second = len(self.samples) / elapsed if elapsed else 0.0
        return {
            "sampleCount": len(self.samples),
            "detectedPeopleHistogram": {
                str(count): detected[count] for count in sorted(detected)
            },
            "usableEmbeddingHistogram": {
                str(count): embeddings[count] for count in sorted(embeddings)
            },
            "elapsedSeconds": elapsed,
            "framesPerSecond": frames_per_second,
        }

    def to_json_text(self) -> str:
        return json.dumps(self.to_json(), separators=(",", ":"), sort_keys=True)


def _read_frame_with_opencv(source: Path, timestamp_seconds: float) -> Any:
    try:
        import cv2
    except ImportError as error:
        raise RuntimeError("OpenCV is required for the native benchmark") from error

    capture = cv2.VideoCapture(str(source))
    try:
        if not capture.isOpened():
            raise ValueError("source video is unreadable")
        capture.set(cv2.CAP_PROP_POS_MSEC, timestamp_seconds * 1000.0)
        success, frame = capture.read()
        if not success or frame is None:
            raise ValueError("source timestamp could not be read")
        return frame
    finally:
        capture.release()


def _validate_timestamps(timestamps: tuple[float, ...]) -> None:
    for timestamp in timestamps:
        _finite_non_negative(timestamp, "timestamp_seconds")


def run_native_benchmark(
    source: Path,
    timestamps: tuple[float, ...],
    detector: Detector,
    embedder: Embedder,
    *,
    reader: FrameReader | None = None,
) -> BenchmarkReport:
    """Evaluate injected components on frames read directly from ``source``.

    Only aggregate counters and timing are retained. Frame, detection and
    embedding objects are released after each requested timestamp.
    """

    source = Path(source)
    _validate_timestamps(timestamps)
    frame_reader = reader or _read_frame_with_opencv
    samples: list[BenchmarkSample] = []

    for timestamp in timestamps:
        started = time.perf_counter()
        frame = frame_reader(source, timestamp)
        if frame is None:
            raise ValueError("source timestamp could not be read")
        detections = tuple(detector.detect(frame))
        usable_embeddings = sum(
            embedder.embed(frame, detection.box) is not None for detection in detections
        )
        elapsed = time.perf_counter() - started
        samples.append(
            BenchmarkSample(
                timestamp_seconds=timestamp,
                detected_people=len(detections),
                usable_embeddings=usable_embeddings,
                elapsed_seconds=elapsed,
            )
        )
        del frame, detections

    return BenchmarkReport(tuple(samples))
