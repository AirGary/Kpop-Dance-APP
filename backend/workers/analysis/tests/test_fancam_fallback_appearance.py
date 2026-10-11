from __future__ import annotations

from stage_lab_analysis.detection import NormalizedBox
from stage_lab_analysis.fancam_demo.fallback_appearance import expanded_retry_box


def test_expanded_retry_box_expands_each_side_and_clamps_to_frame() -> None:
    expanded = expanded_retry_box(NormalizedBox(0.05, 0.05, 0.40, 0.20))

    assert expanded == NormalizedBox(0.0, 0.0, 0.55, 0.30)
