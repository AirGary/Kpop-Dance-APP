from collections import deque
import sys
from types import SimpleNamespace

import numpy as np
import pytest

from stage_lab_analysis.fancam_demo.local_review import (
    LocalReviewSession,
    ReviewCancelled,
)


@pytest.fixture
def keyboard_review(monkeypatch):
    """Exercise the real prompt and mapping logic using synthetic GUI input."""
    keys = deque()
    closed_windows = []

    def wait_key(delay):
        assert delay == 0
        assert keys, "Review requested an unexpected extra key"
        return keys.popleft()

    monkeypatch.setitem(
        sys.modules,
        "cv2",
        SimpleNamespace(
            FONT_HERSHEY_SIMPLEX=0,
            LINE_AA=0,
            putText=lambda *args: None,
            imshow=lambda *args: None,
            waitKey=wait_key,
            destroyWindow=closed_windows.append,
        ),
    )
    session = LocalReviewSession()
    frame = np.zeros((64, 64, 3), dtype=np.uint8)
    detection = SimpleNamespace(
        box=SimpleNamespace(x=0.0, y=0.0, width=1.0, height=1.0)
    )

    def review(sequence, candidate="candidate-01", *, force=False):
        keys.extend(ord(key) if isinstance(key, str) else key for key in sequence)
        try:
            return session.review(frame, detection, candidate, force=force)
        finally:
            assert not keys, "Review did not consume the supplied keyboard sequence"

    return session, review, closed_windows


@pytest.mark.parametrize("enter", [10, 13])
@pytest.mark.parametrize("code", list("ABCDEabcde"))
def test_letter_then_enter_confirms_and_remembers_member(keyboard_review, code, enter):
    session, review, closed_windows = keyboard_review
    expected = f"member-{ord(code.upper()) - ord('A') + 1:02d}"

    assert review([code, enter]) == expected
    assert session.known("candidate-01") == expected
    assert len(closed_windows) == 1


@pytest.mark.parametrize("backspace", [8, 127])
def test_backspace_allows_correcting_member_code(keyboard_review, backspace):
    session, review, _ = keyboard_review

    assert review(["A", backspace, "e", 13]) == "member-05"
    assert session.known("candidate-01") == "member-05"


@pytest.mark.parametrize("sequence", [[13], ["1", 13], ["A", 8, 13], ["x"]])
def test_empty_invalid_or_rejected_input_does_not_confirm(keyboard_review, sequence):
    session, review, closed_windows = keyboard_review

    assert review(sequence) is None
    assert session.known("candidate-01") is None
    assert len(closed_windows) == 1


def test_escape_cancels_and_closes_window(keyboard_review):
    session, review, closed_windows = keyboard_review

    with pytest.raises(ReviewCancelled):
        review(["A", 27])

    assert session.known("candidate-01") is None
    assert len(closed_windows) == 1


def test_known_candidate_without_force_does_not_prompt_again(keyboard_review):
    _, review, closed_windows = keyboard_review

    assert review(["A", 13]) == "member-01"
    assert review([]) == "member-01"
    assert len(closed_windows) == 1


@pytest.mark.parametrize(
    ("sequence", "expected"),
    [(["a", 13], "member-01"), (["B", 13], None), (["x"], None), ([13], None)],
)
def test_force_reconfirms_only_original_member_without_rebinding(
    keyboard_review, sequence, expected
):
    session, review, closed_windows = keyboard_review

    assert review(["A", 13]) == "member-01"
    assert review(sequence, force=True) == expected
    assert session.known("candidate-01") == "member-01"
    assert len(closed_windows) == 2
    assert review(["B", 13], "candidate-02") == "member-02"


def test_member_cannot_be_bound_to_two_runtime_candidates(keyboard_review):
    session, review, _ = keyboard_review

    assert review(["A", 13]) == "member-01"
    assert review(["a", 13], "candidate-02") is None
    assert session.known("candidate-01") == "member-01"
    assert session.known("candidate-02") is None
