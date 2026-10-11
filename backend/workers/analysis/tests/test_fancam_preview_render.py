from __future__ import annotations

import importlib
import importlib.util
import json
from pathlib import Path
import subprocess

import cv2
import numpy as np
import pytest

from stage_lab_analysis.detection import NormalizedBox


@pytest.fixture
def renderer():
    name = "stage_lab_analysis.fancam_demo.preview_render"
    assert importlib.util.find_spec(name) is not None, "preview renderer is not implemented"
    return importlib.import_module(name)


@pytest.mark.parametrize("missing_policy", ["bridge", "hold"])
def test_mask_samples_are_not_counted_as_identity_observations(renderer, missing_policy):
    body = NormalizedBox(.3, .2, .1, .6)
    samples = ((0., body), (.1, body), (.2, body))
    boxes = renderer._camera_boxes(samples, (0., .1, .2), 7, 30,
                                  inferred_times={.1}, missing_policy=missing_policy)
    assert not boxes[0][1]
    assert all(boxes[i][1] for i in range(1, 6))
    assert not boxes[6][1]


@pytest.mark.parametrize("shape,box", [
    ((1080, 1920), NormalizedBox(.45, .1, .1, .8)),
    ((1920, 1080), NormalizedBox(.3, .2, .4, .6)),
    ((960, 540), NormalizedBox(.0, .0, .3, 1.)),
    ((320, 640), NormalizedBox(.1, .2, .8, .6)),
])
def test_portrait_geometry_preserves_full_body(renderer, shape, box):
    h, w = shape
    bounds = renderer._crop_bounds(box, w, h)
    if bounds is None:
        image = np.full((h, w, 3), 180, np.uint8)
        frame, focused = renderer._compose_frame(image, box, 180, 320)
        assert not focused
        assert np.array_equal(frame, renderer._letterbox(image, 180, 320))
        return
    left, top, right, bottom = bounds
    assert (right-left)*16 == (bottom-top)*9
    assert 0 <= left <= box.x*w
    assert 0 <= top <= box.y*h
    assert (box.x+box.width)*w <= right <= w
    assert (box.y+box.height)*h <= bottom <= h
    # Both axes retain at least the clipped twenty-percent body margin.
    assert left <= max(0, (box.x-.2*box.width)*w)
    assert top <= max(0, (box.y-.2*box.height)*h)
    assert right >= min(w, (box.x+1.2*box.width)*w)
    assert bottom >= min(h, (box.y+1.2*box.height)*h)


def test_interpolation_and_uncertain_boundaries(renderer):
    a = NormalizedBox(.1, .2, .1, .6)
    b = NormalizedBox(.3, .2, .1, .6)
    samples = ((.1, a), (.5, b), (.6, None), (.7, a), (1.3, b))
    times = tuple(t for t, _ in samples)
    assert renderer._box_at(samples, times, .3).x == pytest.approx(.2)
    for t in (.55, .6, .65):
        box, inferred = renderer._resolve_box_at(samples, times, t)
        assert box is not None
        assert inferred is True
    for t in (0., 1., 1.31):
        assert renderer._box_at(samples, times, t) is None
    assert renderer._box_at((), (), 0.) is None


def test_bounded_occlusion_is_bridged_only_between_accepted_boxes(renderer):
    before = NormalizedBox(.1, .2, .1, .6)
    after = NormalizedBox(.5, .2, .1, .6)
    samples = ((0., before), (.5, None), (1., None), (1.5, after))
    times = tuple(t for t, _ in samples)

    box, inferred = renderer._resolve_box_at(samples, times, .75)

    assert inferred is True
    assert box.x == pytest.approx(.3)
    assert renderer._resolve_box_at(samples, times, 1.6) == (None, False)


def test_long_occlusion_is_not_bridged(renderer):
    box = NormalizedBox(.1, .2, .1, .6)
    bridgeable = ((0., box), (2., None), (4., box))
    bridgeable_times = tuple(t for t, _ in bridgeable)
    bridged, inferred = renderer._resolve_box_at(bridgeable, bridgeable_times, 2.)
    assert bridged == box
    assert inferred is True

    samples = ((0., box), (.5, None), (6., None), (6.1, box))
    times = tuple(t for t, _ in samples)

    assert renderer._resolve_box_at(samples, times, 1.5) == (None, False)


def test_fallback_keeps_entire_stage_without_stretching(renderer):
    stage = np.full((180, 320, 3), (30, 90, 160), np.uint8)
    stage[:, :12] = (0, 255, 0)
    stage[:, -12:] = (255, 0, 0)
    frame, focused = renderer._compose_frame(stage, None, 180, 320)
    assert not focused
    assert frame.shape == (320, 180, 3)
    assert not frame[:100].any()
    assert frame[160, 1, 1] == 255
    assert frame[160, -2, 0] == 255


def test_camera_keeps_standing_scale_through_brief_crouch(renderer):
    standing = NormalizedBox(.4, .1, .15, .8)
    crouch = NormalizedBox(.4, .5, .15, .4)
    samples = tuple((i/10, crouch if 9 <= i <= 11 else standing) for i in range(21))
    camera = renderer._camera_boxes(samples, tuple(t for t, _ in samples), 21, 10)
    box, _ = camera[10]
    assert box.height >= .79
    assert box.y <= crouch.y
    assert box.y+box.height >= crouch.y+crouch.height
    assert renderer._camera_boxes(((0., None),), (0.,), 1, 10) == [(None, False)]


def test_inferred_partial_boxes_do_not_erase_last_reliable_scale(renderer):
    standing = NormalizedBox(.4, .1, .15, .8)
    partial = NormalizedBox(.43, .5, .09, .3)
    samples = ((0., standing),) + tuple((i / 10, partial) for i in range(1, 31))
    inferred_times = {t for t, _ in samples[1:]}

    camera = renderer._camera_boxes(
        samples, tuple(t for t, _ in samples), 31, 10,
        inferred_times=inferred_times, missing_policy='hold')

    assert all(box.height >= .79 for box, _ in camera)
    assert all(box.y <= partial.y and box.y + box.height >= partial.y + partial.height
               for box, _ in camera[1:])


def test_camera_holds_last_reliable_framing_through_brief_dropout(renderer):
    box = NormalizedBox(.4, .1, .15, .8)
    samples = ((0., box), (.1, box), (.2, None), (.3, None), (.4, box),
               (.5, None), (.6, None))

    camera = renderer._camera_boxes(samples, tuple(t for t, _ in samples), 7, 10)

    assert all(item[0] is not None for item in camera)
    assert all(camera[index][1] is True for index in (2, 3, 5, 6))


def test_camera_follows_fast_horizontal_move_without_inflating_subject_box(renderer):
    left = NormalizedBox(.1, .1, .12, .8)
    right = NormalizedBox(.75, .1, .12, .8)
    samples = ((0., left), (.1, left), (.2, right), (.3, right))

    camera = renderer._camera_boxes(samples, tuple(t for t, _ in samples), 4, 10)

    for (_, source), (box, _) in zip(samples, camera):
        assert box.width <= .13
        assert box.x <= source.x
        assert box.x + box.width >= source.x + source.width


def test_camera_holds_last_composable_box_through_brief_geometry_glitch(renderer):
    reliable = NormalizedBox(.4, .2, .12, .5)
    impossible = NormalizedBox(.1, .1, .8, .8)

    selected, inferred = renderer._composable_camera_box(
        impossible, reliable, 1920, 1080, age_frames=15, max_hold_frames=15)
    expired, expired_inferred = renderer._composable_camera_box(
        impossible, reliable, 1920, 1080, age_frames=16, max_hold_frames=15)

    assert selected == reliable
    assert inferred is True
    assert expired == impossible
    assert expired_inferred is False


def test_hold_freezes_last_camera_without_future_gap_smoothing(renderer):
    standing = NormalizedBox(.1, .1, .15, .6)
    crouch = NormalizedBox(.2, .4, .1, .3)
    future = NormalizedBox(.65, .1, .2, .8)
    samples = ((0., standing), (.2, crouch), (.3, None), (.4, None),
               (.5, None), (.6, future))
    camera = renderer._camera_boxes(samples, tuple(t for t, _ in samples), 7, 10,
                                    missing_policy="hold")
    prefix = renderer._camera_boxes(samples[:5], tuple(t for t, _ in samples[:5]),
                                    7, 10, missing_policy="hold")

    assert camera[2][0].height > crouch.height
    assert camera[:6] == prefix[:6]
    assert camera[3:6] == [(camera[2][0], True)] * 3
    assert camera[6][0].x == pytest.approx(future.x)
    assert camera[6][1] is False


def test_hold_interpolates_adjacent_observations(renderer):
    left = NormalizedBox(.1, .2, .1, .4)
    right = NormalizedBox(.3, .2, .1, .4)
    camera = renderer._camera_boxes(((0., left), (.4, right)), (0., .4), 5, 10,
                                    missing_policy="hold")

    assert camera[2][0].x == pytest.approx(.2)
    assert all(box is not None and not inferred for box, inferred in camera)


def test_hold_leading_trailing_and_long_absence(renderer):
    body = NormalizedBox(.4, .2, .1, .4)
    samples = ((0., None), (.1, None), (.2, body), (.3, None),
               (.9, None), (1., body), (1.1, None))
    camera = renderer._camera_boxes(samples, tuple(t for t, _ in samples), 17, 10,
                                    missing_policy="hold")

    assert all(camera[i] == (None, False) for i in (0, 1, 8, 9, 16))
    assert all(camera[i][0] == body and not camera[i][1] for i in (2, 10))
    assert all(camera[i] == (body, True) for i in (*range(3, 8), *range(11, 16)))
    assert renderer._camera_boxes((), (), 2, 10, missing_policy="hold") == [
        (None, False), (None, False)]


@pytest.mark.parametrize("fps,last_observation,hold_seconds,last_focused_frame", [
    (10, .25, .25, 5), (30, .07, .03, 3), (1, 0., .5, 0),
    (10, .2, 0., 2), (10, .2, .2, 4), (10, .2, .1, 3), (10, .2, 1., 12),
    (10, .1, .7, 8),
])
def test_hold_timeout_uses_actual_observation_time(
        renderer, fps, last_observation, hold_seconds, last_focused_frame):
    body = NormalizedBox(.4, .2, .1, .4)
    samples = ((0., body),)
    if last_observation:
        samples += ((last_observation, body),)
    samples += ((last_observation + .01, None),)
    camera = renderer._camera_boxes(
        samples, tuple(t for t, _ in samples), last_focused_frame + 2, fps,
        missing_policy="hold", hold_seconds=hold_seconds)

    assert all(box == body for box, _ in camera[:-1])
    assert all(inferred == (i/fps > last_observation)
               for i, (_, inferred) in enumerate(camera[:-1]))
    assert camera[-1] == (None, False)


def test_bridge_default_remains_unchanged(renderer):
    left = NormalizedBox(.1, .2, .1, .4)
    right = NormalizedBox(.5, .2, .1, .4)
    samples = ((0., left), (.1, None), (.8, right), (1.2, None))
    times = tuple(t for t, _ in samples)
    default = renderer._camera_boxes(samples, times, 17, 10)

    assert default == renderer._camera_boxes(samples, times, 17, 10,
                                             missing_policy="bridge", hold_seconds=0.)
    assert default[4][0].x == pytest.approx(.3)
    assert default[4][1] is True


@pytest.fixture
def source(tmp_path):
    path = tmp_path / "synthetic.mp4"
    subprocess.run([
        "ffmpeg", "-v", "error", "-nostdin", "-n", "-f", "lavfi",
        "-i", "testsrc2=size=320x180:rate=12:duration=1", "-an",
        "-c:v", "libx264", "-pix_fmt", "yuv420p", str(path),
    ], check=True, capture_output=True)
    return path


def probe(path):
    return json.loads(subprocess.run([
        "ffprobe", "-v", "error", "-show_streams", "-show_format",
        "-of", "json", str(path),
    ], check=True, capture_output=True, text=True).stdout)


def test_synthetic_render_shape_duration_faststart_and_privacy(renderer, source, tmp_path):
    output = tmp_path / "preview.mp4"
    box = NormalizedBox(.45, .2, .1, .6)
    report = renderer.render_preview(source, output,
        ((0., box), (.4, box), (.5, None), (.9, box)),
        duration=1., fps=30, width=180, height=320)
    stream = probe(output)["streams"][0]
    assert (stream["width"], stream["height"]) == (180, 320)
    assert stream["codec_name"] == "h264"
    assert stream["pix_fmt"] == "yuv420p"
    assert int(stream["nb_frames"]) == 30
    assert float(stream["duration"]) == pytest.approx(1., abs=1/30)
    data = output.read_bytes()
    assert data.index(b"moov") < data.index(b"mdat")
    assert report["frame_count"] == 30
    assert report["focused_frames"] == 30
    assert report["focused_frames"] + report["fallback_frames"] == 30
    assert report["focused_frames"] == report["observed_frames"] + report["bridged_frames"]
    assert report["bridged_frames"] > 0
    assert str(source) not in json.dumps(report)
    assert not {"samples", "boxes", "features", "source"} & report.keys()
    assert set(tmp_path.iterdir()) == {source, output}


def test_synthetic_hold_render_expires_without_geometry_rehold(renderer, source, tmp_path):
    left = NormalizedBox(.1, .2, .1, .4)
    right = NormalizedBox(.7, .2, .1, .4)
    samples = ((0., left), (.25, left), (.3, None), (.6, None),
               (.7, right), (.8, None))
    output = tmp_path / "hold.mp4"
    report = renderer.render_preview(
        source, output, samples, duration=1., fps=10, width=180, height=320,
        missing_policy="hold", hold_seconds=.15)

    assert report["frame_count"] == 10
    assert report["observed_frames"] == 4
    assert report["bridged_frames"] == 3
    assert report["focused_frames"] == 7
    assert report["fallback_frames"] == 3
    stream = probe(output)["streams"][0]
    assert (stream["width"], stream["height"], int(stream["nb_frames"])) == (180, 320, 10)
    capture = cv2.VideoCapture(str(output))
    try:
        for index in range(10):
            ok, frame = capture.read()
            assert ok and frame.shape == (320, 180, 3)
            # Full-stage letterboxing is visible well below the text overlay.
            if index in (5, 6, 9):
                assert frame[40:70].max() < 8
            else:
                assert frame[40:70].mean() > 10
        assert not capture.read()[0]
    finally:
        capture.release()
    assert set(tmp_path.iterdir()) == {source, output}


@pytest.mark.parametrize("options", [
    {"missing_policy": "predict"}, {"missing_policy": None}, {"missing_policy": []},
    {"hold_seconds": -.1}, {"hold_seconds": float("nan")},
    {"hold_seconds": float("inf")}, {"hold_seconds": float("-inf")},
    {"hold_seconds": True}, {"hold_seconds": False},
    {"hold_seconds": ".5"}, {"hold_seconds": None},
])
def test_invalid_missing_options_fail_before_media_io(renderer, tmp_path, options):
    with pytest.raises(ValueError, match="missing_policy|hold_seconds"):
        renderer.render_preview(tmp_path / "missing.mp4", tmp_path / "out.mp4", (),
                                duration=1., **options)
    assert not list(tmp_path.iterdir())


@pytest.mark.parametrize("kind", ["file", "symlink"])
def test_refuses_overwrite(renderer, tmp_path, kind):
    output = tmp_path / "existing.mp4"
    if kind == "file":
        output.write_bytes(b"keep me")
    else:
        output.symlink_to(tmp_path / "missing-target")
    with pytest.raises(FileExistsError):
        renderer.render_preview(tmp_path / "missing.mp4", output, (), duration=1)
    assert output.is_symlink() if kind == "symlink" else output.read_bytes() == b"keep me"


def test_missing_parent_is_not_created(renderer, source, tmp_path):
    output = tmp_path / "missing" / "preview.mp4"
    with pytest.raises(FileNotFoundError):
        renderer.render_preview(source, output, (), duration=1.)
    assert not output.parent.exists()


def test_short_source_does_not_publish_partial_output(renderer, source, tmp_path):
    output = tmp_path / "preview.mp4"
    with pytest.raises((ValueError, RuntimeError)):
        renderer.render_preview(source, output, (), duration=2., width=180, height=320)
    assert set(tmp_path.iterdir()) == {source}


def test_atomic_publish_race_preserves_other_file(renderer, source, tmp_path, monkeypatch):
    output = tmp_path / "preview.mp4"
    real_link = renderer.os.link

    def competing_publish(src, dst):
        Path(dst).write_bytes(b"other writer")
        real_link(src, dst)

    monkeypatch.setattr(renderer.os, "link", competing_publish)
    with pytest.raises(FileExistsError):
        renderer.render_preview(source, output, (), duration=.2, width=180, height=320)
    assert output.read_bytes() == b"other writer"
    assert set(tmp_path.iterdir()) == {source, output}


def test_optional_delayed_audio_preserves_timeline(renderer, source, tmp_path):
    with_audio = tmp_path / "audio-source.mp4"
    subprocess.run([
        "ffmpeg", "-v", "error", "-nostdin", "-n", "-i", str(source),
        "-itsoffset", "0.3", "-f", "lavfi", "-i",
        "sine=frequency=440:sample_rate=48000:duration=0.5",
        "-map", "0:v:0", "-map", "1:a:0", "-c:v", "copy",
        "-c:a", "aac", str(with_audio),
    ], check=True, capture_output=True)
    output = tmp_path / "preview.mp4"
    renderer.render_preview(with_audio, output, (), duration=1., width=180, height=320)
    streams = probe(output)["streams"]
    assert {s["codec_type"] for s in streams} == {"video", "audio"}
    assert float(probe(output)["format"]["duration"]) == pytest.approx(1., abs=.05)
    pcm = subprocess.run([
        "ffmpeg", "-v", "error", "-i", str(output), "-map", "0:a:0",
        "-f", "f32le", "-ac", "1", "-ar", "48000", "pipe:1",
    ], check=True, capture_output=True).stdout
    signal = np.frombuffer(pcm, dtype="<f4")
    assert np.max(np.abs(signal[:9600])) < .005
    assert np.max(np.abs(signal[19200:28800])) > .05


@pytest.mark.parametrize("options,samples", [
    ({"duration": 0}, ()), ({"duration": float("nan")}, ()),
    ({"fps": 0}, ()), ({"width": 541}, ()), ({"height": 540}, ()),
    ({}, ((.5, None), (.4, None))), ({}, ((0., None), (0., None))),
])
def test_invalid_arguments_do_not_create_files(renderer, source, tmp_path, options, samples):
    params = {"duration": 1., **options}
    with pytest.raises(ValueError):
        renderer.render_preview(source, tmp_path / "out.mp4", samples, **params)
    assert set(tmp_path.iterdir()) == {source}
