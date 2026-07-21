from dataclasses import replace
import zipfile

import pytest

from stage_lab_analysis.package import (
    AnalysisPackageError,
    PackageInputs,
    validate_analysis_package,
    write_analysis_package,
)


def inputs() -> PackageInputs:
    return PackageInputs(
        manifest={"schemaVersion": 1, "modelVersion": "test"},
        spotlight=[{"timeSeconds": 0.0, "x": 0.1, "y": 0.2, "width": 0.3, "height": 0.6, "confidence": 0.9}],
        pose=[{"timeSeconds": 0.0, "keypoints": [{"name": "hip", "x": 0.2, "y": 0.5, "confidence": 0.9}], "confidence": 0.9}],
        timeline=[{"startSeconds": 0.0, "endSeconds": 2.0, "difficulty": "easy", "reasons": []}],
        confidence=[{"startSeconds": 0.0, "endSeconds": 2.0, "confidence": 0.9}],
    )


def test_package_contains_exact_members_and_validates_hashes(tmp_path):
    artifact = write_analysis_package(tmp_path / "result-v1.zip", inputs())

    assert artifact.byte_count > 0
    assert len(artifact.sha256) == 64
    assert validate_analysis_package(artifact.path) == artifact
    with zipfile.ZipFile(artifact.path) as archive:
        assert archive.namelist() == [
            "confidence.json",
            "manifest.json",
            "pose-track.json",
            "spotlight-track.json",
            "timeline.json",
        ]


def test_package_json_is_deterministic_and_rejects_path_traversal(tmp_path):
    first = write_analysis_package(tmp_path / "first.zip", inputs())
    second = write_analysis_package(tmp_path / "second.zip", inputs())

    assert first.sha256 == second.sha256
    with pytest.raises(AnalysisPackageError, match="member"):
        write_analysis_package(tmp_path / "bad.zip", replace(inputs(), manifest={"../manifest.json": {}}))
