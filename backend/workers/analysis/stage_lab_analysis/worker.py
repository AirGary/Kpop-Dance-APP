from __future__ import annotations

from pathlib import Path
from dataclasses import replace
from typing import Callable, Iterable, Protocol

from .candidates import CandidateExtractor, CandidateSet
from .detection import Detection, PersonDetector
from .tracking import ByteTrackPersonTracker


class FrameReader(Protocol):
    def __call__(self, proxy: Path) -> Iterable[tuple[float, object, int, int]]: ...


def _opencv_frames(proxy: Path, frame_stride: int = 1):
    if frame_stride < 1:
        raise ValueError("frame stride must be positive")
    try:
        import cv2
    except ImportError as error:
        raise RuntimeError("OpenCV is required for candidate extraction") from error
    capture = cv2.VideoCapture(str(proxy))
    if not capture.isOpened():
        raise RuntimeError("analysis proxy could not be opened")
    try:
        fps = capture.get(cv2.CAP_PROP_FPS) or 30.0
        frame_index = 0
        while True:
            success, frame = capture.read()
            if not success:
                break
            if frame_index % frame_stride == 0:
                height, width = frame.shape[:2]
                yield frame_index / fps, frame, width, height
            frame_index += 1
    finally:
        capture.release()


class AnalysisWorker:
    def __init__(
        self,
        *,
        detector: PersonDetector,
        frame_reader: FrameReader = _opencv_frames,
        tracker: ByteTrackPersonTracker | None = None,
        candidate_extractor: CandidateExtractor | None = None,
        frame_stride: int = 1,
    ) -> None:
        self.detector = detector
        self.frame_reader = frame_reader
        self.tracker = tracker or ByteTrackPersonTracker()
        self.candidate_extractor = candidate_extractor or CandidateExtractor()
        if frame_stride < 1:
            raise ValueError("frame stride must be positive")
        self.frame_stride = frame_stride

    def detect_candidates(self, workspace: Path) -> CandidateSet:
        proxy = workspace / "proxy.mp4" if workspace.name == "analysis" else workspace / "analysis" / "proxy.mp4"
        if not proxy.is_file():
            raise FileNotFoundError("analysis proxy is missing")
        frame_samples: dict[int, list[tuple[float, object, object]]] = {}
        reader = self.frame_reader
        try:
            frames = reader(proxy, self.frame_stride)  # type: ignore[call-arg]
        except TypeError:
            frames = reader(proxy)
        for time_seconds, frame, _, _ in frames:
            detections = tuple(
                Detection(time_seconds, detection.box, detection.confidence)
                for detection in self.detector.detect(frame)
            )
            tracks = self.tracker.update(detections)
            for track in tracks:
                if track.samples and track.last_sample.time_seconds == time_seconds:
                    frame_samples.setdefault(track.track_id, []).append(
                        (time_seconds, frame, track.last_sample.box)
                    )
        analysis_directory = proxy.parent
        candidate_directory = analysis_directory / "candidates"
        candidate_directory.mkdir(parents=True, exist_ok=True)
        extracted = self.candidate_extractor.extract(
            self.tracker.tracks,
            representative_path=lambda track_id, index: f"analysis/candidates/track-{track_id}-{index}.jpg",
        )
        candidates = type(extracted)(
            tuple(
                replace(
                    candidate,
                    representative_image_paths=tuple(
                        f"analysis/candidates/{candidate.candidate_id}-{index}.jpg"
                        for index in range(1, 4)
                    ),
                )
                for candidate in extracted.candidates
            )
        )
        for candidate in candidates.candidates:
            self._write_representatives(
                candidate,
                frame_samples.get(candidate.track_id, []),
                candidate_directory,
            )
        return candidates

    @staticmethod
    def _write_representatives(candidate, samples, directory: Path) -> None:
        """Write three temporally separated crops when the reader supplies image frames."""
        usable = [sample for sample in samples if hasattr(sample[1], "shape")]
        if not usable:
            return
        try:
            import cv2
        except ImportError as error:
            raise RuntimeError("OpenCV is required to write candidate images") from error
        selected = [usable[index * (len(usable) - 1) // 2] for index in range(3)]
        for index, (_, frame, box) in enumerate(selected, start=1):
            height, width = frame.shape[:2]
            padding_x = box.width * width * 0.12
            padding_y = box.height * height * 0.12
            left = max(0, int(box.x * width - padding_x))
            top = max(0, int(box.y * height - padding_y))
            right = min(width, int((box.x + box.width) * width + padding_x))
            bottom = min(height, int((box.y + box.height) * height + padding_y))
            crop = frame[top:bottom, left:right]
            success, encoded = cv2.imencode(".jpg", crop, [cv2.IMWRITE_JPEG_QUALITY, 90])
            if not success:
                raise RuntimeError("candidate image encoding failed")
            (directory / f"{candidate.candidate_id}-{index}.jpg").write_bytes(encoded.tobytes())
