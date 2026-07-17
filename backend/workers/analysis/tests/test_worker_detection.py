from __future__ import annotations

from pathlib import Path

from stage_lab_analysis.detection import Detection, NormalizedBox
from stage_lab_analysis.worker import AnalysisWorker


def test_worker_detect_candidates_uses_proxy_and_writes_real_candidate_paths(
    tmp_path: Path,
) -> None:
    proxy = tmp_path / "analysis" / "proxy.mp4"
    proxy.parent.mkdir()
    proxy.write_bytes(b"proxy")

    def frames(_: Path):
        for second in range(3):
            yield float(second), object(), 100, 100

    class Detector:
        def detect(self, frame: object) -> tuple[Detection, ...]:
            return (Detection(0.0, NormalizedBox(0.2, 0.1, 0.3, 0.7), 0.9),)

    worker = AnalysisWorker(detector=Detector(), frame_reader=frames)
    result = worker.detect_candidates(tmp_path)

    assert len(result.candidates) == 1
    assert result.candidates[0].representative_image_paths == (
        "analysis/candidates/candidate-1-1.jpg",
        "analysis/candidates/candidate-1-2.jpg",
        "analysis/candidates/candidate-1-3.jpg",
    )
