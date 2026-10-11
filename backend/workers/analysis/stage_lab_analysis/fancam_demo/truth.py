from __future__ import annotations

from dataclasses import dataclass
import json
import math
from pathlib import Path
import re


GROUND_TRUTH_FILE_NAME = "fancam-demo-ground-truth.local.json"
GROUND_TRUTH_SCHEMA_VERSION = 1
MIN_SCENE_COUNT = 30
MAX_SCENE_COUNT = 50
_STABLE_MEMBER_ID = re.compile(r"member-(?:0[1-9]|[1-9][0-9]+)\Z")


def _timestamp(value: object) -> float:
    if isinstance(value, bool):
        raise ValueError("timestamp_seconds must be finite and non-negative")
    try:
        result = float(value)
    except (TypeError, ValueError, OverflowError) as error:
        raise ValueError("timestamp_seconds must be finite and non-negative") from error
    if not math.isfinite(result) or result < 0:
        raise ValueError("timestamp_seconds must be finite and non-negative")
    return result


def _member_ids(values: tuple[str, ...], field_name: str) -> tuple[str, ...]:
    for member_id in values:
        if (
            not isinstance(member_id, str)
            or not member_id
            or member_id != member_id.strip()
            or "/" in member_id
            or "\\" in member_id
        ):
            raise ValueError(f"{field_name} must contain non-empty opaque member IDs")
    if len(set(values)) != len(values):
        raise ValueError(f"{field_name} must contain unique member IDs")
    return values


def _stable_member_ids(values: tuple[str, ...], field_name: str) -> tuple[str, ...]:
    for member_id in values:
        if not isinstance(member_id, str) or _STABLE_MEMBER_ID.fullmatch(member_id) is None:
            raise ValueError(
                f"{field_name} must contain stable anonymous member IDs"
            )
    if len(set(values)) != len(values):
        raise ValueError(f"{field_name} must contain unique stable anonymous member IDs")
    return values


@dataclass(frozen=True, slots=True)
class GroundTruthScene:
    timestamp_seconds: float
    visible_member_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "timestamp_seconds", _timestamp(self.timestamp_seconds))
        object.__setattr__(
            self,
            "visible_member_ids",
            _stable_member_ids(tuple(self.visible_member_ids), "visible_member_ids"),
        )


@dataclass(frozen=True, slots=True)
class PersonAssignment:
    runtime_candidate_id: str
    stable_member_id: str | None
    confirmed: bool
    confirmation_requested: bool

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "runtime_candidate_id",
            _member_ids((self.runtime_candidate_id,), "runtime_candidate_id")[0],
        )
        if self.stable_member_id is not None:
            object.__setattr__(
                self,
                "stable_member_id",
                _stable_member_ids(
                    (self.stable_member_id,), "stable_member_id"
                )[0],
            )
        if not isinstance(self.confirmed, bool):
            raise ValueError("confirmed must be a boolean")
        if not isinstance(self.confirmation_requested, bool):
            raise ValueError("confirmation_requested must be a boolean")


@dataclass(frozen=True, slots=True, init=False)
class SceneObservation:
    timestamp_seconds: float
    assignments: tuple[PersonAssignment, ...]

    def __init__(
        self,
        timestamp_seconds: float,
        assignments: tuple[PersonAssignment, ...] | None = None,
        assigned_member_id: str | None = None,
        confirmation_requested: bool = False,
        *,
        detected_member_ids: tuple[str, ...] | None = None,
    ) -> None:
        """Store runtime-only person assignments for one evaluated timestamp.

        The keyword-only legacy inputs preserve compatibility for the existing
        runner until it emits person assignments directly.
        """

        object.__setattr__(self, "timestamp_seconds", _timestamp(timestamp_seconds))
        if assignments is not None:
            if detected_member_ids is not None or assigned_member_id is not None:
                raise ValueError("assignments cannot be combined with legacy fields")
            if not isinstance(confirmation_requested, bool):
                raise ValueError("confirmation_requested must be a boolean")
            normalized_assignments = tuple(assignments)
        else:
            if not isinstance(confirmation_requested, bool):
                raise ValueError("confirmation_requested must be a boolean")
            legacy_detected_member_ids = _stable_member_ids(
                tuple(detected_member_ids or ()), "detected_member_ids"
            )
            if assigned_member_id is not None:
                assigned_member_id = _stable_member_ids(
                    (assigned_member_id,), "assigned_member_id"
                )[0]
                normalized_assignments = (
                    PersonAssignment(
                        "legacy-runtime-0",
                        assigned_member_id,
                        True,
                        confirmation_requested,
                    ),
                )
            elif legacy_detected_member_ids:
                normalized_assignments = tuple(
                    PersonAssignment(
                        f"legacy-runtime-{index}",
                        member_id,
                        False,
                        confirmation_requested,
                    )
                    for index, member_id in enumerate(legacy_detected_member_ids)
                )
            elif confirmation_requested:
                normalized_assignments = (
                    PersonAssignment("legacy-runtime-unmapped", None, False, True),
                )
            else:
                normalized_assignments = ()

        if not all(
            isinstance(assignment, PersonAssignment)
            for assignment in normalized_assignments
        ):
            raise TypeError("assignments must contain PersonAssignment values")
        runtime_candidate_ids = tuple(
            assignment.runtime_candidate_id for assignment in normalized_assignments
        )
        if len(set(runtime_candidate_ids)) != len(runtime_candidate_ids):
            raise ValueError("assignments must contain unique runtime candidate IDs")
        object.__setattr__(self, "assignments", normalized_assignments)


@dataclass(frozen=True, slots=True)
class GroundTruthSet:
    scenes: tuple[GroundTruthScene, ...]

    def __post_init__(self) -> None:
        scenes = tuple(self.scenes)
        if not MIN_SCENE_COUNT <= len(scenes) <= MAX_SCENE_COUNT:
            raise ValueError("ground truth must contain between 30 and 50 scenes")
        if not all(isinstance(scene, GroundTruthScene) for scene in scenes):
            raise TypeError("scenes must contain GroundTruthScene values")
        timestamps = tuple(scene.timestamp_seconds for scene in scenes)
        if any(left >= right for left, right in zip(timestamps, timestamps[1:])):
            raise ValueError("ground truth scene timestamps must be strictly increasing")
        object.__setattr__(self, "scenes", scenes)


def _load_json(path: Path) -> object:
    try:
        text = path.read_text(encoding="utf-8")
        return json.loads(text, parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
    except (OSError, json.JSONDecodeError, ValueError) as error:
        raise ValueError("ground truth file is unreadable") from error


def load_ground_truth(path: Path) -> GroundTruthSet:
    path = Path(path)
    if path.name != GROUND_TRUTH_FILE_NAME:
        raise ValueError("ground truth must use the ignored local filename")
    payload = _load_json(path)
    if not isinstance(payload, dict) or set(payload) != {"schemaVersion", "scenes"}:
        raise ValueError("ground truth schema contains unsupported fields")
    if payload["schemaVersion"] != GROUND_TRUTH_SCHEMA_VERSION:
        raise ValueError("ground truth schema version is unsupported")
    raw_scenes = payload["scenes"]
    if not isinstance(raw_scenes, list):
        raise ValueError("ground truth scenes must be an array")

    scenes: list[GroundTruthScene] = []
    for raw_scene in raw_scenes:
        if not isinstance(raw_scene, dict) or set(raw_scene) != {
            "timestampSeconds",
            "visibleMemberIds",
        }:
            raise ValueError("ground truth scene contains unsupported fields")
        visible_ids = raw_scene["visibleMemberIds"]
        if not isinstance(visible_ids, list) or not all(
            isinstance(member_id, str) for member_id in visible_ids
        ):
            raise ValueError("visibleMemberIds must be an array of strings")
        scenes.append(
            GroundTruthScene(
                timestamp_seconds=raw_scene["timestampSeconds"],
                visible_member_ids=tuple(visible_ids),
            )
        )
    return GroundTruthSet(tuple(scenes))
