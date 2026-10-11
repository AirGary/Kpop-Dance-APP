from __future__ import annotations

from dataclasses import dataclass, replace
import json
import math
from pathlib import Path
import re
from collections.abc import Mapping
from typing import Literal

from ..detection import Detection
from ..reid import PersonEmbedding, cosine_similarity
from .truth import GroundTruthScene, GroundTruthSet


PROPOSAL_FILE_NAME = "fancam-demo-ground-truth.proposed.local.json"
PROPOSAL_SCHEMA_VERSION = 1
MIN_SCENE_COUNT = 30
MAX_SCENE_COUNT = 50
ProposalConfidence = Literal["high", "review"]
_CANDIDATE_ID = re.compile(r"candidate-(?:0[1-9]|[1-9][0-9]+)\Z")
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


def _candidate_ids(values: tuple[str, ...]) -> tuple[str, ...]:
    for candidate_id in values:
        if (
            not isinstance(candidate_id, str)
            or not candidate_id
            or candidate_id != candidate_id.strip()
            or _CANDIDATE_ID.fullmatch(candidate_id) is None
        ):
            raise ValueError(
                "candidate_ids must match candidate-<zero-padded positive integer>"
            )
    if len(set(values)) != len(values):
        raise ValueError("candidate_ids must contain unique opaque IDs")
    return values


@dataclass(frozen=True, slots=True)
class ProposalScene:
    timestamp_seconds: float
    candidate_ids: tuple[str, ...]
    confidence: ProposalConfidence
    accepted: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "timestamp_seconds", _timestamp(self.timestamp_seconds))
        object.__setattr__(
            self, "candidate_ids", _candidate_ids(tuple(self.candidate_ids))
        )
        if self.confidence not in ("high", "review"):
            raise ValueError("confidence must be high or review")
        if not isinstance(self.accepted, bool):
            raise ValueError("accepted must be a boolean")


@dataclass(frozen=True, slots=True)
class ProposalSet:
    scenes: tuple[ProposalScene, ...]

    def __post_init__(self) -> None:
        scenes = tuple(self.scenes)
        if not MIN_SCENE_COUNT <= len(scenes) <= MAX_SCENE_COUNT:
            raise ValueError("proposal must contain between 30 and 50 scenes")
        if not all(isinstance(scene, ProposalScene) for scene in scenes):
            raise TypeError("scenes must contain ProposalScene values")
        timestamps = tuple(scene.timestamp_seconds for scene in scenes)
        if any(left >= right for left, right in zip(timestamps, timestamps[1:])):
            raise ValueError("proposal scene timestamps must be strictly increasing")
        object.__setattr__(self, "scenes", scenes)

    def to_json(self) -> dict[str, object]:
        return {
            "schemaVersion": PROPOSAL_SCHEMA_VERSION,
            "scenes": [
                {
                    "timestampSeconds": scene.timestamp_seconds,
                    "candidateIds": list(scene.candidate_ids),
                    "confidence": scene.confidence,
                    "accepted": scene.accepted,
                }
                for scene in self.scenes
            ],
        }


class CandidateRegistry:
    """Runtime-only anonymous Re-ID representatives for one proposal run."""

    __slots__ = ("_candidates", "_last_detection_count", "_next_candidate_number")

    def __init__(self) -> None:
        self._candidates: dict[str, PersonEmbedding | None] = {}
        self._last_detection_count: int | None = None
        self._next_candidate_number = 1

    def register(self, candidate_id: str, embedding: PersonEmbedding) -> None:
        _candidate_ids((candidate_id,))
        if not isinstance(embedding, PersonEmbedding):
            raise TypeError("embedding must be a PersonEmbedding")
        if candidate_id in self._candidates:
            raise ValueError("candidate ID is already registered")
        self._candidates[candidate_id] = embedding
        self._next_candidate_number = max(
            self._next_candidate_number,
            int(candidate_id.removeprefix("candidate-")) + 1,
        )

    def assign_or_register(
        self,
        embedding: PersonEmbedding | None,
        *,
        excluded_candidate_ids: frozenset[str] = frozenset(),
    ) -> tuple[str, float, float, bool]:
        if embedding is None:
            return self._register_new(None), 0.0, 0.0, False

        matches = tuple(
            (candidate_id, cosine_similarity(embedding, representative))
            for candidate_id, representative in self._candidates.items()
            if representative is not None and candidate_id not in excluded_candidate_ids
        )
        if not matches:
            return self._register_new(embedding), 0.0, 0.0, False

        candidate_id, score = max(matches, key=lambda match: match[1])
        runner_up = max(
            (candidate_score for other_id, candidate_score in matches if other_id != candidate_id),
            default=float("-inf"),
        )
        return candidate_id, score, score - runner_up, True

    def detection_count_changed(self, count: int) -> bool:
        changed = self._last_detection_count != count
        self._last_detection_count = count
        return changed

    def _register_new(self, embedding: PersonEmbedding | None) -> str:
        candidate_id = f"candidate-{self._next_candidate_number:02d}"
        self._next_candidate_number += 1
        self._candidates[candidate_id] = embedding
        return candidate_id


HIGH_SCORE = 0.90
HIGH_MARGIN = 0.08


def propose_scene(
    timestamp_seconds: float,
    detections: tuple[Detection, ...],
    embeddings: tuple[PersonEmbedding | None, ...],
    registry: CandidateRegistry,
) -> ProposalScene:
    if len(detections) != len(embeddings):
        raise ValueError("detections and embeddings must align")

    candidate_ids: list[str] = []
    confident = bool(detections) and not registry.detection_count_changed(len(detections))
    for embedding in embeddings:
        candidate_id, score, margin, known = registry.assign_or_register(
            embedding,
            excluded_candidate_ids=frozenset(candidate_ids),
        )
        candidate_ids.append(candidate_id)
        confident &= (
            known
            and embedding is not None
            and score >= HIGH_SCORE
            and margin >= HIGH_MARGIN
        )
    return ProposalScene(
        timestamp_seconds,
        tuple(candidate_ids),
        "high" if confident else "review",
    )


def _load_json(path: Path) -> object:
    try:
        text = path.read_text(encoding="utf-8")
        return json.loads(
            text,
            parse_constant=lambda _: (_ for _ in ()).throw(ValueError()),
        )
    except (OSError, json.JSONDecodeError, ValueError) as error:
        raise ValueError("proposal file is unreadable") from error


def load_proposal(path: Path) -> ProposalSet:
    path = Path(path)
    if path.name != PROPOSAL_FILE_NAME:
        raise ValueError("proposal must use the ignored local filename")
    payload = _load_json(path)
    if not isinstance(payload, dict) or set(payload) != {"schemaVersion", "scenes"}:
        raise ValueError("proposal schema contains unsupported fields")
    if payload["schemaVersion"] != PROPOSAL_SCHEMA_VERSION:
        raise ValueError("proposal schema version is unsupported")
    raw_scenes = payload["scenes"]
    if not isinstance(raw_scenes, list):
        raise ValueError("proposal scenes must be an array")

    scenes: list[ProposalScene] = []
    for raw_scene in raw_scenes:
        if not isinstance(raw_scene, dict) or set(raw_scene) != {
            "timestampSeconds",
            "candidateIds",
            "confidence",
            "accepted",
        }:
            raise ValueError("proposal scene contains unsupported fields")
        candidate_ids = raw_scene["candidateIds"]
        if not isinstance(candidate_ids, list) or not all(
            isinstance(candidate_id, str) for candidate_id in candidate_ids
        ):
            raise ValueError("candidateIds must be an array of strings")
        scenes.append(
            ProposalScene(
                timestamp_seconds=raw_scene["timestampSeconds"],
                candidate_ids=tuple(candidate_ids),
                confidence=raw_scene["confidence"],
                accepted=raw_scene["accepted"],
            )
        )
    return ProposalSet(tuple(scenes))


def load_local_proposal(project_root: Path) -> ProposalSet:
    """Load the sole production proposal location under a project root."""
    project_root = Path(project_root)
    return load_proposal(project_root / "docs" / PROPOSAL_FILE_NAME)


def apply_acceptance(
    proposal: ProposalSet,
    *,
    accept_high: bool,
    accept_review_timestamps: tuple[float, ...],
) -> ProposalSet:
    """Apply explicit local acceptance without changing AI provenance."""

    if not isinstance(accept_high, bool):
        raise ValueError("accept_high must be a boolean")
    review_timestamps = frozenset(
        _timestamp(timestamp) for timestamp in accept_review_timestamps
    )
    available_review_timestamps = frozenset(
        scene.timestamp_seconds
        for scene in proposal.scenes
        if scene.confidence == "review"
    )
    if not review_timestamps <= available_review_timestamps:
        raise ValueError("review timestamps must refer to review scenes")

    return ProposalSet(
        tuple(
            replace(
                scene,
                accepted=(
                    scene.accepted
                    or (accept_high and scene.confidence == "high")
                    or (
                        scene.confidence == "review"
                        and scene.timestamp_seconds in review_timestamps
                    )
                ),
            )
            for scene in proposal.scenes
        )
    )


def scrub_candidate_ids(proposal: ProposalSet) -> ProposalSet:
    """Retain review metadata while removing runtime-only candidate IDs."""
    return ProposalSet(
        tuple(replace(scene, candidate_ids=()) for scene in proposal.scenes)
    )


def accepted_truth(
    proposal: ProposalSet, stable_member_ids_by_candidate: Mapping[str, str]
) -> GroundTruthSet:
    if any(not scene.accepted for scene in proposal.scenes):
        raise ValueError("only accepted proposals can become truth")
    if not isinstance(stable_member_ids_by_candidate, Mapping):
        raise ValueError("stable member IDs must be supplied as a mapping")

    candidate_ids = tuple(
        dict.fromkeys(
            candidate_id
            for scene in proposal.scenes
            for candidate_id in scene.candidate_ids
        )
    )
    expected_candidates = frozenset(candidate_ids)
    supplied_candidates = frozenset(stable_member_ids_by_candidate)
    missing_candidates = expected_candidates - supplied_candidates
    if missing_candidates:
        raise ValueError("missing stable mapping for accepted candidate")
    if supplied_candidates - expected_candidates:
        raise ValueError("stable mapping contains unknown candidate")

    stable_member_ids = tuple(
        stable_member_ids_by_candidate[candidate_id] for candidate_id in candidate_ids
    )
    if any(
        not isinstance(member_id, str)
        or _STABLE_MEMBER_ID.fullmatch(member_id) is None
        for member_id in stable_member_ids
    ):
        raise ValueError("stable mapping values must be stable anonymous member IDs")
    if len(set(stable_member_ids)) != len(stable_member_ids):
        raise ValueError("stable mapping values must be unique")

    return GroundTruthSet(
        tuple(
            GroundTruthScene(
                scene.timestamp_seconds,
                tuple(
                    stable_member_ids_by_candidate[candidate_id]
                    for candidate_id in scene.candidate_ids
                ),
            )
            for scene in proposal.scenes
        )
    )
