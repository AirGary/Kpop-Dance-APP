from __future__ import annotations

from dataclasses import dataclass
import math

from .pose import PoseFrame


@dataclass(frozen=True, slots=True)
class DifficultyReason:
    code: str
    label: str


@dataclass(frozen=True, slots=True)
class PracticeSegment:
    start_seconds: float
    end_seconds: float
    difficulty: str
    reasons: tuple[DifficultyReason, ...]
    repeat_group_id: str | None = None


def build_practice_timeline(
    frames: list[PoseFrame] | tuple[PoseFrame, ...],
    *,
    beats: tuple[float, ...] = (),
    min_duration: float = 0.5,
    max_duration: float = 8.0,
) -> tuple[PracticeSegment, ...]:
    if not frames:
        return ()
    if min_duration <= 0 or max_duration < min_duration:
        raise ValueError("invalid segment duration bounds")
    chunks: list[list[PoseFrame]] = [[]]
    for frame in frames:
        if chunks[-1] and frame.time_seconds - chunks[-1][-1].time_seconds > 1.5:
            chunks.append([])
        chunks[-1].append(frame)
    segments: list[PracticeSegment] = []
    for chunk in chunks:
        start = _snap(chunk[0].time_seconds, beats)
        end = _snap(chunk[-1].time_seconds, beats)
        if end - start < min_duration:
            end = min(chunk[-1].time_seconds + min_duration, chunk[0].time_seconds + max_duration)
        displacement = sum(
            abs(current.box[0] - previous.box[0]) + abs(current.box[1] - previous.box[1])
            for previous, current in zip(chunk, chunk[1:])
        )
        reasons = (DifficultyReason("displacement", "位移变化明显"),) if displacement >= 0.2 else ()
        difficulty = "hard" if displacement >= 0.8 else "medium" if displacement >= 0.2 else "easy"
        segments.append(PracticeSegment(start, end, difficulty, reasons))
    return _assign_repeats(segments)


def _snap(value: float, beats: tuple[float, ...]) -> float:
    if not beats:
        return value
    nearest = min(beats, key=lambda beat: abs(beat - value))
    return nearest if abs(nearest - value) <= 0.15 else value


def _assign_repeats(segments: list[PracticeSegment]) -> tuple[PracticeSegment, ...]:
    signatures: dict[tuple[str, int], str] = {}
    counts: dict[str, int] = {}
    result: list[PracticeSegment] = []
    for segment in segments:
        signature = (segment.difficulty, round(segment.end_seconds - segment.start_seconds))
        group = signatures.get(signature)
        if group is None:
            counts[segment.difficulty] = counts.get(segment.difficulty, 0) + 1
            group = f"repeat-{len(signatures) + 1}"
            signatures[signature] = group
        result.append(segment.__class__(segment.start_seconds, segment.end_seconds, segment.difficulty, segment.reasons, group if len(segments) > 1 else None))
    return tuple(result)
