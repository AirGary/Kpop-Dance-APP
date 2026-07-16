from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import time
import urllib.request
from collections.abc import Callable, Sequence
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Literal, TypeAlias


Device: TypeAlias = Literal["mps", "cpu"]
ModelProbe: TypeAlias = Callable[[str, Device], bool]
REQUIRED_MODEL_FIELDS = (
    "name",
    "sourceUrl",
    "sha256",
    "license",
    "licenseUrl",
)
APPROVED_MODEL_LICENSES = frozenset({"Apache-2.0"})


class RuntimeProbeError(RuntimeError):
    """Raised when no supported inference device passes the real probe."""


class PythonVersionError(RuntimeProbeError):
    """Raised when the worker is not running under Python 3.11."""


class ModelManifestError(RuntimeProbeError):
    """Raised when model provenance is incomplete or malformed."""


@dataclass(frozen=True, slots=True)
class RuntimeCapabilities:
    device: Device
    detector_ready: bool
    pose_ready: bool
    ffmpeg_version: str


def require_python_311(version_info: Sequence[int]) -> None:
    if tuple(version_info[:2]) != (3, 11):
        raise PythonVersionError("Stage Lab local AI requires Python 3.11.x")


def load_model_manifest(path: Path) -> dict[str, object]:
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ModelManifestError("model manifest is unreadable") from error

    models = manifest.get("models") if isinstance(manifest, dict) else None
    if not isinstance(models, list) or not models:
        raise ModelManifestError("model manifest requires a non-empty models list")

    for index, model in enumerate(models):
        if not isinstance(model, dict):
            raise ModelManifestError(f"models[{index}] must be an object")
        for field in REQUIRED_MODEL_FIELDS:
            value = model.get(field)
            if not isinstance(value, str) or not value.strip():
                raise ModelManifestError(f"models[{index}] requires {field}")
        sha256 = model["sha256"]
        if len(sha256) != 64 or any(character not in "0123456789abcdef" for character in sha256.lower()):
            raise ModelManifestError(f"models[{index}] sha256 must be 64 hexadecimal characters")
        if model["license"] not in APPROVED_MODEL_LICENSES:
            raise ModelManifestError(
                f"models[{index}] requires an approved commercial license"
            )

    return manifest


def _probe_device(device: Device, probe: ModelProbe) -> bool:
    return probe("detector", device) and probe("pose", device)


def choose_device(*, mps_available: bool, probe: ModelProbe) -> Device:
    if mps_available and _probe_device("mps", probe):
        return "mps"
    if _probe_device("cpu", probe):
        return "cpu"
    raise RuntimeProbeError("detector and pose probes failed on all supported devices")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def resolve_model_config(
    model: dict[str, object],
    *,
    model_root: Path,
    package_root: Path | None = None,
) -> Path:
    package_path = model.get("packageConfigPath")
    if package_path is not None:
        if package_root is None:
            raise ModelManifestError("package root is required for packageConfigPath")
        config = package_root / str(package_path)
    else:
        config = model_root / str(model["configLocalPath"])

    if not config.is_file():
        raise ModelManifestError(f"model config is missing: {config.name}")
    if _sha256(config) != str(model["configSha256"]):
        raise ModelManifestError(f"model config checksum mismatch: {config.name}")
    return config


def resolve_model_checkpoint(
    model: dict[str, object],
    *,
    model_root: Path,
) -> Path:
    checkpoint = model_root / str(model["localPath"])
    if not checkpoint.is_file():
        raise ModelManifestError(f"model checkpoint is missing: {checkpoint.name}")
    if _sha256(checkpoint) != str(model["sha256"]):
        raise ModelManifestError(
            f"checkpoint checksum mismatch: {checkpoint.name}"
        )
    return checkpoint


def validate_detector_boxes(boxes) -> None:
    import numpy as np

    if boxes.ndim != 2 or boxes.shape[-1] != 4:
        raise RuntimeProbeError("detector returned an invalid bounding-box tensor")
    if boxes.shape[0] == 0:
        raise RuntimeProbeError("detector returned no bounding boxes")
    if not bool(np.isfinite(boxes.detach().cpu().numpy() if hasattr(boxes, "detach") else boxes).all()):
        raise RuntimeProbeError("detector returned non-finite bounding boxes")


@contextmanager
def trusted_checkpoint_loading(checkpoint: Path, expected_sha256: str):
    if _sha256(checkpoint) != expected_sha256:
        raise ModelManifestError(f"checkpoint checksum mismatch: {checkpoint.name}")

    import torch

    original_load = torch.load
    trusted_path = checkpoint.resolve()

    def verified_load(filename, *args, **kwargs):
        try:
            candidate = Path(filename).resolve()
        except TypeError:
            candidate = None
        if candidate == trusted_path:
            if _sha256(checkpoint) != expected_sha256:
                raise ModelManifestError(
                    f"checkpoint checksum mismatch: {checkpoint.name}"
                )
            kwargs.setdefault("weights_only", False)
        return original_load(filename, *args, **kwargs)

    torch.load = verified_load
    try:
        yield
    finally:
        torch.load = original_load


def _download_verified(url: str, destination: Path, expected_sha256: str) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.is_file() and _sha256(destination) == expected_sha256:
        return

    temporary = destination.with_suffix(f"{destination.suffix}.download")
    try:
        with urllib.request.urlopen(url, timeout=60) as response, temporary.open("wb") as file:
            while chunk := response.read(1024 * 1024):
                file.write(chunk)
        actual_sha256 = _sha256(temporary)
        if actual_sha256 != expected_sha256:
            raise ModelManifestError(
                f"checksum mismatch for {destination.name}: {actual_sha256}"
            )
        temporary.replace(destination)
    finally:
        temporary.unlink(missing_ok=True)


def download_manifest_assets(manifest_path: Path, model_root: Path) -> None:
    manifest = load_model_manifest(manifest_path)
    for model in manifest["models"]:
        assert isinstance(model, dict)
        _download_verified(
            str(model["sourceUrl"]),
            model_root / str(model["localPath"]),
            str(model["sha256"]),
        )
        _download_verified(
            str(model["configUrl"]),
            model_root / str(model["configLocalPath"]),
            str(model["configSha256"]),
        )


def _ffmpeg_version() -> str:
    result = subprocess.run(
        ["ffmpeg", "-version"],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.splitlines()[0]


def _is_supported_mps_failure(error: Exception) -> bool:
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


class OpenMMLabProbe:
    def __init__(self, manifest_path: Path, model_root: Path) -> None:
        manifest = load_model_manifest(manifest_path)
        self._models = {
            str(model["role"]): model
            for model in manifest["models"]
            if isinstance(model, dict)
        }
        self._model_root = model_root

    def __call__(self, model_name: str, device: Device) -> bool:
        try:
            if model_name == "detector":
                self._probe_detector(device)
            elif model_name == "pose":
                self._probe_pose(device)
            else:
                raise RuntimeProbeError(f"unknown probe model: {model_name}")
        except Exception as error:
            if device == "mps" and _is_supported_mps_failure(error):
                return False
            raise RuntimeProbeError(
                f"{model_name} probe failed on {device}: {type(error).__name__}: {error}"
            ) from error
        return True

    def _paths(self, role: str) -> tuple[Path, Path]:
        try:
            model = self._models[role]
        except KeyError as error:
            raise ModelManifestError(f"model manifest requires role {role}") from error
        package_root = None
        if model.get("packageConfigPath") is not None:
            if role != "pose":
                raise ModelManifestError(
                    f"unsupported package config provider for role {role}"
                )
            import mmpose

            package_root = Path(mmpose.__file__).resolve().parent
        return (
            resolve_model_config(
                model,
                model_root=self._model_root,
                package_root=package_root,
            ),
            resolve_model_checkpoint(model, model_root=self._model_root),
        )

    @staticmethod
    def _test_frame():
        import numpy as np

        frame = np.zeros((640, 640, 3), dtype=np.uint8)
        frame[80:600, 160:480] = (96, 160, 224)
        return frame

    def _probe_detector(self, device: Device) -> None:
        from mmdet.apis import inference_detector, init_detector

        config, checkpoint = self._paths("detector")
        model = init_detector(str(config), str(checkpoint), device=device)
        result = inference_detector(model, self._test_frame())
        boxes = result.pred_instances.bboxes
        validate_detector_boxes(boxes)

    def _probe_pose(self, device: Device) -> None:
        import numpy as np
        from mmpose.apis import inference_topdown, init_model

        config, checkpoint = self._paths("pose")
        pose_model = self._models["pose"]
        with trusted_checkpoint_loading(checkpoint, str(pose_model["sha256"])):
            model = init_model(str(config), str(checkpoint), device=device)
        boxes = np.array([[160.0, 80.0, 480.0, 600.0]], dtype=np.float32)
        results = inference_topdown(model, self._test_frame(), boxes, bbox_format="xyxy")
        if not results:
            raise RuntimeProbeError("pose estimator returned no sample")
        keypoints = results[0].pred_instances.keypoints
        if keypoints.ndim != 3 or keypoints.shape[-1] != 2:
            raise RuntimeProbeError("pose estimator returned an invalid keypoint tensor")


def run_real_probe(manifest_path: Path, model_root: Path) -> dict[str, object]:
    require_python_311(sys.version_info)
    try:
        import torch
    except ImportError as error:
        raise RuntimeProbeError("PyTorch is not installed in the local AI environment") from error

    started_at = time.monotonic()
    probe = OpenMMLabProbe(manifest_path, model_root)
    device = choose_device(
        mps_available=torch.backends.mps.is_available(),
        probe=probe,
    )
    capabilities = RuntimeCapabilities(
        device=device,
        detector_ready=True,
        pose_ready=True,
        ffmpeg_version=_ffmpeg_version(),
    )
    return {
        **asdict(capabilities),
        "pythonVersion": sys.version.split()[0],
        "torchVersion": torch.__version__,
        "elapsedSeconds": round(time.monotonic() - started_at, 3),
    }


def _main() -> int:
    parser = argparse.ArgumentParser(description="Verify the Stage Lab local AI runtime")
    parser.add_argument("command", choices=("download", "probe"))
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--model-root", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    arguments = parser.parse_args()

    require_python_311(sys.version_info)
    if arguments.command == "download":
        download_manifest_assets(arguments.manifest, arguments.model_root)
        return 0

    if arguments.output is None:
        parser.error("probe requires --output")
    result = run_real_probe(arguments.manifest, arguments.model_root)
    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    temporary = arguments.output.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(arguments.output)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
