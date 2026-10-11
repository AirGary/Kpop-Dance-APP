from __future__ import annotations

import pytest

from stage_lab_analysis.fancam_demo import benchmark_cli
from stage_lab_analysis.fancam_demo.benchmark import (
    BenchmarkReport,
    BenchmarkSample,
    run_native_benchmark,
)


def test_benchmark_report_never_serializes_embeddings_or_paths() -> None:
    report = BenchmarkReport((BenchmarkSample(0.0, 5, 5, 0.2),))

    assert report.to_json() == {
        "sampleCount": 1,
        "detectedPeopleHistogram": {"5": 1},
        "usableEmbeddingHistogram": {"5": 1},
        "elapsedSeconds": 0.2,
        "framesPerSecond": 5.0,
    }


def test_benchmark_sample_rejects_negative_values() -> None:
    with pytest.raises(ValueError):
        BenchmarkSample(-1.0, 5, 5, 0.1)


def test_native_runner_aggregates_injected_detector_results(tmp_path) -> None:
    source = tmp_path / "private-source.mp4"
    observed_reads = []

    class Detection:
        box = object()

    class Detector:
        def detect(self, frame):
            assert frame == "frame"
            return (Detection(), Detection(), Detection(), Detection(), Detection())

    class Embedder:
        def embed(self, frame, box):
            assert frame == "frame"
            assert box is Detection.box
            return object()

    def reader(read_source, timestamp):
        observed_reads.append((read_source, timestamp))
        return "frame"

    report = run_native_benchmark(
        source,
        (0.0,),
        Detector(),
        Embedder(),
        reader=reader,
    )

    assert observed_reads == [(source, 0.0)]
    assert report.to_json()["detectedPeopleHistogram"] == {"5": 1}
    assert report.to_json()["usableEmbeddingHistogram"] == {"5": 1}


def test_cli_default_model_root_is_relative_to_repository_root(monkeypatch) -> None:
    monkeypatch.delenv("STAGE_LAB_MODEL_ROOT", raising=False)

    assert benchmark_cli._default_model_root().name == "models"
    assert benchmark_cli._default_model_root().parent.name == ".local-ai"
    assert benchmark_cli._default_model_root().is_absolute()


def test_components_can_keep_weak_detections_for_offline_trajectory(monkeypatch, tmp_path) -> None:
    options = {}

    def detector(**kwargs):
        options.update(kwargs)
        return object()

    monkeypatch.setattr(benchmark_cli, "RTMDetPersonDetector", detector)
    monkeypatch.setattr(benchmark_cli, "OpenVINOReIDEmbedder", lambda **_kwargs: object())
    monkeypatch.setattr(benchmark_cli, "load_model_manifest", lambda _path: {
        "models": [
            {"role": "detector", "configLocalPath": "detector.py", "localPath": "detector.pth"},
            {"role": "reid", "assets": [
                {"role": "xml", "localPath": "reid.xml", "sha256": "x"},
                {"role": "bin", "localPath": "reid.bin", "sha256": "y"},
            ]},
        ]
    })

    benchmark_cli._components(tmp_path, detector_threshold=.1)

    assert options["threshold"] == .1
