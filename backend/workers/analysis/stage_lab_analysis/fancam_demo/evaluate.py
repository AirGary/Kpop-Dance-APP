from __future__ import annotations

from dataclasses import dataclass
import math

from .truth import GroundTruthScene, GroundTruthSet, SceneObservation


def _score(value: object, name: str) -> float:
    if isinstance(value, bool):
        raise ValueError(f"{name} must be between 0 and 1")
    try:
        result = float(value)
    except (TypeError, ValueError, OverflowError) as error:
        raise ValueError(f"{name} must be between 0 and 1") from error
    if not math.isfinite(result) or not 0.0 <= result <= 1.0:
        raise ValueError(f"{name} must be between 0 and 1")
    return result


def _count(value: object, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{name} must be a non-negative integer")
    return value


@dataclass(frozen=True, slots=True)
class EvaluationResult:
    detection_recall: float
    identity_accuracy: float | None
    id_switches: int
    false_locks: int
    confirmation_requests: int

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "detection_recall", _score(self.detection_recall, "detection_recall")
        )
        if self.identity_accuracy is not None:
            object.__setattr__(
                self,
                "identity_accuracy",
                _score(self.identity_accuracy, "identity_accuracy"),
            )
        object.__setattr__(self, "id_switches", _count(self.id_switches, "id_switches"))
        object.__setattr__(self, "false_locks", _count(self.false_locks, "false_locks"))
        object.__setattr__(
            self,
            "confirmation_requests",
            _count(self.confirmation_requests, "confirmation_requests"),
        )

    def to_json(self) -> dict[str, object]:
        return {
            "detectionRecall": self.detection_recall,
            "identityAccuracy": self.identity_accuracy,
            "idSwitches": self.id_switches,
            "falseLocks": self.false_locks,
            "confirmationRequests": self.confirmation_requests,
        }


def _scene_for(
    scenes: tuple[GroundTruthScene, ...], timestamp_seconds: float
) -> GroundTruthScene | None:
    return next(
        (
            scene
            for scene in scenes
            if scene.timestamp_seconds == timestamp_seconds
        ),
        None,
    )


def evaluate_membership(
    truth: GroundTruthSet,
    observations: tuple[SceneObservation, ...],
) -> EvaluationResult:
    observations = tuple(observations)
    if not all(isinstance(observation, SceneObservation) for observation in observations):
        raise TypeError("observations must contain SceneObservation values")
    timestamps = tuple(observation.timestamp_seconds for observation in observations)
    if len(set(timestamps)) != len(timestamps):
        raise ValueError("observations must not contain duplicate timestamps")

    total_visible = sum(len(scene.visible_member_ids) for scene in truth.scenes)
    detected_visible = 0
    for scene in truth.scenes:
        observation = _scene_for(observations, scene.timestamp_seconds)
        if observation is not None:
            detected_visible += min(
                len(observation.assignments), len(scene.visible_member_ids)
            )
    detection_recall = detected_visible / total_visible if total_visible else 0.0

    correct_assignments = 0
    false_locks = 0
    confirmed_assignments = 0
    id_switches = 0
    confirmation_requests = 0
    last_confirmed_member_ids_by_runtime_candidate: dict[str, str] = {}
    last_confirmed_runtime_candidates_by_member_id: dict[str, str] = {}
    for observation in sorted(observations, key=lambda item: item.timestamp_seconds):
        scene = _scene_for(truth.scenes, observation.timestamp_seconds)
        visible_member_ids = frozenset(
            scene.visible_member_ids if scene is not None else ()
        )
        assigned_visible_member_ids: set[str] = set()
        for assignment in observation.assignments:
            if not assignment.confirmed:
                confirmation_requests += 1
                continue
            if assignment.confirmation_requested:
                confirmation_requests += 1
            confirmed_assignments += 1
            stable_member_id = assignment.stable_member_id
            if stable_member_id is None or stable_member_id not in visible_member_ids:
                false_locks += 1
            elif stable_member_id in assigned_visible_member_ids:
                false_locks += 1
            else:
                correct_assignments += 1
                assigned_visible_member_ids.add(stable_member_id)

            if stable_member_id is not None:
                previous_member_id = last_confirmed_member_ids_by_runtime_candidate.get(
                    assignment.runtime_candidate_id
                )
                if (
                    previous_member_id is not None
                    and previous_member_id != stable_member_id
                ):
                    id_switches += 1
                last_confirmed_member_ids_by_runtime_candidate[
                    assignment.runtime_candidate_id
                ] = stable_member_id
                previous_runtime_candidate_id = (
                    last_confirmed_runtime_candidates_by_member_id.get(
                        stable_member_id
                    )
                )
                if (
                    previous_runtime_candidate_id is not None
                    and previous_runtime_candidate_id
                    != assignment.runtime_candidate_id
                ):
                    id_switches += 1
                last_confirmed_runtime_candidates_by_member_id[stable_member_id] = (
                    assignment.runtime_candidate_id
                )
    identity_accuracy = (
        correct_assignments / confirmed_assignments
        if confirmed_assignments
        else None
    )
    return EvaluationResult(
        detection_recall=detection_recall,
        identity_accuracy=identity_accuracy,
        id_switches=id_switches,
        false_locks=false_locks,
        confirmation_requests=confirmation_requests,
    )
