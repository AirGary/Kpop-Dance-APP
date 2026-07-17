from __future__ import annotations


class MediaError(RuntimeError):
    """A stable, user-safe media processing failure."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)
