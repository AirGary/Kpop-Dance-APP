from __future__ import annotations

import json
import subprocess
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from stage_lab_analysis import media as media_module
from stage_lab_analysis.errors import MediaError
from stage_lab_analysis.media import MediaReport, create_proxy, preflight


FIXTURE_SCRIPT = Path(__file__).parent / "fixtures" / "generate_media_fixtures.sh"
MOV_FORMAT_NAME = "mov,mp4,m4a,3gp,3g2,mj2"


@pytest.fixture(scope="session")
def media_fixtures(tmp_path_factory: pytest.TempPathFactory) -> Path:
    directory = tmp_path_factory.mktemp("media-fixtures")
    subprocess.run(
        [str(FIXTURE_SCRIPT), str(directory)],
        check=True,
        shell=False,
        timeout=60,
    )
    return directory


def assert_media_error(error: pytest.ExceptionInfo[MediaError], code: str) -> None:
    assert error.value.code == code
    assert str(error.value) == code


def test_preflight_reports_supported_h264_media(media_fixtures: Path) -> None:
    report = preflight(media_fixtures / "4k60-h264.mp4")

    assert report == MediaReport(
        duration_seconds=pytest.approx(0.2, abs=0.05),
        width=3840,
        height=2160,
        fps=pytest.approx(60.0),
        rotation_degrees=0,
        video_codec="h264",
        has_audio=True,
    )


def test_preflight_reports_rotation_from_mov_side_data(media_fixtures: Path) -> None:
    report = preflight(media_fixtures / "rotated.mov")

    assert report.rotation_degrees == 90


def test_preflight_allows_video_without_audio(media_fixtures: Path) -> None:
    assert preflight(media_fixtures / "no-audio.mp4").has_audio is False


@pytest.mark.parametrize(
    ("fixture_name", "code"),
    [
        ("corrupt.mp4", "media_corrupt"),
        ("audio-only.m4a", "video_track_missing"),
        ("over-six-minutes.mp4", "duration_exceeded"),
    ],
)
def test_preflight_returns_stable_media_errors(
    media_fixtures: Path, fixture_name: str, code: str
) -> None:
    with pytest.raises(MediaError) as error:
        preflight(media_fixtures / fixture_name)

    assert_media_error(error, code)


def test_preflight_rejects_sparse_file_over_two_gib_before_ffprobe(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    source = tmp_path / "oversize.mp4"
    with source.open("wb") as file:
        file.truncate(2 * 1024**3 + 1)

    def unexpected_probe(*args, **kwargs):
        pytest.fail("ffprobe must not run for an oversized file")

    monkeypatch.setattr(subprocess, "run", unexpected_probe)

    with pytest.raises(MediaError) as error:
        preflight(source)

    assert_media_error(error, "file_size_exceeded")


def test_preflight_rejects_h264_in_matroska_container(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    source = tmp_path / "clip.mkv"
    source.write_bytes(b"fixture")
    response = {
        "streams": [
            {
                "index": 0,
                "codec_type": "video",
                "codec_name": "h264",
                "width": 640,
                "height": 360,
                "avg_frame_rate": "24/1",
                "duration": "1.0",
            }
        ],
        "format": {"format_name": "matroska,webm", "duration": "1.0"},
    }
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda argv, **kwargs: subprocess.CompletedProcess(
            argv, 0, json.dumps(response), ""
        ),
    )

    with pytest.raises(MediaError) as error:
        preflight(source)

    assert_media_error(error, "codec_unsupported")


def _multi_stream_response() -> dict[str, object]:
    return {
        "streams": [
            {
                "index": 2,
                "codec_type": "video",
                "codec_name": "mjpeg",
                "pix_fmt": "yuvj420p",
                "width": 320,
                "height": 320,
                "avg_frame_rate": "1/1",
                "duration": "1.0",
                "disposition": {"attached_pic": 1, "default": 0},
            },
            {
                "index": 5,
                "codec_type": "video",
                "codec_name": "h264",
                "pix_fmt": "yuv420p",
                "width": 1280,
                "height": 720,
                "avg_frame_rate": "30/1",
                "r_frame_rate": "30/1",
                "start_time": "0",
                "duration": "1.0",
                "disposition": {"attached_pic": 0, "default": 1},
            },
        ],
        "format": {"format_name": MOV_FORMAT_NAME, "duration": "1.0"},
    }


def test_preflight_excludes_cover_art_and_prefers_default_video_stream(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    source = tmp_path / "multi.mp4"
    source.write_bytes(b"fixture")
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda argv, **kwargs: subprocess.CompletedProcess(
            argv, 0, json.dumps(_multi_stream_response()), ""
        ),
    )

    report = preflight(source)

    assert report.video_codec == "h264"
    assert (report.width, report.height) == (1280, 720)


def test_create_proxy_maps_selected_absolute_video_stream_index(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    source = tmp_path / "multi.mp4"
    source.write_bytes(b"source")
    destination = tmp_path / "proxy.mp4"
    mapped_streams: list[str] = []

    def proxy_response() -> dict[str, object]:
        return {
            "streams": [
                {
                    "index": 0,
                    "codec_type": "video",
                    "codec_name": "h264",
                    "pix_fmt": "yuv420p",
                    "width": 1280,
                    "height": 720,
                    "avg_frame_rate": "30/1",
                    "r_frame_rate": "30/1",
                    "start_time": "0",
                    "duration": "1.0",
                    "disposition": {"attached_pic": 0, "default": 1},
                }
            ],
            "format": {"format_name": MOV_FORMAT_NAME, "duration": "1.0"},
        }

    def fake_run(argv, **kwargs):
        if Path(argv[0]).name == "ffmpeg":
            mapped_streams.extend(
                argv[index + 1]
                for index, value in enumerate(argv)
                if value == "-map"
            )
            Path(argv[-1]).write_bytes(b"proxy")
            return subprocess.CompletedProcess(argv, 0, "", "")
        payload = (
            _multi_stream_response()
            if Path(argv[-1]) == source
            else proxy_response()
        )
        return subprocess.CompletedProcess(argv, 0, json.dumps(payload), "")

    monkeypatch.setattr(subprocess, "run", fake_run)

    create_proxy(source, destination)

    assert mapped_streams[0] == "0:5"


def test_preflight_rejects_unsupported_codec_without_leaking_probe_data(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    source = tmp_path / "private user clip.mkv"
    source.write_bytes(b"fixture")
    response = {
        "streams": [
            {
                "codec_type": "video",
                "codec_name": "vp9",
                "width": 640,
                "height": 360,
                "avg_frame_rate": "24/1",
                "duration": "1.0",
            }
        ],
        "format": {"format_name": MOV_FORMAT_NAME, "duration": "1.0"},
    }

    def fake_run(argv, **kwargs):
        assert isinstance(argv, list)
        assert kwargs["shell"] is False
        return subprocess.CompletedProcess(
            argv, 0, json.dumps(response), "secret stderr"
        )

    monkeypatch.setattr(subprocess, "run", fake_run)

    with pytest.raises(MediaError) as error:
        preflight(source)

    assert_media_error(error, "codec_unsupported")
    assert source.name not in str(error.value)
    assert "secret stderr" not in str(error.value)


@pytest.mark.parametrize(
    "bad_value",
    ["NaN", "Infinity", "0", "-1", "not-a-number"],
)
def test_preflight_rejects_invalid_numeric_metadata(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, bad_value: str
) -> None:
    source = tmp_path / "source.mp4"
    source.write_bytes(b"fixture")
    response = {
        "streams": [
            {
                "codec_type": "video",
                "codec_name": "h264",
                "width": 640,
                "height": 360,
                "avg_frame_rate": f"{bad_value}/1" if bad_value == "0" else bad_value,
                "duration": "1.0",
            }
        ],
        "format": {"format_name": MOV_FORMAT_NAME, "duration": "1.0"},
    }
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda argv, **kwargs: subprocess.CompletedProcess(
            argv, 0, json.dumps(response), ""
        ),
    )

    with pytest.raises(MediaError) as error:
        preflight(source)

    assert_media_error(error, "media_corrupt")


def test_preflight_parses_fractional_fps_and_tag_rotation(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    source = tmp_path / "source.mp4"
    source.write_bytes(b"fixture")
    response = {
        "streams": [
            {
                "index": 0,
                "codec_type": "video",
                "codec_name": "hevc",
                "width": 1920,
                "height": 1080,
                "avg_frame_rate": "30000/1001",
                "duration": "1.0",
                "tags": {"rotate": "-90"},
            }
        ],
        "format": {"format_name": MOV_FORMAT_NAME, "duration": "1.0"},
    }
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda argv, **kwargs: subprocess.CompletedProcess(
            argv, 0, json.dumps(response), ""
        ),
    )

    report = preflight(source)

    assert report.video_codec == "hevc"
    assert report.fps == pytest.approx(29.97002997)
    assert report.rotation_degrees == 270


def test_preflight_uses_longest_valid_duration_to_prevent_limit_bypass(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    source = tmp_path / "source.mp4"
    source.write_bytes(b"fixture")
    response = {
        "streams": [
            {
                "index": 0,
                "codec_type": "video",
                "codec_name": "h264",
                "width": 640,
                "height": 360,
                "avg_frame_rate": "24/1",
                "duration": "1.0",
            }
        ],
        "format": {"format_name": MOV_FORMAT_NAME, "duration": "361.0"},
    }
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda argv, **kwargs: subprocess.CompletedProcess(
            argv, 0, json.dumps(response), ""
        ),
    )

    with pytest.raises(MediaError) as error:
        preflight(source)

    assert_media_error(error, "duration_exceeded")


def test_preflight_falls_back_when_average_frame_rate_is_unknown(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    source = tmp_path / "source.mp4"
    source.write_bytes(b"fixture")
    response = {
        "streams": [
            {
                "index": 0,
                "codec_type": "video",
                "codec_name": "h264",
                "width": 640,
                "height": 360,
                "avg_frame_rate": "0/0",
                "r_frame_rate": "30000/1001",
                "duration": "1.0",
            }
        ],
        "format": {"format_name": MOV_FORMAT_NAME, "duration": "1.0"},
    }
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda argv, **kwargs: subprocess.CompletedProcess(
            argv, 0, json.dumps(response), ""
        ),
    )

    assert preflight(source).fps == pytest.approx(29.97002997)


def test_report_fps_is_maximum_of_all_valid_declared_rates(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    source = tmp_path / "source.mp4"
    source.write_bytes(b"fixture")
    response = {
        "streams": [
            {
                "index": 0,
                "codec_type": "video",
                "codec_name": "h264",
                "pix_fmt": "yuv420p",
                "width": 640,
                "height": 360,
                "avg_frame_rate": "1941/100",
                "r_frame_rate": "60/1",
                "start_time": "0",
                "duration": "1.0",
            }
        ],
        "format": {"format_name": MOV_FORMAT_NAME, "duration": "1.0"},
    }
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda argv, **kwargs: subprocess.CompletedProcess(
            argv, 0, json.dumps(response), ""
        ),
    )

    details = media_module._inspect(source)
    report = details.report

    assert report.fps == pytest.approx(60.0)
    assert details.average_fps == pytest.approx(19.41)
    assert details.real_fps == pytest.approx(60.0)
    assert "fps=30" in media_module._video_filter(report)


def test_create_proxy_rejects_vfr_proxy_with_any_rate_above_30(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    source = tmp_path / "source.mp4"
    source.write_bytes(b"source")
    destination = tmp_path / "existing.mp4"
    destination.write_bytes(b"existing")
    filters: list[str] = []

    def response(rate: str) -> str:
        return json.dumps(
            {
                "streams": [
                    {
                        "index": 0,
                        "codec_type": "video",
                        "codec_name": "h264",
                        "pix_fmt": "yuv420p",
                        "width": 640,
                        "height": 360,
                        "avg_frame_rate": "1941/100",
                        "r_frame_rate": rate,
                        "start_time": "0",
                        "duration": "1.0",
                    }
                ],
                "format": {
                    "format_name": MOV_FORMAT_NAME,
                    "duration": "1.0",
                },
            }
        )

    def fake_run(argv, **kwargs):
        if Path(argv[0]).name == "ffmpeg":
            filters.append(argv[argv.index("-vf") + 1])
            Path(argv[-1]).write_bytes(b"proxy")
            return subprocess.CompletedProcess(argv, 0, "", "")
        rate = "60/1" if Path(argv[-1]) == source else "30001/1000"
        return subprocess.CompletedProcess(argv, 0, response(rate), "")

    monkeypatch.setattr(subprocess, "run", fake_run)

    with pytest.raises(MediaError) as error:
        create_proxy(source, destination)

    assert_media_error(error, "ffmpeg_failed")
    assert filters and "fps=30" in filters[0]
    assert destination.read_bytes() == b"existing"


def test_create_proxy_downscales_4k60_to_720p30(
    media_fixtures: Path, tmp_path: Path
) -> None:
    destination = tmp_path / "proxy.mp4"

    report = create_proxy(media_fixtures / "4k60-h264.mp4", destination)

    assert destination.is_file()
    assert report.width <= 1280
    assert report.height <= 720
    assert report.fps <= 30.01
    assert report.video_codec == "h264"
    assert report.has_audio is True


def test_create_proxy_does_not_upscale_or_increase_fps(
    media_fixtures: Path, tmp_path: Path
) -> None:
    destination = tmp_path / "proxy.mp4"

    report = create_proxy(media_fixtures / "540p24.mp4", destination)

    assert (report.width, report.height) == (960, 540)
    assert report.fps == pytest.approx(24.0, abs=0.05)
    assert report.has_audio is False


def test_create_proxy_handles_rotated_portrait_within_portrait_bounds(
    media_fixtures: Path, tmp_path: Path
) -> None:
    destination = tmp_path / "portrait proxy.mp4"

    report = create_proxy(media_fixtures / "rotated.mov", destination)

    display_width, display_height = (
        (report.height, report.width)
        if report.rotation_degrees in (90, 270)
        else (report.width, report.height)
    )
    assert display_width <= 720
    assert display_height <= 1280


def test_create_proxy_supports_special_characters_without_shell_interpolation(
    media_fixtures: Path, tmp_path: Path
) -> None:
    source = tmp_path / "source ; $(touch injected).mp4"
    source.write_bytes((media_fixtures / "no-audio.mp4").read_bytes())
    destination = tmp_path / "result ; [safe] $video.mp4"

    create_proxy(source, destination)

    assert destination.is_file()
    assert not (tmp_path / "injected").exists()


def test_create_proxy_failure_preserves_existing_destination_and_hides_details(
    media_fixtures: Path, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    destination = tmp_path / "existing-private-name.mp4"
    original = b"existing destination"
    destination.write_bytes(original)
    real_run = subprocess.run

    def fail_ffmpeg(argv, **kwargs):
        if Path(argv[0]).name == "ffmpeg":
            return subprocess.CompletedProcess(argv, 1, "", "private failure details")
        return real_run(argv, **kwargs)

    monkeypatch.setattr(subprocess, "run", fail_ffmpeg)

    with pytest.raises(MediaError) as error:
        create_proxy(media_fixtures / "no-audio.mp4", destination)

    assert_media_error(error, "ffmpeg_failed")
    assert "private failure" not in str(error.value)
    assert destination.read_bytes() == original
    assert list(tmp_path.glob(".*.tmp-*.mp4")) == []


def test_create_proxy_rejects_wrong_pixel_format_before_publish(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    source = tmp_path / "source.mp4"
    source.write_bytes(b"source")
    destination = tmp_path / "existing.mp4"
    destination.write_bytes(b"existing")

    def probe_payload(pixel_format: str) -> str:
        return json.dumps(
            {
                "streams": [
                    {
                        "index": 0,
                        "codec_type": "video",
                        "codec_name": "h264",
                        "pix_fmt": pixel_format,
                        "width": 640,
                        "height": 360,
                        "avg_frame_rate": "24/1",
                        "duration": "1.0",
                    }
                ],
                "format": {"format_name": MOV_FORMAT_NAME, "duration": "1.0"},
            }
        )

    def fake_run(argv, **kwargs):
        if Path(argv[0]).name == "ffmpeg":
            Path(argv[-1]).write_bytes(b"proxy")
            return subprocess.CompletedProcess(argv, 0, "", "")
        pixel_format = "yuv420p" if Path(argv[-1]) == source else "yuv444p"
        return subprocess.CompletedProcess(argv, 0, probe_payload(pixel_format), "")

    monkeypatch.setattr(subprocess, "run", fake_run)

    with pytest.raises(MediaError) as error:
        create_proxy(source, destination)

    assert_media_error(error, "ffmpeg_failed")
    assert destination.read_bytes() == b"existing"


@pytest.mark.parametrize(
    ("proxy_duration", "proxy_start", "proxy_has_audio"),
    [
        ("0.20", "0", True),
        ("1.0", "1.0", True),
        ("1.0", "0", False),
    ],
    ids=["truncated", "nonzero-start", "audio-lost"],
)
def test_create_proxy_rejects_incomplete_output_before_publish(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    proxy_duration: str,
    proxy_start: str,
    proxy_has_audio: bool,
) -> None:
    source = tmp_path / "source.mp4"
    source.write_bytes(b"source")
    destination = tmp_path / "existing.mp4"
    destination.write_bytes(b"existing")
    transcoded = False

    def payload(duration: str, start: str, has_audio: bool) -> str:
        streams = [
            {
                "index": 0,
                "codec_type": "video",
                "codec_name": "h264",
                "pix_fmt": "yuv420p",
                "width": 640,
                "height": 360,
                "avg_frame_rate": "24/1",
                "r_frame_rate": "24/1",
                "start_time": start,
                "duration": duration,
            }
        ]
        if has_audio:
            streams.append({"index": 1, "codec_type": "audio"})
        return json.dumps(
            {
                "streams": streams,
                "format": {
                    "format_name": MOV_FORMAT_NAME,
                    "duration": duration,
                },
            }
        )

    def fake_run(argv, **kwargs):
        nonlocal transcoded
        if Path(argv[0]).name == "ffmpeg":
            transcoded = True
            Path(argv[-1]).write_bytes(b"proxy")
            return subprocess.CompletedProcess(argv, 0, "", "")
        probed = Path(argv[-1])
        if probed == destination and not transcoded:
            return subprocess.CompletedProcess(argv, 1, "", "invalid old file")
        response = (
            payload("1.0", "0", True)
            if probed == source
            else payload(proxy_duration, proxy_start, proxy_has_audio)
        )
        return subprocess.CompletedProcess(argv, 0, response, "private stderr")

    monkeypatch.setattr(subprocess, "run", fake_run)

    with pytest.raises(MediaError) as error:
        create_proxy(source, destination)

    assert_media_error(error, "ffmpeg_failed")
    assert destination.read_bytes() == b"existing"
    assert "private stderr" not in str(error.value)


def test_transcode_timeout_scales_for_six_minutes_and_has_hard_cap(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    source = tmp_path / "six-minutes.mp4"
    source.write_bytes(b"source")
    destination = tmp_path / "proxy.mp4"
    observed_timeouts: list[float] = []

    def payload() -> str:
        return json.dumps(
            {
                "streams": [
                    {
                        "index": 0,
                        "codec_type": "video",
                        "codec_name": "h264",
                        "pix_fmt": "yuv420p",
                        "width": 640,
                        "height": 360,
                        "avg_frame_rate": "24/1",
                        "r_frame_rate": "24/1",
                        "start_time": "0",
                        "duration": "360.0",
                    }
                ],
                "format": {
                    "format_name": MOV_FORMAT_NAME,
                    "duration": "360.0",
                },
            }
        )

    def fake_run(argv, **kwargs):
        if Path(argv[0]).name == "ffmpeg":
            observed_timeouts.append(kwargs["timeout"])
            Path(argv[-1]).write_bytes(b"proxy")
            return subprocess.CompletedProcess(argv, 0, "", "")
        return subprocess.CompletedProcess(argv, 0, payload(), "")

    monkeypatch.setattr(subprocess, "run", fake_run)

    create_proxy(source, destination)

    assert observed_timeouts == [3600]
    assert media_module._transcode_timeout_seconds(10_000) == 3600


def test_create_proxy_concurrent_writers_publish_valid_file(
    media_fixtures: Path, tmp_path: Path
) -> None:
    destination = tmp_path / "shared.mp4"

    with ThreadPoolExecutor(max_workers=2) as executor:
        reports = list(
            executor.map(
                lambda _: create_proxy(
                    media_fixtures / "no-audio.mp4", destination
                ),
                range(2),
            )
        )

    assert destination.is_file()
    assert preflight(destination).video_codec == "h264"
    assert all(report.video_codec == "h264" for report in reports)
    assert list(tmp_path.glob(".*.tmp-*.mp4")) == []


def test_create_proxy_first_writer_wins_for_different_sources(
    media_fixtures: Path, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    destination = tmp_path / "shared.mp4"
    first_source = media_fixtures / "540p24.mp4"
    second_source = media_fixtures / "no-audio.mp4"
    first_entered_transcode = threading.Event()
    real_transcode = media_module._transcode

    def delayed_transcode(source, temporary, details):
        if source == first_source:
            first_entered_transcode.set()
            time.sleep(0.3)
        real_transcode(source, temporary, details)

    monkeypatch.setattr(media_module, "_transcode", delayed_transcode)

    with ThreadPoolExecutor(max_workers=2) as executor:
        first = executor.submit(create_proxy, first_source, destination)
        assert first_entered_transcode.wait(timeout=2)
        second = executor.submit(create_proxy, second_source, destination)
        reports = [first.result(timeout=10), second.result(timeout=10)]

    final_report = preflight(destination)
    final_shape = (final_report.width, final_report.height, final_report.fps)
    assert all(
        (report.width, report.height, report.fps) == final_shape
        for report in reports
    )
    assert (tmp_path / ".shared.mp4.lock").is_file()


def test_create_proxy_does_not_modify_source(
    media_fixtures: Path, tmp_path: Path
) -> None:
    source = media_fixtures / "no-audio.mp4"
    before = source.read_bytes()

    create_proxy(source, tmp_path / "proxy.mp4")

    assert source.read_bytes() == before


def test_create_proxy_rejects_source_as_destination_without_modifying_it(
    media_fixtures: Path, tmp_path: Path
) -> None:
    source = tmp_path / "same.mp4"
    source.write_bytes((media_fixtures / "no-audio.mp4").read_bytes())
    before = source.read_bytes()

    with pytest.raises(MediaError) as error:
        create_proxy(source, source)

    assert_media_error(error, "ffmpeg_failed")
    assert source.read_bytes() == before
