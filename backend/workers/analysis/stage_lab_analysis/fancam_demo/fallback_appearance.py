from __future__ import annotations

from ..detection import NormalizedBox


def expanded_retry_box(box: NormalizedBox) -> NormalizedBox:
    """Expand every side by one quarter and clamp the result to the frame."""
    left = max(0.0, box.x - (box.width * 0.25))
    top = max(0.0, box.y - (box.height * 0.25))
    right = min(1.0, box.x + box.width + (box.width * 0.25))
    bottom = min(1.0, box.y + box.height + (box.height * 0.25))
    return NormalizedBox(left, top, right - left, bottom - top)
