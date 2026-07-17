from __future__ import annotations

import json
import math
import os
import subprocess
import tempfile
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path
from typing import Any

from .errors import MediaError


MAX_DURATION_SECONDS = 360.0
PROBE_TIMEOUT_SECONDS = 30
TRANSCODE_TIMEOUT_SECONDS = 180
SUPPORTED_VIDEO_CODECS = frozenset({"h264", "hevc"})


@dataclass(frozen=True, slots=True)
class MediaReport:
    duration_seconds: float
    width: int
    height: int
    fps: float
    rotation_degrees: int
    video_codec: str
    has_audio: bool


def _positive_float(value: object) -> float:
    if isinstance(value, bool):
        raise ValueError
    result = float(value)
    if not math.isfinite(result) or result <= 0:
        raise ValueError
    return result


def _positive_int(value: object) -> int:
    if isinstance(value, bool):
        raise ValueError
    result = int(value)
    if result <= 0 or isinstance(value, float) and not value.is_integer():
        raise ValueError
    return result


def _fps(value: object) -> float:
    if not isinstance(value, str) or not value.strip():
        raise ValueError
    result = float(Fraction(value))
    if not math.isfinite(result) or result <= 0:
        raise ValueError
    return result


def _stream_fps(stream: dict[str, Any]) -> float:
    average = stream.get("avg_frame_rate")
    value = (
        stream.get("r_frame_rate")
        if average in (None, "", "N/A", "0/0", "0/1")
        else average
    )
    return _fps(value)


def _rotation(stream: dict[str, Any]) -> int:
    candidates: list[object] = []
    tags = stream.get("tags")
    if isinstance(tags, dict) and "rotate" in tags:
        candidates.append(tags["rotate"])
    side_data = stream.get("side_data_list")
    if isinstance(side_data, list):
        candidates.extend(
            entry["rotation"]
            for entry in side_data
            if isinstance(entry, dict) and "rotation" in entry
        )

    if not candidates:
        return 0
    try:
        value = float(candidates[0])
    except (TypeError, ValueError, OverflowError) as error:
        raise ValueError from error
    if not math.isfinite(value):
        raise ValueError
    normalized = int(round(value)) % 360
    if normalized not in (0, 90, 180, 270):
        raise ValueError
    return normalized


def _load_probe_json(stdout: str) -> dict[str, Any]:
    def reject_constant(_: str) -> None:
        raise ValueError

    payload = json.loads(stdout, parse_constant=reject_constant)
    if not isinstance(payload, dict):
        raise ValueError
    return payload


def _run_probe(source: Path) -> dict[str, Any]:
    argv = [
        "ffprobe",
        "-v",
        "error",
        "-show_streams",
        "-show_format",
        "-of",
        "json",
        str(source),
    ]
    try:
        result = subprocess.run(
            argv,
            check=False,
            capture_output=True,
            text=True,
            shell=False,
            timeout=PROBE_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise MediaError("media_corrupt") from error
    if result.returncode != 0:
        raise MediaError("media_corrupt")
    try:
        return _load_probe_json(result.stdout)
    except (json.JSONDecodeError, TypeError, ValueError) as error:
        raise MediaError("media_corrupt") from error


def _inspect(source: Path) -> tuple[MediaReport, str | None]:
    payload = _run_probe(source)
    streams = payload.get("streams")
    if not isinstance(streams, list):
        raise MediaError("media_corrupt")

    video_stream = next(
        (
            stream
            for stream in streams
            if isinstance(stream, dict) and stream.get("codec_type") == "video"
        ),
        None,
    )
    if video_stream is None:
        raise MediaError("video_track_missing")

    codec = video_stream.get("codec_name")
    if not isinstance(codec, str) or codec not in SUPPORTED_VIDEO_CODECS:
        raise MediaError("codec_unsupported")

    stream_duration = video_stream.get("duration")
    format_data = payload.get("format")
    format_duration = (
        format_data.get("duration") if isinstance(format_data, dict) else None
    )
    try:
        duration_candidates = [
            _positive_float(value)
            for value in (stream_duration, format_duration)
            if value not in (None, "N/A")
        ]
        if not duration_candidates:
            raise ValueError
        duration = max(duration_candidates)
        width = _positive_int(video_stream.get("width"))
        height = _positive_int(video_stream.get("height"))
        frame_rate = _stream_fps(video_stream)
        rotation = _rotation(video_stream)
    except (TypeError, ValueError, OverflowError, ZeroDivisionError) as error:
        raise MediaError("media_corrupt") from error

    if duration > MAX_DURATION_SECONDS:
        raise MediaError("duration_exceeded")

    has_audio = any(
        isinstance(stream, dict) and stream.get("codec_type") == "audio"
        for stream in streams
    )
    pixel_format = video_stream.get("pix_fmt")
    return (
        MediaReport(
            duration_seconds=duration,
            width=width,
            height=height,
            fps=frame_rate,
            rotation_degrees=rotation,
            video_codec=codec,
            has_audio=has_audio,
        ),
        pixel_format if isinstance(pixel_format, str) else None,
    )


def preflight(source: Path) -> MediaReport:
    return _inspect(Path(source))[0]


def _display_dimensions(report: MediaReport) -> tuple[int, int]:
    if report.rotation_degrees in (90, 270):
        return report.height, report.width
    return report.width, report.height


def _video_filter(report: MediaReport) -> str:
    display_width, display_height = _display_dimensions(report)
    max_width, max_height = (
        (720, 1280) if display_height > display_width else (1280, 720)
    )
    filters = [
        (
            f"scale=w='min(iw,{max_width})':h='min(ih,{max_height})':"
            "force_original_aspect_ratio=decrease:force_divisible_by=2"
        ),
        "setsar=1",
    ]
    if report.fps > 30:
        filters.append("fps=30")
    filters.append("setpts=PTS-STARTPTS")
    return ",".join(filters)


def _transcode(source: Path, temporary: Path, report: MediaReport) -> None:
    argv = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
        "-nostdin",
        "-y",
        "-i",
        str(source),
        "-map",
        "0:v:0",
        "-map",
        "0:a:0?",
        "-vf",
        _video_filter(report),
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        "-preset",
        "veryfast",
        "-map_metadata",
        "-1",
    ]
    if report.has_audio:
        argv.extend(
            [
                "-af",
                "asetpts=PTS-STARTPTS",
                "-c:a",
                "aac",
            ]
        )
    argv.extend(["-movflags", "+faststart", str(temporary)])

    try:
        result = subprocess.run(
            argv,
            check=False,
            capture_output=True,
            text=True,
            shell=False,
            timeout=TRANSCODE_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise MediaError("ffmpeg_failed") from error
    if result.returncode != 0:
        raise MediaError("ffmpeg_failed")


def _validate_proxy(
    source: MediaReport, proxy: MediaReport, pixel_format: str | None
) -> None:
    source_display_width, source_display_height = _display_dimensions(source)
    display_width, display_height = _display_dimensions(proxy)
    max_width, max_height = (
        (720, 1280) if display_height > display_width else (1280, 720)
    )
    if (
        proxy.video_codec != "h264"
        or pixel_format != "yuv420p"
        or display_width > max_width
        or display_height > max_height
        or proxy.fps > min(source.fps, 30.0) + 0.01
        or display_width > source_display_width
        or display_height > source_display_height
    ):
        raise MediaError("ffmpeg_failed")


def _fsync_file(path: Path) -> None:
    with path.open("rb") as file:
        os.fsync(file.fileno())


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def create_proxy(source: Path, destination: Path) -> MediaReport:
    source = Path(source)
    destination = Path(destination)
    if source.resolve() == destination.resolve():
        raise MediaError("ffmpeg_failed")
    source_report = preflight(source)
    destination.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{destination.name}.tmp-",
        suffix=".mp4",
        dir=destination.parent,
    )
    os.close(descriptor)
    temporary = Path(temporary_name)
    try:
        _transcode(source, temporary, source_report)
        try:
            proxy_report, pixel_format = _inspect(temporary)
            _validate_proxy(source_report, proxy_report, pixel_format)
        except MediaError as error:
            raise MediaError("ffmpeg_failed") from error
        _fsync_file(temporary)
        os.replace(temporary, destination)
        _fsync_directory(destination.parent)
        return proxy_report
    finally:
        temporary.unlink(missing_ok=True)
