from __future__ import annotations

import hashlib
from pathlib import Path

import numpy as np
import pytest

from stage_lab_analysis.detection import NormalizedBox
from stage_lab_analysis.runtime_probe import (
    ModelManifestError,
    OpenMMLabProbe,
    OpenVINOReIDProbe,
)
from stage_lab_analysis.reid import (
    OpenVINOReIDEmbedder,
    PersonEmbedding,
    _crop,
    _quality,
    cosine_similarity,
)


def _model_assets(tmp_path: Path) -> tuple[Path, Path, str, str]:
    xml = tmp_path / "person-reidentification-retail-0277.xml"
    binary = tmp_path / "person-reidentification-retail-0277.bin"
    xml.write_bytes(b"verified OpenVINO XML")
    binary.write_bytes(b"verified OpenVINO BIN")
    return (
        xml,
        binary,
        hashlib.sha256(xml.read_bytes()).hexdigest(),
        hashlib.sha256(binary.read_bytes()).hexdigest(),
    )


def _embedder(
    tmp_path: Path,
    *,
    values: tuple[float, ...] = (3.0, 4.0),
    infer=None,
    device: str = "CPU",
) -> OpenVINOReIDEmbedder:
    xml, binary, xml_hash, binary_hash = _model_assets(tmp_path)
    return OpenVINOReIDEmbedder(
        model_xml=xml,
        model_bin=binary,
        expected_xml_sha256=xml_hash,
        expected_bin_sha256=binary_hash,
        infer=infer or (lambda _: values),
        device=device,
    )


def test_embedder_rejects_invalid_or_blurred_crops(tmp_path: Path) -> None:
    embedder = _embedder(tmp_path)
    textured = (np.indices((160, 80)).sum(axis=0) % 2 * 255).astype(np.uint8)
    frame = np.repeat(textured[..., None], 3, axis=2)

    assert embedder.embed(frame, NormalizedBox(0.0, 0.0, 0.01, 0.01)) is None
    assert embedder.embed(np.zeros_like(frame), NormalizedBox(0.1, 0.1, 0.8, 0.8)) is None


def test_embedder_returns_l2_normalized_embedding(tmp_path: Path) -> None:
    embedder = _embedder(tmp_path)
    textured = (np.indices((160, 80)).sum(axis=0) % 2 * 255).astype(np.uint8)
    frame = np.repeat(textured[..., None], 3, axis=2)

    embedding = embedder.embed(frame, NormalizedBox(0.1, 0.1, 0.8, 0.8))

    assert embedding is not None
    assert embedding.values == pytest.approx((0.6, 0.8))
    assert sum(value * value for value in embedding.values) == pytest.approx(1.0)
    assert 0.0 < embedding.quality <= 1.0


def test_cosine_similarity_is_deterministic_for_normalized_embeddings() -> None:
    first = PersonEmbedding((0.6, 0.8), quality=0.9)
    second = PersonEmbedding((0.8, -0.6), quality=0.8)

    assert cosine_similarity(first, second) == pytest.approx(0.0)
    assert cosine_similarity(first, first) == pytest.approx(1.0)


def test_embedder_refuses_tampered_model_asset_before_inference(tmp_path: Path) -> None:
    embedder = _embedder(tmp_path)
    xml = tmp_path / "person-reidentification-retail-0277.xml"
    xml.write_bytes(b"tampered")
    frame = (np.indices((160, 80)).sum(axis=0) % 2 * 255).astype(np.uint8)
    frame = np.repeat(frame[..., None], 3, axis=2)

    with pytest.raises(ModelManifestError, match="checksum mismatch"):
        embedder.embed(frame, NormalizedBox(0.1, 0.1, 0.8, 0.8))


@pytest.mark.parametrize(
    "infer",
    [
        lambda _: (_ for _ in ()).throw(RuntimeError("inference failed")),
        lambda _: None,
    ],
    ids=["execution-error", "invalid-output"],
)
def test_embedder_converts_inference_failures_to_missing_embedding(
    tmp_path: Path,
    infer,
) -> None:
    embedder = _embedder(tmp_path, infer=infer)
    textured = (np.indices((160, 80)).sum(axis=0) % 2 * 255).astype(np.uint8)
    frame = np.repeat(textured[..., None], 3, axis=2)

    assert embedder.embed(frame, NormalizedBox(0.1, 0.1, 0.8, 0.8)) is None


@pytest.mark.parametrize("device", ["GPU", "AUTO", "mps"])
def test_embedder_rejects_any_non_cpu_openvino_device(
    tmp_path: Path,
    device: str,
) -> None:
    with pytest.raises(ValueError, match="CPU"):
        _embedder(tmp_path, device=device)


def test_cpu_probe_requires_individually_verified_xml_and_bin_assets(tmp_path: Path) -> None:
    xml, binary, xml_hash, binary_hash = _model_assets(tmp_path)
    manifest = tmp_path / "model-manifest.json"
    manifest.write_text(
        __import__("json").dumps(
            {
                "models": [
                    {
                        "role": "reid",
                        "name": "person-reidentification-retail-0277",
                        "sourceUrl": "https://github.com/openvinotoolkit/open_model_zoo",
                        "sha256": xml_hash,
                        "license": "Apache-2.0",
                        "licenseUrl": "https://www.apache.org/licenses/LICENSE-2.0",
                        "provenanceLocalPath": "model.yml",
                        "assets": [
                            {
                                "role": "xml",
                                "sourceUrl": "https://example.com/model.xml",
                                "localPath": xml.name,
                                "sha256": xml_hash,
                            },
                            {
                                "role": "bin",
                                "sourceUrl": "https://example.com/model.bin",
                                "localPath": binary.name,
                                "sha256": binary_hash,
                            },
                        ],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    captured: dict[str, object] = {}

    class FakeEmbedder:
        def __init__(self, **kwargs: object) -> None:
            captured.update(kwargs)

        def embed(self, frame: object, box: NormalizedBox) -> PersonEmbedding:
            return PersonEmbedding((1 / 16,) * 256, quality=0.9)

    assert OpenVINOReIDProbe(manifest, tmp_path, embedder_factory=FakeEmbedder)()
    assert captured == {
        "model_xml": xml,
        "model_bin": binary,
        "expected_xml_sha256": xml_hash,
        "expected_bin_sha256": binary_hash,
        "device": "CPU",
    }


def test_runtime_probe_fixture_is_sharp_enough_for_reid_quality_gate() -> None:
    crop = _crop(
        OpenMMLabProbe._test_frame(),
        NormalizedBox.from_pixels(160, 80, 480, 600, width=640, height=640),
    )

    assert crop is not None
    assert _quality(crop) >= 0.03
