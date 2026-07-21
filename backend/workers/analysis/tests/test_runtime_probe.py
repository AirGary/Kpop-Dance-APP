from __future__ import annotations

import json
import sys
import tomllib
from types import SimpleNamespace
from pathlib import Path

import pytest

from stage_lab_analysis.runtime_probe import (
    ModelManifestError,
    PythonVersionError,
    RuntimeProbeError,
    _is_supported_mps_failure,
    choose_device,
    load_model_manifest,
    require_python_311,
    resolve_model_checkpoint,
    resolve_model_config,
    trusted_checkpoint_loading,
    validate_detector_boxes,
)
from stage_lab_analysis.supply_chain import SupplyChainError, validate_supply_chain


REPOSITORY_ROOT = Path(__file__).resolve().parents[4]


def test_python_runtime_requires_exactly_python_311() -> None:
    require_python_311((3, 11, 9))

    with pytest.raises(PythonVersionError, match="Python 3.11"):
        require_python_311((3, 10, 14))

    with pytest.raises(PythonVersionError, match="Python 3.11"):
        require_python_311((3, 12, 0))


@pytest.mark.parametrize(
    "missing_field",
    ["name", "sourceUrl", "sha256", "license", "licenseUrl"],
)
def test_model_manifest_rejects_missing_provenance_field(
    tmp_path: Path,
    missing_field: str,
) -> None:
    model = {
        "name": "rtmdet-m-person",
        "sourceUrl": "https://download.openmmlab.com/example.pth",
        "sha256": "a" * 64,
        "license": "Apache-2.0",
        "licenseUrl": "https://github.com/open-mmlab/mmdetection/blob/main/LICENSE",
    }
    del model[missing_field]
    manifest_path = tmp_path / "model-manifest.json"
    manifest_path.write_text(json.dumps({"models": [model]}), encoding="utf-8")

    with pytest.raises(ModelManifestError, match=missing_field):
        load_model_manifest(manifest_path)


@pytest.mark.parametrize(
    "license_name",
    ["UNKNOWN", "non-commercial", "CC-BY-NC-4.0"],
)
def test_model_manifest_rejects_unapproved_or_noncommercial_license(
    tmp_path: Path,
    license_name: str,
) -> None:
    model = {
        "name": "unapproved-model",
        "sourceUrl": "https://example.com/model.pth",
        "sha256": "a" * 64,
        "license": license_name,
        "licenseUrl": "https://example.com/license",
    }
    manifest_path = tmp_path / "model-manifest.json"
    manifest_path.write_text(json.dumps({"models": [model]}), encoding="utf-8")

    with pytest.raises(ModelManifestError, match="approved commercial license"):
        load_model_manifest(manifest_path)


def test_choose_device_uses_mps_only_when_both_model_probes_pass() -> None:
    calls: list[tuple[str, str]] = []

    def probe(model: str, device: str) -> bool:
        calls.append((model, device))
        return True

    assert choose_device(mps_available=True, probe=probe) == "mps"
    assert calls == [("detector", "mps"), ("pose", "mps")]


@pytest.mark.parametrize("failing_model", ["detector", "pose"])
def test_choose_device_falls_back_to_cpu_exactly_once(
    failing_model: str,
) -> None:
    calls: list[tuple[str, str]] = []

    def probe(model: str, device: str) -> bool:
        calls.append((model, device))
        return not (device == "mps" and model == failing_model)

    assert choose_device(mps_available=True, probe=probe) == "cpu"
    assert calls.count(("detector", "cpu")) == 1
    assert calls.count(("pose", "cpu")) == 1
    assert all(calls.count(call) == 1 for call in set(calls))


def test_choose_device_skips_mps_when_it_is_unavailable() -> None:
    calls: list[tuple[str, str]] = []

    def probe(model: str, device: str) -> bool:
        calls.append((model, device))
        return True

    assert choose_device(mps_available=False, probe=probe) == "cpu"
    assert calls == [("detector", "cpu"), ("pose", "cpu")]


@pytest.mark.parametrize(
    "message",
    [
        "nms_impl: implementation for device mps:0 not found",
        "MPS backend does not support this operation",
    ],
)
def test_mps_probe_recognizes_known_mmcv_fallback_errors(message: str) -> None:
    assert _is_supported_mps_failure(RuntimeError(message))


def test_bootstrap_handles_chumpy_legacy_build_before_worker_install() -> None:
    script = (REPOSITORY_ROOT / "scripts/bootstrap-local-ai.sh").read_text(
        encoding="utf-8"
    )
    chumpy_install = "--no-build-isolation chumpy==0.70"
    worker_install = 'pip install --no-build-isolation --no-deps -e "$worker_root"'

    assert chumpy_install in script
    assert script.index(chumpy_install) < script.index(worker_install)


def test_inference_dependencies_pin_mmdet_compatible_mmcv() -> None:
    pyproject = tomllib.loads(
        (REPOSITORY_ROOT / "backend/workers/analysis/pyproject.toml").read_text(
            encoding="utf-8"
        )
    )

    assert "mmcv==2.1.0" in pyproject["project"]["optional-dependencies"][
        "inference"
    ]


def test_inference_dependencies_pin_macos_27_pytorch_pair() -> None:
    pyproject = tomllib.loads(
        (REPOSITORY_ROOT / "backend/workers/analysis/pyproject.toml").read_text(
            encoding="utf-8"
        )
    )
    dependencies = pyproject["project"]["optional-dependencies"]["inference"]

    assert "torch==2.13.0" in dependencies
    assert "torchvision==0.28.0" in dependencies


def test_bootstrap_builds_mmcv_with_compatible_toolchain() -> None:
    script = (REPOSITORY_ROOT / "scripts/bootstrap-local-ai.sh").read_text(
        encoding="utf-8"
    )
    toolchain_install = "setuptools==80.10.2 wheel==0.47.0 ninja==1.13.0"
    torch_install = "torch==2.13.0 torchvision==0.28.0"
    mmcv_install = "--no-build-isolation mmcv==2.1.0"
    worker_install = 'pip install --no-build-isolation --no-deps -e "$worker_root"'

    assert toolchain_install in script
    assert torch_install in script
    assert mmcv_install in script
    assert script.index(toolchain_install) < script.index(torch_install)
    assert script.index(torch_install) < script.index(mmcv_install)
    assert script.index(mmcv_install) < script.index(worker_install)
    assert 'export PATH="$virtual_environment/bin:$PATH"' in script


def test_bootstrap_consumes_committed_exact_constraints() -> None:
    script = (REPOSITORY_ROOT / "scripts/bootstrap-local-ai.sh").read_text(
        encoding="utf-8"
    )
    constraints = (
        REPOSITORY_ROOT
        / "backend/workers/analysis/constraints-macos-arm64.txt"
    ).read_text(encoding="utf-8")

    assert 'readonly constraints="$worker_root/constraints-macos-arm64.txt"' in script
    assert 'offline=(--no-index --find-links "$package_root" -c "$constraints")' in script
    assert script.count('pip install "${offline[@]}"') >= 4
    assert "pip install --upgrade pip" not in script
    assert "pip download --no-build-isolation --require-hashes" in script
    assert all(
        not line or line.startswith("#") or "==" in line
        for line in constraints.splitlines()
    )


def test_dependency_lock_and_license_evidence_cover_the_same_artifacts() -> None:
    validate_supply_chain(
        REPOSITORY_ROOT / "backend/workers/analysis/requirements-macos-arm64.lock",
        REPOSITORY_ROOT / "backend/workers/analysis/dependency-licenses.json",
    )


def test_dependency_evidence_rejects_unknown_license(tmp_path: Path) -> None:
    lock = tmp_path / "requirements.lock"
    lock.write_text(f"example==1.0 --hash=sha256:{'a' * 64}\n", encoding="utf-8")
    licenses = tmp_path / "licenses.json"
    licenses.write_text(
        json.dumps(
            {
                "commercialDistributionApproved": False,
                "packages": [
                    {
                        "name": "example",
                        "version": "1.0",
                        "sourceUrl": "https://files.pythonhosted.org/example.whl",
                        "sha256": "a" * 64,
                        "license": "UNKNOWN",
                        "licenseEvidence": [
                            {"type": "reviewed-artifact", "sha256": "a" * 64}
                        ],
                        "reviewStatus": "approved-for-local-technical-demo",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(SupplyChainError, match="unapproved dependency license"):
        validate_supply_chain(lock, licenses)


def test_dependency_evidence_must_bind_license_review_to_artifact(
    tmp_path: Path,
) -> None:
    lock = tmp_path / "requirements.lock"
    lock.write_text(f"example==1.0 --hash=sha256:{'a' * 64}\n", encoding="utf-8")
    licenses = tmp_path / "licenses.json"
    licenses.write_text(
        json.dumps(
            {
                "commercialDistributionApproved": False,
                "packages": [
                    {
                        "name": "example",
                        "version": "1.0",
                        "sourceUrl": "https://files.pythonhosted.org/example.whl",
                        "sha256": "a" * 64,
                        "license": "MIT",
                        "licenseEvidence": [],
                        "reviewStatus": "approved-for-local-technical-demo",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(SupplyChainError, match="license evidence"):
        validate_supply_chain(lock, licenses)


def test_verify_script_removes_stale_capability_report_before_probe() -> None:
    script = (REPOSITORY_ROOT / "scripts/verify-local-ai.sh").read_text(
        encoding="utf-8"
    )

    removal = 'rm -f "$capabilities"'
    environment_check = 'if [[ ! -x "$python" ]]'
    assert removal in script
    assert script.index(removal) < script.index(environment_check)


def test_trusted_checkpoint_loading_is_hash_gated_and_restored(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    checkpoint = tmp_path / "official.pth"
    checkpoint.write_bytes(b"verified official checkpoint")
    digest = __import__("hashlib").sha256(checkpoint.read_bytes()).hexdigest()
    calls: list[dict[str, object]] = []

    def original_load(*args: object, **kwargs: object) -> object:
        calls.append(kwargs)
        return object()

    fake_torch = SimpleNamespace(load=original_load)
    monkeypatch.setitem(sys.modules, "torch", fake_torch)

    with trusted_checkpoint_loading(checkpoint, digest):
        fake_torch.load(checkpoint)
        assert fake_torch.load is not original_load

    assert calls == [{"weights_only": False}]
    assert fake_torch.load is original_load

    with pytest.raises(ModelManifestError, match="checksum"):
        with trusted_checkpoint_loading(checkpoint, "0" * 64):
            pass


def test_pose_config_resolves_inside_complete_package_tree(tmp_path: Path) -> None:
    package_root = tmp_path / "mmpose"
    package_config = package_root / ".mim/configs/pose.py"
    package_config.parent.mkdir(parents=True)
    package_config.write_text("_base_ = ['../_base_/runtime.py']\n", encoding="utf-8")
    digest = __import__("hashlib").sha256(package_config.read_bytes()).hexdigest()
    model = {
        "configLocalPath": "standalone-pose.py",
        "packageConfigPath": ".mim/configs/pose.py",
        "configSha256": digest,
    }

    resolved = resolve_model_config(
        model,
        model_root=tmp_path / "models",
        package_root=package_root,
    )

    assert resolved == package_config


def test_model_checkpoint_is_verified_immediately_before_loading(
    tmp_path: Path,
) -> None:
    checkpoint = tmp_path / "detector.pth"
    checkpoint.write_bytes(b"verified detector checkpoint")
    digest = __import__("hashlib").sha256(checkpoint.read_bytes()).hexdigest()
    model = {
        "localPath": checkpoint.name,
        "sha256": digest,
    }

    assert resolve_model_checkpoint(model, model_root=tmp_path) == checkpoint

    checkpoint.write_bytes(b"tampered after bootstrap")
    with pytest.raises(ModelManifestError, match="checkpoint checksum mismatch"):
        resolve_model_checkpoint(model, model_root=tmp_path)


def test_detector_gate_rejects_empty_or_nonfinite_boxes() -> None:
    import numpy as np

    validate_detector_boxes(np.array([[1.0, 2.0, 3.0, 4.0]]))

    with pytest.raises(RuntimeProbeError, match="no bounding boxes"):
        validate_detector_boxes(np.empty((0, 4)))

    with pytest.raises(RuntimeProbeError, match="non-finite"):
        validate_detector_boxes(np.array([[1.0, 2.0, float("nan"), 4.0]]))
