from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
import hashlib
import math
from pathlib import Path
from typing import Any

from .detection import NormalizedBox
from .runtime_probe import ModelManifestError


@dataclass(frozen=True, slots=True)
class PersonEmbedding:
    """A finite, L2-normalized whole-person appearance descriptor."""

    values: tuple[float, ...]
    quality: float

    def __post_init__(self) -> None:
        if not self.values or not all(math.isfinite(value) for value in self.values):
            raise ValueError("embedding values must be finite and non-empty")
        if not math.isfinite(self.quality) or not 0.0 <= self.quality <= 1.0:
            raise ValueError("embedding quality must be between 0 and 1")
        norm_squared = sum(value * value for value in self.values)
        if not math.isclose(norm_squared, 1.0, rel_tol=1e-6, abs_tol=1e-6):
            raise ValueError("embedding values must be L2-normalized")


def cosine_similarity(first: PersonEmbedding, second: PersonEmbedding) -> float:
    if len(first.values) != len(second.values):
        raise ValueError("embedding dimensions must match")
    return max(-1.0, min(1.0, sum(left * right for left, right in zip(first.values, second.values))))


class OpenVINOReIDEmbedder:
    """Hash-gated adapter for OpenVINO person-reidentification-retail-0277."""

    def __init__(
        self,
        *,
        model_xml: Path | str,
        model_bin: Path | str,
        expected_xml_sha256: str,
        expected_bin_sha256: str,
        device: str = "CPU",
        infer: Callable[[Any], Sequence[float]] | None = None,
        min_width: int = 16,
        min_height: int = 32,
        min_quality: float = 0.03,
    ) -> None:
        if device.upper() != "CPU":
            raise ValueError("OpenVINO Re-ID supports only the CPU device")
        self._model_xml = Path(model_xml)
        self._model_bin = Path(model_bin)
        self._expected_xml_sha256 = expected_xml_sha256
        self._expected_bin_sha256 = expected_bin_sha256
        self._device = "CPU"
        self._provided_infer = infer
        self._inference: Callable[[Any], Sequence[float]] | None = None
        self._min_width = min_width
        self._min_height = min_height
        self._min_quality = min_quality

    def embed(self, frame: Any, box: NormalizedBox) -> PersonEmbedding | None:
        crop = _crop(frame, box)
        if crop is None or crop.shape[1] < self._min_width or crop.shape[0] < self._min_height:
            return None
        quality = _quality(crop)
        if quality < self._min_quality:
            return None

        try:
            values = tuple(
                float(value) for value in self._load_inference()(_prepare(crop))
            )
            norm = math.sqrt(sum(value * value for value in values))
        except ModelManifestError:
            raise
        except Exception:
            return None
        if not math.isfinite(norm) or norm <= 0.0:
            return None
        return PersonEmbedding(tuple(value / norm for value in values), quality)

    def _load_inference(self) -> Callable[[Any], Sequence[float]]:
        if self._inference is None:
            _verify_asset(self._model_xml, self._expected_xml_sha256)
            _verify_asset(self._model_bin, self._expected_bin_sha256)
            self._inference = self._provided_infer or self._openvino_inference()
        return self._inference

    def _openvino_inference(self) -> Callable[[Any], Sequence[float]]:
        try:
            from openvino import Core
        except ImportError as error:
            raise RuntimeError("OpenVINO dependencies are not installed") from error

        core = Core()
        model = core.read_model(model=str(self._model_xml), weights=str(self._model_bin))
        compiled_model = core.compile_model(model, self._device)

        def infer(batch: Any) -> Sequence[float]:
            result = compiled_model([batch])
            return next(iter(result.values())).reshape(-1)

        return infer


def _verify_asset(path: Path, expected_sha256: str) -> None:
    if not path.is_file():
        raise ModelManifestError(f"model asset is missing: {path.name}")
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    if digest != expected_sha256:
        raise ModelManifestError(f"model asset checksum mismatch: {path.name}")


def _crop(frame: Any, box: NormalizedBox):
    import numpy as np

    image = np.asarray(frame)
    if image.ndim != 3 or image.shape[2] < 3 or image.shape[0] <= 0 or image.shape[1] <= 0:
        return None
    height, width = image.shape[:2]
    left = max(0, min(width, math.floor(box.x * width)))
    top = max(0, min(height, math.floor(box.y * height)))
    right = max(left, min(width, math.ceil((box.x + box.width) * width)))
    bottom = max(top, min(height, math.ceil((box.y + box.height) * height)))
    return image[top:bottom, left:right, :3]


def _quality(crop: Any) -> float:
    import numpy as np

    gray = np.asarray(crop, dtype=np.float32).mean(axis=2)
    if gray.shape[0] < 2 or gray.shape[1] < 2 or not bool(np.isfinite(gray).all()):
        return 0.0
    horizontal = np.diff(gray, axis=1)
    vertical = np.diff(gray, axis=0)
    focus = float(np.var(horizontal) + np.var(vertical))
    return min(1.0, focus / 2048.0)


def _prepare(crop: Any):
    import cv2
    import numpy as np

    resized = cv2.resize(crop, (128, 256), interpolation=cv2.INTER_LINEAR)
    return np.ascontiguousarray(resized.transpose(2, 0, 1)[None, ...], dtype=np.float32)
