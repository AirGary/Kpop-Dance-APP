from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
import json
import math
from pathlib import Path
from typing import Any

from .evaluate import EvaluationResult


APPROVED_LICENSE_ID = "Apache-2.0"


def _non_empty(value: object, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must not be empty")
    return value


def _finite_non_negative(value: object, name: str) -> float:
    if isinstance(value, bool):
        raise ValueError(f"{name} must be finite and non-negative")
    try:
        result = float(value)
    except (TypeError, ValueError, OverflowError) as error:
        raise ValueError(f"{name} must be finite and non-negative") from error
    if not math.isfinite(result) or result < 0.0:
        raise ValueError(f"{name} must be finite and non-negative")
    return result


def _positive_finite(value: object, name: str) -> float:
    result = _finite_non_negative(value, name)
    if result == 0.0:
        raise ValueError(f"{name} must be positive")
    return result


@dataclass(frozen=True, slots=True)
class ComponentCandidate:
    name: str
    version: str
    license_id: str
    cpu_probe: Callable[[], bool]
    run: Callable[..., "ComponentScore"]
    provenance: str = ""
    supply_chain_reviewed: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "name", _non_empty(self.name, "name"))
        object.__setattr__(self, "version", _non_empty(self.version, "version"))
        object.__setattr__(self, "license_id", _non_empty(self.license_id, "license_id"))
        if not callable(self.cpu_probe) or not callable(self.run):
            raise ValueError("cpu_probe and run must be callable")
        if self.provenance:
            object.__setattr__(self, "provenance", _non_empty(self.provenance, "provenance"))
        if not isinstance(self.supply_chain_reviewed, bool):
            raise ValueError("supply_chain_reviewed must be a boolean")


@dataclass(frozen=True, slots=True)
class ComponentScore:
    candidate: ComponentCandidate
    result: EvaluationResult
    elapsed_seconds: float
    labelled_minutes: float = 1.0
    identity_evidence_verified: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.candidate, ComponentCandidate):
            raise TypeError("candidate must be a ComponentCandidate")
        if not isinstance(self.result, EvaluationResult):
            raise TypeError("result must be an EvaluationResult")
        if not isinstance(self.identity_evidence_verified, bool):
            raise ValueError("identity_evidence_verified must be a boolean")
        object.__setattr__(
            self,
            "elapsed_seconds",
            _finite_non_negative(self.elapsed_seconds, "elapsed_seconds"),
        )
        object.__setattr__(
            self,
            "labelled_minutes",
            _positive_finite(self.labelled_minutes, "labelled_minutes"),
        )

    def to_json(self) -> dict[str, object]:
        return {
            "metrics": self.result.to_json(),
            "elapsedSeconds": self.elapsed_seconds,
            "labelledMinutes": self.labelled_minutes,
            "identityEvidenceVerified": self.identity_evidence_verified,
            "metricScope": "member_set_consistency_only",
        }


def _current_baseline_cpu_probe() -> bool:
    capabilities_path = Path(__file__).resolve().parents[5] / ".local-ai" / "runtime-capabilities.json"
    try:
        payload = json.loads(capabilities_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    return bool(
        isinstance(payload, dict)
        and payload.get("device") == "cpu"
        and payload.get("detector_ready") is True
        and payload.get("reid_ready") is True
    )


def _current_baseline_run(*args: Any, **kwargs: Any) -> ComponentScore:
    from .evaluation_runner import run_current_baseline

    return run_current_baseline(*args, **kwargs)


def register_current_baseline() -> ComponentCandidate:
    return ComponentCandidate(
        name="current-baseline",
        version="RTMDet-m + OpenVINO 0277 + existing tracker",
        license_id=APPROVED_LICENSE_ID,
        cpu_probe=_current_baseline_cpu_probe,
        run=_current_baseline_run,
        provenance="backend/workers/analysis/model-manifest.json (hash-gated)",
        supply_chain_reviewed=True,
    )
