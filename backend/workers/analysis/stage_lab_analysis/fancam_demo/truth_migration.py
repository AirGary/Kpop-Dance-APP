from __future__ import annotations

from dataclasses import dataclass
import json
import math
import os
from pathlib import Path
import re

from .truth import GroundTruthScene, GroundTruthSet


_CANDIDATE_ID = re.compile(r"candidate-(?:0[1-9]|[1-9][0-9]+)\Z")
_STABLE_MEMBER_ID = re.compile(r"member-(?:0[1-9]|[1-9][0-9]+)\Z")


@dataclass(frozen=True, slots=True)
class LegacyTruthScene:
    timestamp_seconds: float
    candidate_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        timestamp = _timestamp(self.timestamp_seconds)
        candidate_ids = tuple(self.candidate_ids)
        if any(
            not isinstance(candidate_id, str)
            or _CANDIDATE_ID.fullmatch(candidate_id) is None
            for candidate_id in candidate_ids
        ):
            raise ValueError("candidate_ids must contain candidate IDs")
        if len(set(candidate_ids)) != len(candidate_ids):
            raise ValueError("candidate_ids must contain unique candidate IDs")
        object.__setattr__(self, "timestamp_seconds", timestamp)
        object.__setattr__(self, "candidate_ids", candidate_ids)


def _timestamp(value: object) -> float:
    if isinstance(value, bool):
        raise ValueError("timestamp_seconds must be finite and non-negative")
    try:
        timestamp = float(value)
    except (TypeError, ValueError, OverflowError) as error:
        raise ValueError("timestamp_seconds must be finite and non-negative") from error
    if not math.isfinite(timestamp) or timestamp < 0:
        raise ValueError("timestamp_seconds must be finite and non-negative")
    return timestamp


def load_legacy_truth(path: Path) -> tuple[LegacyTruthScene, ...]:
    try:
        payload = json.loads(
            Path(path).read_text(encoding="utf-8"),
            parse_constant=lambda _: (_ for _ in ()).throw(ValueError()),
        )
    except (OSError, json.JSONDecodeError, ValueError) as error:
        raise ValueError("legacy truth file is unreadable") from error
    if not isinstance(payload, dict) or set(payload) != {"schemaVersion", "scenes"}:
        raise ValueError("legacy truth schema contains unsupported fields")
    if payload["schemaVersion"] != 1 or not isinstance(payload["scenes"], list):
        raise ValueError("legacy truth schema is unsupported")

    scenes: list[LegacyTruthScene] = []
    for raw_scene in payload["scenes"]:
        if not isinstance(raw_scene, dict) or set(raw_scene) != {
            "timestampSeconds",
            "visibleMemberIds",
        }:
            raise ValueError("legacy truth scene contains unsupported fields")
        candidate_ids = raw_scene["visibleMemberIds"]
        if not isinstance(candidate_ids, list) or not all(
            isinstance(candidate_id, str) for candidate_id in candidate_ids
        ):
            raise ValueError("legacy candidate IDs must be an array of strings")
        scenes.append(
            LegacyTruthScene(raw_scene["timestampSeconds"], tuple(candidate_ids))
        )
    return tuple(scenes)


def convert_scene_member_ids(
    legacy_scenes: tuple[LegacyTruthScene, ...],
    scene_member_ids: tuple[tuple[str, ...], ...],
) -> GroundTruthSet:
    assignments = tuple(tuple(member_ids) for member_ids in scene_member_ids)
    if len(legacy_scenes) != len(assignments):
        raise ValueError("scene assignments must align with legacy scenes")
    if any(
        len(scene.candidate_ids) != len(member_ids)
        for scene, member_ids in zip(legacy_scenes, assignments)
    ):
        raise ValueError("scene assignments must align with legacy scenes")
    return GroundTruthSet(
        tuple(
            GroundTruthScene(
                scene.timestamp_seconds,
                member_ids,
            )
            for scene, member_ids in zip(legacy_scenes, assignments)
        )
    )


def write_stable_truth_exclusive(truth: GroundTruthSet, destination: Path) -> None:
    payload = json.dumps(
        {
            "schemaVersion": 1,
            "scenes": [
                {
                    "timestampSeconds": scene.timestamp_seconds,
                    "visibleMemberIds": list(scene.visible_member_ids),
                }
                for scene in truth.scenes
            ],
        },
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    destination = Path(destination)
    descriptor: int | None = None
    created = False
    try:
        descriptor = os.open(destination, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        created = True
        with os.fdopen(descriptor, "wb") as output:
            descriptor = None
            output.write(payload)
    except BaseException:
        if descriptor is not None:
            os.close(descriptor)
        if created:
            destination.unlink(missing_ok=True)
        raise


def _move_exclusive(source: Path, destination: Path) -> None:
    os.link(source, destination)
    try:
        source.unlink()
    except BaseException:
        destination.unlink(missing_ok=True)
        raise


def migrate_legacy_truth(
    legacy_path: Path,
    backup_path: Path,
    destination: Path,
    truth: GroundTruthSet,
) -> GroundTruthSet:
    legacy_path = Path(legacy_path)
    backup_path = Path(backup_path)
    destination = Path(destination)
    if not isinstance(truth, GroundTruthSet):
        raise TypeError("truth must be a GroundTruthSet")
    if destination.exists() and destination != legacy_path:
        raise FileExistsError("migration destination already exists")
    _move_exclusive(legacy_path, backup_path)
    try:
        write_stable_truth_exclusive(truth, destination)
    except BaseException:
        _move_exclusive(backup_path, legacy_path)
        raise
    return truth
