from __future__ import annotations

import re
from typing import Any


_STABLE_MEMBER_ID = re.compile(r"member-(?:0[1-9]|[1-9][0-9]+)\Z")
_WINDOW_NAME = "Fancam local review"


class ReviewCancelled(Exception):
    """The reviewer explicitly cancelled the current local evaluation run."""


def member_id_from_code(code: str) -> str | None:
    if len(code) != 1 or not ("A" <= code <= "Z"):
        return None
    return f"member-{ord(code) - ord('A') + 1:02d}"


def _as_display_image(frame: Any):
    import numpy as np

    image = np.asarray(frame)
    if image.ndim == 2:
        return np.repeat(image[..., None], 3, axis=2)
    if image.ndim == 3 and image.shape[2] == 1:
        return np.repeat(image, 3, axis=2)
    if image.ndim != 3 or image.shape[2] < 3:
        return None
    return image[:, :, :3]


def _pixel_bounds(image: Any, detection: Any) -> tuple[int, int, int, int] | None:
    box = getattr(detection, "box", None)
    if image is None or box is None:
        return None
    height, width = image.shape[:2]
    left = max(0, min(width, int(box.x * width)))
    top = max(0, min(height, int(box.y * height)))
    right = max(left, min(width, int((box.x + box.width) * width)))
    bottom = max(top, min(height, int((box.y + box.height) * height)))
    if right <= left or bottom <= top:
        return None
    return left, top, right, bottom


def _candidate_region(image: Any, detection: Any):
    bounds = _pixel_bounds(image, detection)
    if bounds is None:
        return None
    left, top, right, bottom = bounds
    return image[top:bottom, left:right].copy()


def _compose_legacy_truth_display(
    frame: Any, detection: Any, entered_member_id: str, cv2: Any
):
    import numpy as np

    image = _as_display_image(frame)
    bounds = _pixel_bounds(image, detection)
    if bounds is None:
        return None
    left, top, right, bottom = bounds
    source_panel = image.copy()
    candidate_region = source_panel[top:bottom, left:right].copy()
    cv2.rectangle(source_panel, (left, top), (right, bottom), (0, 255, 0), 2)
    gap = 8
    source_height, source_width = source_panel.shape[:2]
    crop_height, crop_width = candidate_region.shape[:2]
    panel_height = max(source_height, crop_height)
    panel_width = source_width + gap + crop_width
    display = np.zeros((panel_height + 56, panel_width, 3), dtype=source_panel.dtype)
    display[:source_height, :source_width] = source_panel
    display[:crop_height, source_width + gap : source_width + gap + crop_width] = (
        candidate_region
    )
    cv2.putText(
        display,
        "Source frame with boxed detection and crop; Enter confirms",
        (8, panel_height + 24),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.5,
        (255, 255, 255),
        1,
        cv2.LINE_AA,
    )
    cv2.putText(
        display,
        entered_member_id or "Type A-Z then Enter; X rejects; Esc cancels",
        (8, panel_height + 48),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.6,
        (255, 255, 255),
        1,
        cv2.LINE_AA,
    )
    return display


class LocalReviewSession:
    """One macOS-local, in-memory review session with no persistence."""

    __slots__ = ("_closed", "_member_to_runtime", "_runtime_to_member")

    def __init__(self) -> None:
        self._runtime_to_member: dict[str, str] = {}
        self._member_to_runtime: dict[str, str] = {}
        self._closed = False

    def known(self, runtime_candidate_id: str) -> str | None:
        if self._closed:
            return None
        return self._runtime_to_member.get(runtime_candidate_id)

    def review(
        self,
        frame: Any,
        detection: Any,
        runtime_candidate_id: str,
        *,
        force: bool = False,
    ) -> str | None:
        if self._closed:
            return self.known(runtime_candidate_id)
        existing_member_id = self._runtime_to_member.get(runtime_candidate_id)
        if existing_member_id is not None:
            if not force:
                return existing_member_id
            member_id = self._prompt(frame, detection, runtime_candidate_id)
            return existing_member_id if member_id == existing_member_id else None
        member_id = self._prompt(frame, detection, runtime_candidate_id)
        if (
            member_id is None
            or _STABLE_MEMBER_ID.fullmatch(member_id) is None
            or member_id in self._member_to_runtime
        ):
            return None
        self._runtime_to_member[runtime_candidate_id] = member_id
        self._member_to_runtime[member_id] = runtime_candidate_id
        return member_id

    def close(self) -> None:
        self._runtime_to_member.clear()
        self._member_to_runtime.clear()
        self._closed = True

    def _prompt(self, frame: Any, detection: Any, runtime_candidate_id: str) -> str | None:
        """Show only the current in-memory candidate region and await a choice."""

        del runtime_candidate_id

        try:
            import cv2
        except ImportError:
            return None

        image = _as_display_image(frame)
        candidate_region = _candidate_region(image, detection)
        if candidate_region is None:
            return None
        entered_code = ""
        try:
            while True:
                display = candidate_region.copy()
                cv2.putText(
                    display,
                    "Type A-Z then Enter; X rejects; Esc cancels",
                    (8, 24),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.5,
                    (255, 255, 255),
                    1,
                    cv2.LINE_AA,
                )
                cv2.putText(
                    display,
                    entered_code or "Enter A-Z",
                    (8, 48),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.6,
                    (255, 255, 255),
                    1,
                    cv2.LINE_AA,
                )
                cv2.imshow(_WINDOW_NAME, display)
                key = cv2.waitKey(0) & 0xFF
                if key == 27:
                    raise ReviewCancelled()
                if key in (10, 13):
                    return member_id_from_code(entered_code)
                if key in (8, 127):
                    entered_code = ""
                elif key == ord("x") and not entered_code:
                    return None
                elif 65 <= key <= 90:
                    entered_code = chr(key)
                elif 97 <= key <= 122:
                    entered_code = chr(key).upper()
        finally:
            del candidate_region
            cv2.destroyWindow(_WINDOW_NAME)


class LegacyTruthReviewSession(LocalReviewSession):
    """Local-only reviewer for assigning stable IDs to legacy truth candidates."""

    __slots__ = ()

    def review_candidate(
        self, frame: Any, detection: Any, candidate_id: str
    ) -> str | None:
        if self._closed:
            return self.known(candidate_id)
        return self._prompt(frame, detection, candidate_id)

    def _prompt(self, frame: Any, detection: Any, runtime_candidate_id: str) -> str | None:
        del runtime_candidate_id

        try:
            import cv2
        except ImportError:
            return None

        entered_member_id = ""
        try:
            while True:
                display = _compose_legacy_truth_display(
                    frame, detection, entered_member_id, cv2
                )
                if display is None:
                    return None
                cv2.imshow(_WINDOW_NAME, display)
                key = cv2.waitKey(0) & 0xFF
                if key == 27:
                    raise ReviewCancelled()
                if key in (10, 13):
                    return entered_member_id
                if key in (8, 127):
                    entered_member_id = entered_member_id[:-1]
                elif key == ord("x") and not entered_member_id:
                    return None
                elif (32 <= key <= 126 and chr(key).isalnum()) or key == ord("-"):
                    entered_member_id += chr(key)
        finally:
            cv2.destroyWindow(_WINDOW_NAME)
