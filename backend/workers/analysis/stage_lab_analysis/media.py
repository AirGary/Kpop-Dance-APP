from __future__ import annotations

import fcntl
import json
import math
import os
import subprocess
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path
from typing import Any

from .errors import MediaError


MAX_DURATION_SECONDS = 360.0
MAX_FILE_SIZE_BYTES = 2 * 1024**3
PROBE_TIMEOUT_SECONDS = 30
MIN_TRANSCODE_TIMEOUT_SECONDS = 180
MAX_TRANSCODE_TIMEOUT_SECONDS = 3600
SUPPORTED_VIDEO_CODECS = frozenset({"h264", "hevc"})
SUPPORTED_CONTAINER_NAMES = frozenset({"mov", "mp4"})


@dataclass(frozen=True, slots=True)
class MediaReport:
    duration_seconds: float
    width: int
    height: int
    fps: float
    rotation_degrees: int
    video_codec: str
    has_audio: bool


@dataclass(frozen=True, slots=True)
class _MediaDetails:
    report: MediaReport
    format_name: str
    pixel_format: str | None
    average_fps: float | None
    real_fps: float | None
    frame_rates: tuple[float, ...]
    selected_stream_index: int
    video_start_time: float
    video_duration_seconds: float


def _positive_float(value: object) -> float:
    if isinstance(value, bool):
        raise ValueError
    result = float(value)
    if not math.isfinite(result) or result <= 0:
        raise ValueError
    return result


def _finite_float(value: object) -> float:
    if isinstance(value, bool):
        raise ValueError
    result = float(value)
    if not math.isfinite(result):
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


def _optional_stream_rate(value: object) -> float | None:
    unavailable = (None, "", "N/A", "0/0", "0/1")
    return None if value in unavailable else _fps(value)


def _stream_rates(
    stream: dict[str, Any],
) -> tuple[float | None, float | None, tuple[float, ...]]:
    average_fps = _optional_stream_rate(stream.get("avg_frame_rate"))
    real_fps = _optional_stream_rate(stream.get("r_frame_rate"))
    rates = tuple(rate for rate in (average_fps, real_fps) if rate is not None)
    if not rates:
        raise ValueError
    return average_fps, real_fps, rates


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
    try:
        if source.stat().st_size > MAX_FILE_SIZE_BYTES:
            raise MediaError("file_size_exceeded")
    except MediaError:
        raise
    except OSError as error:
        raise MediaError("media_corrupt") from error

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


def _is_attached_picture(stream: dict[str, Any]) -> bool:
    disposition = stream.get("disposition")
    return isinstance(disposition, dict) and disposition.get("attached_pic") == 1


def _is_default_stream(stream: dict[str, Any]) -> bool:
    disposition = stream.get("disposition")
    return isinstance(disposition, dict) and disposition.get("default") == 1


def _inspect(source: Path) -> _MediaDetails:
    payload = _run_probe(source)
    streams = payload.get("streams")
    if not isinstance(streams, list):
        raise MediaError("media_corrupt")

    format_data = payload.get("format")
    format_name = (
        format_data.get("format_name") if isinstance(format_data, dict) else None
    )
    if not isinstance(format_name, str) or not (
        set(format_name.split(",")) & SUPPORTED_CONTAINER_NAMES
    ):
        raise MediaError("codec_unsupported")

    video_streams = [
        stream
        for stream in streams
        if isinstance(stream, dict)
        and stream.get("codec_type") == "video"
        and not _is_attached_picture(stream)
    ]
    if not video_streams:
        raise MediaError("video_track_missing")
    video_stream = next(
        (stream for stream in video_streams if _is_default_stream(stream)),
        video_streams[0],
    )

    codec = video_stream.get("codec_name")
    if not isinstance(codec, str) or codec not in SUPPORTED_VIDEO_CODECS:
        raise MediaError("codec_unsupported")

    stream_duration = video_stream.get("duration")
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
        video_duration = _positive_float(
            stream_duration
            if stream_duration not in (None, "N/A")
            else format_duration
        )
        width = _positive_int(video_stream.get("width"))
        height = _positive_int(video_stream.get("height"))
        average_fps, real_fps, frame_rates = _stream_rates(video_stream)
        frame_rate = max(frame_rates)
        rotation = _rotation(video_stream)
        raw_start_time = video_stream.get("start_time")
        if raw_start_time in (None, "N/A"):
            raw_start_time = (
                format_data.get("start_time")
                if isinstance(format_data, dict)
                else None
            )
        video_start_time = (
            0.0 if raw_start_time in (None, "N/A") else _finite_float(raw_start_time)
        )
        selected_stream_index = video_stream.get("index")
        if (
            isinstance(selected_stream_index, bool)
            or not isinstance(selected_stream_index, int)
            or selected_stream_index < 0
        ):
            raise ValueError
    except (TypeError, ValueError, OverflowError, ZeroDivisionError) as error:
        raise MediaError("media_corrupt") from error

    if duration > MAX_DURATION_SECONDS:
        raise MediaError("duration_exceeded")

    has_audio = any(
        isinstance(stream, dict) and stream.get("codec_type") == "audio"
        for stream in streams
    )
    pixel_format = video_stream.get("pix_fmt")
    return _MediaDetails(
        report=MediaReport(
            duration_seconds=duration,
            width=width,
            height=height,
            fps=frame_rate,
            rotation_degrees=rotation,
            video_codec=codec,
            has_audio=has_audio,
        ),
        format_name=format_name,
        pixel_format=pixel_format if isinstance(pixel_format, str) else None,
        average_fps=average_fps,
        real_fps=real_fps,
        frame_rates=frame_rates,
        selected_stream_index=selected_stream_index,
        video_start_time=video_start_time,
        video_duration_seconds=video_duration,
    )


def preflight(source: Path) -> MediaReport:
    return _inspect(Path(source)).report


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


def _transcode_timeout_seconds(duration_seconds: float) -> int:
    scaled = math.ceil(duration_seconds * 10)
    return min(
        MAX_TRANSCODE_TIMEOUT_SECONDS,
        max(MIN_TRANSCODE_TIMEOUT_SECONDS, scaled),
    )


def _transcode(source: Path, temporary: Path, details: _MediaDetails) -> None:
    report = details.report
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
        f"0:{details.selected_stream_index}",
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
            timeout=_transcode_timeout_seconds(details.video_duration_seconds),
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise MediaError("ffmpeg_failed") from error
    if result.returncode != 0:
        raise MediaError("ffmpeg_failed")


def _validate_proxy(source: _MediaDetails, proxy: _MediaDetails) -> None:
    _validate_general_proxy(proxy)
    source_report = source.report
    proxy_report = proxy.report
    source_display_width, source_display_height = _display_dimensions(source_report)
    display_width, display_height = _display_dimensions(proxy_report)
    duration_tolerance = max(
        0.1,
        2.0 / min(source_report.fps, proxy_report.fps),
    )
    if (
        proxy_report.fps > min(source_report.fps, 30.0)
        or display_width > source_display_width
        or display_height > source_display_height
        or proxy_report.has_audio != source_report.has_audio
        or abs(proxy.video_duration_seconds - source.video_duration_seconds)
        > duration_tolerance
    ):
        raise MediaError("ffmpeg_failed")


def _validate_general_proxy(details: _MediaDetails) -> None:
    report = details.report
    display_width, display_height = _display_dimensions(report)
    max_width, max_height = (
        (720, 1280) if display_height > display_width else (1280, 720)
    )
    if (
        report.video_codec != "h264"
        or details.pixel_format != "yuv420p"
        or display_width > max_width
        or display_height > max_height
        or report.fps > 30.0
        or any(rate > 30.0 for rate in details.frame_rates)
        or abs(details.video_start_time) > max(0.05, 1.0 / report.fps)
    ):
        raise MediaError("ffmpeg_failed")


@contextmanager
def _destination_lock(destination: Path) -> Iterator[None]:
    lock_path = destination.parent / f".{destination.name}.lock"
    try:
        with lock_path.open("a+b") as lock_file:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
    except OSError as error:
        raise MediaError("ffmpeg_failed") from error


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
    destination.parent.mkdir(parents=True, exist_ok=True)
    with _destination_lock(destination):
        if destination.exists():
            try:
                existing_details = _inspect(destination)
                _validate_general_proxy(existing_details)
                return existing_details.report
            except MediaError:
                pass

        source_details = _inspect(source)
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{destination.name}.tmp-",
            suffix=".mp4",
            dir=destination.parent,
        )
        os.close(descriptor)
        temporary = Path(temporary_name)
        try:
            _transcode(source, temporary, source_details)
            try:
                proxy_details = _inspect(temporary)
                _validate_proxy(source_details, proxy_details)
            except MediaError as error:
                raise MediaError("ffmpeg_failed") from error
            _fsync_file(temporary)
            os.replace(temporary, destination)
            _fsync_directory(destination.parent)
            return proxy_details.report
        finally:
            temporary.unlink(missing_ok=True)
