from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import tempfile
import zipfile


REQUIRED_MEMBERS = (
    "confidence.json",
    "manifest.json",
    "pose-track.json",
    "spotlight-track.json",
    "timeline.json",
)


class AnalysisPackageError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class PackageInputs:
    manifest: dict
    spotlight: list[dict]
    pose: list[dict]
    timeline: list[dict]
    confidence: list[dict]


@dataclass(frozen=True, slots=True)
class PackageArtifact:
    path: Path
    sha256: str
    byte_count: int


def write_analysis_package(destination: Path, inputs: PackageInputs) -> PackageArtifact:
    if any("/" in str(key) or ".." in str(key) for key in inputs.manifest):
        raise AnalysisPackageError("manifest contains unsafe member")
    payloads = {
        "confidence.json": inputs.confidence,
        "pose-track.json": inputs.pose,
        "spotlight-track.json": inputs.spotlight,
        "timeline.json": inputs.timeline,
    }
    hashes = {name: _digest_json(value) for name, value in payloads.items()}
    manifest = dict(inputs.manifest)
    manifest["memberHashes"] = hashes
    payloads["manifest.json"] = manifest
    destination.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{destination.name}.", suffix=".tmp", dir=destination.parent)
    os.close(descriptor)
    Path(temporary_name).unlink(missing_ok=True)
    temporary = Path(temporary_name)
    try:
        # Keep the tiny JSON package uncompressed so the iOS client can parse it
        # without shipping a third-party ZIP/DEFLATE dependency.
        with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_STORED) as archive:
            for name in REQUIRED_MEMBERS:
                info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
                info.compress_type = zipfile.ZIP_STORED
                archive.writestr(info, _json_bytes(payloads[name]))
        temporary.replace(destination)
    finally:
        temporary.unlink(missing_ok=True)
    return _artifact(destination)


def validate_analysis_package(path: Path) -> PackageArtifact:
    try:
        with zipfile.ZipFile(path) as archive:
            names = tuple(sorted(archive.namelist()))
            if names != REQUIRED_MEMBERS:
                raise AnalysisPackageError("package members are invalid")
            content = {name: archive.read(name) for name in REQUIRED_MEMBERS}
    except (OSError, zipfile.BadZipFile, KeyError) as error:
        raise AnalysisPackageError("package is unreadable") from error
    manifest = json.loads(content["manifest.json"])
    expected = manifest.get("memberHashes", {})
    for name in REQUIRED_MEMBERS:
        if name == "manifest.json":
            continue
        if expected.get(name) != hashlib.sha256(content[name]).hexdigest():
            raise AnalysisPackageError("package member hash mismatch")
    return _artifact(path)


def _json_bytes(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True) + "\n").encode("utf-8")


def _digest_json(value: object) -> str:
    return hashlib.sha256(_json_bytes(value)).hexdigest()


def _artifact(path: Path) -> PackageArtifact:
    data = path.read_bytes()
    return PackageArtifact(path, hashlib.sha256(data).hexdigest(), len(data))
