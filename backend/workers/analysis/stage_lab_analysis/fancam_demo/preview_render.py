"""Runtime-only full-body-box preview; this is not WholeBody acceptance.

Sample times are seconds from the first displayed source video frame. No boxes,
features, source paths or source metadata are written to the output or report.
Only a fully encoded MP4 is published, atomically and without replacement.
"""
from __future__ import annotations

from bisect import bisect_left, bisect_right
import json
import math
import os
from pathlib import Path
import re
import subprocess
import tempfile

import cv2
import numpy as np

from ..detection import NormalizedBox


_MAX_BRIDGED_OCCLUSION_SECONDS = 5.


def _interpolate_box(left, right, weight):
    values = [getattr(left, key)*(1-weight)+getattr(right, key)*weight
              for key in ("x", "y", "width", "height")]
    # Protect NormalizedBox's strict bounds against interpolation roundoff.
    values[2] = min(values[2], 1-values[0])
    values[3] = min(values[3], 1-values[1])
    return NormalizedBox(*values)


def _resolve_box_at(samples, times, timestamp, *, missing_policy="bridge"):
    """Return a box and whether it bridges explicit missing observations.

    A bounded interior gap can be interpolated only when accepted boxes exist
    on both sides. Leading, trailing, sparse, and long gaps remain uncertain.
    """
    if not times or timestamp < times[0] or timestamp > times[-1]:
        return None, False
    index = bisect_left(times, timestamp)
    if index < len(times) and times[index] == timestamp and samples[index][1] is not None:
        return samples[index][1], False
    if missing_policy == "hold" and (
            index == 0 or index == len(samples)
            or samples[index-1][1] is None or samples[index][1] is None):
        return None, False

    left_index = index-1 if index == len(times) or times[index] != timestamp else index-1
    while left_index >= 0 and samples[left_index][1] is None:
        left_index -= 1
    right_index = index
    while right_index < len(samples) and samples[right_index][1] is None:
        right_index += 1
    if left_index < 0 or right_index >= len(samples):
        return None, False

    left_time, left = samples[left_index]
    right_time, right = samples[right_index]
    gap = right_time-left_time
    has_explicit_miss = any(box is None for _, box in samples[left_index+1:right_index])
    if left is None or right is None or gap <= 0:
        return None, False
    if has_explicit_miss:
        if gap > _MAX_BRIDGED_OCCLUSION_SECONDS:
            return None, False
        inferred = True
    else:
        if gap > .5:
            return None, False
        inferred = False
    return _interpolate_box(left, right, (timestamp-left_time)/gap), inferred


def _box_at(samples, times, timestamp):
    return _resolve_box_at(samples, times, timestamp)[0]


def _crop_bounds(box, width, height):
    """An integer 9:16 crop containing the body and clipped 20% margins."""
    left = max(0., (box.x-.2*box.width)*width)
    right = min(float(width), (box.x+1.2*box.width)*width)
    top = max(0., (box.y-.2*box.height)*height)
    bottom = min(float(height), (box.y+1.2*box.height)*height)
    # Quantize outwards; centering must never trim a head or foot.
    unit = math.ceil(max((math.ceil(right)-math.floor(left))/9,
                         (math.ceil(bottom)-math.floor(top))/16))
    crop_width, crop_height = 9*unit, 16*unit
    if crop_width > width or crop_height > height:
        return None
    x = max(0, min(width-crop_width, math.floor((left+right-crop_width)/2)))
    y = max(0, min(height-crop_height, math.floor((top+bottom-crop_height)/2)))
    return x, y, x+crop_width, y+crop_height


def _composable_camera_box(box, last_box, width, height, *,
                           age_frames, max_hold_frames):
    """Use a recent valid camera box for a brief impossible-geometry glitch."""
    if box is not None and _crop_bounds(box, width, height) is not None:
        return box, False
    if (last_box is not None and age_frames <= max_hold_frames
            and _crop_bounds(last_box, width, height) is not None):
        return last_box, True
    return box, False


def _framing_bounds(box, width, height):
    if box is None:
        return None, 'missing_track'
    bounds = _crop_bounds(box, width, height)
    if bounds is not None:
        return bounds, 'portrait'
    unit = math.floor(min(width/9, height/16))
    crop_width, crop_height = 9*unit, 16*unit
    left, top = math.floor(box.x*width), math.floor(box.y*height)
    right = math.ceil((box.x+box.width)*width)
    bottom = math.ceil((box.y+box.height)*height)
    mode = 'reduced_margin'
    if right-left > crop_width or bottom-top > crop_height:
        # Preserve the visible body with local padding, never replace it by the stage.
        crop_width = min(width, max(crop_width, math.ceil((right-left)*1.1)))
        crop_height = min(height, max(crop_height, bottom-top))
        mode = 'local_letterbox'
    x = max(0, min(width-crop_width, math.floor((left+right-crop_width)/2)))
    y = max(0, min(height-crop_height, math.floor((top+bottom-crop_height)/2)))
    return (x, y, x+crop_width, y+crop_height), mode


def _stable_crops(camera_boxes, width, height, fps, *, held_frames=frozenset()):
    targets = [_framing_bounds(box, width, height) for box, _ in camera_boxes]
    sizes = [None if b is None else [b[2]-b[0], b[3]-b[1]] for b, _ in targets]
    zoom_extents = (min(width, height*9/16), height)
    # Anticipate growth only within continuous observations, not across absence.
    for i in range(len(sizes)-2, -1, -1):
        if (sizes[i] is not None and sizes[i+1] is not None
                and i not in held_frames and i+1 not in held_frames):
            for axis, extent in enumerate(zoom_extents):
                sizes[i][axis] = max(sizes[i][axis], sizes[i+1][axis]-.8*extent/fps)
    output = []
    previous = None
    velocity = [0., 0.]
    for i, ((target, mode), size) in enumerate(zip(targets, sizes)):
        if target is None:
            output.append((None, mode))
            previous, velocity = None, [0., 0.]
            continue
        if i in held_frames and previous is not None:
            output.append(output[-1])
            continue
        if i and i-1 in held_frames:
            velocity = [0., 0.]
        if previous is not None:
            for axis, extent in enumerate(zoom_extents):
                size[axis] = max(size[axis], previous[axis+2]-previous[axis]-.25*extent/fps)
        size[0] = min(width, max(size[0], size[1]*9/16))
        size[1] = min(height, max(size[1], size[0]*16/9))
        body = camera_boxes[i][0]
        body_edges = (body.x*width, body.y*height,
                      (body.x+body.width)*width, (body.y+body.height)*height)
        edges = []
        for axis, extent in enumerate((width, height)):
            span = min(extent, math.ceil(size[axis]))
            center = (target[axis]+target[axis+2])/2
            if previous is not None:
                old_center = (previous[axis]+previous[axis+2])/2
                error = center-old_center
                error = math.copysign(max(0., abs(error)-.08*span), error)
                wanted = max(-.5*extent, min(.5*extent, 4*error))
                velocity[axis] += max(-.8*extent/fps,
                                      min(.8*extent/fps, wanted-velocity[axis]))
                center = old_center+velocity[axis]/fps
            low = max(0, math.ceil(body_edges[axis+2])-span)
            high = min(extent-span, math.floor(body_edges[axis]))
            position = max(low, min(high, round(center-span/2)))
            # Body containment takes priority over speed limits during abrupt motion.
            if previous is not None and abs(position+span/2-center) > 1:
                velocity[axis] = 0.
            edges.append((position, position+span))
        previous = (edges[0][0], edges[1][0], edges[0][1], edges[1][1])
        if abs((previous[2]-previous[0])*16 - (previous[3]-previous[1])*9) > 16:
            mode = 'local_letterbox'
        output.append((previous, mode))
    return output


def _letterbox(frame, width, height):
    source_height, source_width = frame.shape[:2]
    scale = min(width/source_width, height/source_height)
    w = max(1, min(width, round(source_width*scale)))
    h = max(1, min(height, round(source_height*scale)))
    result = np.zeros((height, width, 3), dtype=np.uint8)
    x, y = (width-w)//2, (height-h)//2
    result[y:y+h, x:x+w] = cv2.resize(frame, (w, h), interpolation=cv2.INTER_AREA)
    return result


def _compose_frame(frame, box, width, height):
    bounds = None if box is None else _crop_bounds(box, frame.shape[1], frame.shape[0])
    if bounds is None:
        return _letterbox(frame, width, height), False
    x, y, right, bottom = bounds
    return cv2.resize(frame[y:bottom, x:right], (width, height),
                      interpolation=cv2.INTER_AREA), True


def _camera_boxes(samples, times, frame_count, fps, *, inferred_times=frozenset(),
                  missing_policy="bridge", hold_seconds=.5, expire_scale=False):
    """Offline framing: retain standing scale through brief crouches.

    Bridge mode retains legacy interpolation and half-second fallback. Hold
    mode smooths each observed run independently, then freezes its last camera
    box until hold_seconds after the last actual sample; no future run moves it.
    """
    resolved = [_resolve_box_at(samples, times, i/fps, missing_policy=missing_policy)
                for i in range(frame_count)]
    # Propagated geometry remains inference, including interpolated neighbors.
    for i, (box, inferred) in enumerate(resolved):
        t = i/fps
        right = bisect_left(times, t)
        indices = (right,) if right < len(times) and times[right] == t else (right-1, right)
        if any(0 <= j < len(times) and times[j] in inferred_times for j in indices):
            resolved[i] = (box, True)
    if missing_policy == "bridge":
        max_hold_frames = max(1, math.floor(fps*.5))
        last_box = None
        last_box_index = -max_hold_frames-1
        for i, (box, _) in enumerate(resolved):
            if box is not None:
                last_box, last_box_index = box, i
            elif last_box is not None and i-last_box_index <= max_hold_frames:
                resolved[i] = (last_box, True)
    output = []
    observation_times = [t for t, box in samples if box is not None]
    run_start, run_end = 0, frame_count
    radius = max(1, round(fps*.4))
    scale_radius = max(1, round(fps*1.5))
    scale_history = []
    last_reliable_scale = None
    for i, (box, inferred) in enumerate(resolved):
        if missing_policy == "hold":
            if box is None:
                last_observation = bisect_right(observation_times, i/fps)-1
                if (output and output[-1][0] is not None and last_observation >= 0
                        # Include the exact deadline if its sum rounded down.
                        and i/fps <= math.nextafter(
                            observation_times[last_observation]+hold_seconds, math.inf)):
                    output.append((output[-1][0], True))
                else:
                    output.append((None, False))
                continue
            if i == 0 or resolved[i-1][0] is None:
                if expire_scale:
                    scale_history = []
                run_start, run_end = i, i+1
                while run_end < frame_count and resolved[run_end][0] is not None:
                    run_end += 1
        if box is None:
            output.append((None, inferred))
            continue
        neighbors = [b for b, _ in resolved[max(run_start, i-radius):min(run_end, i+radius+1)]
                     if b is not None]
        if expire_scale:
            scale_history = [(j, b) for j, b in scale_history if j >= i-scale_radius]
        if not inferred:
            last_reliable_scale = box
            scale_history.append((i, box))
            scale_history = [(j, b) for j, b in scale_history
                             if j >= i-scale_radius]
        # Inferred/partial boxes may move the camera, but cannot teach it a
        # tighter crop. Retain the last reliable scale through the uncertainty.
        scale_boxes = [b for _, b in scale_history] or [last_reliable_scale or box]
        cx = sum(b.x+b.width/2 for b in neighbors)/len(neighbors)
        bottom = sum(b.y+b.height for b in neighbors)/len(neighbors)
        width = max(box.width, float(np.quantile([b.width for b in scale_boxes], .85)))
        height = max(box.height, float(np.quantile([b.height for b in scale_boxes], .85)))
        # Keep the smoothed center/bottom only while the current body remains
        # inside the stable-size box. Fast movement therefore moves the camera
        # instead of inflating its field of view and flashing to full stage.
        left = min(box.x, max(box.x+box.width-width, cx-width/2))
        top = min(box.y, max(box.y+box.height-height, bottom-height))
        left = min(1-width, max(0., left))
        top = min(1-height, max(0., top))
        output.append((NormalizedBox(left, top, width, height), inferred))
    return output


def _probe(source):
    result = subprocess.run([
        "ffprobe", "-v", "error", "-show_entries",
        "stream=codec_type,start_time,duration", "-of", "json", str(source),
    ], capture_output=True, text=True, timeout=30)
    if result.returncode:
        raise ValueError("source media could not be probed")
    streams = json.loads(result.stdout).get("streams", [])
    video = next((stream for stream in streams if stream["codec_type"] == "video"), None)
    if video is None:
        raise ValueError("source has no video stream")
    return video, any(stream["codec_type"] == "audio" for stream in streams)


def render_preview(source: Path, destination: Path,
                   samples: tuple[tuple[float, NormalizedBox | None], ...], *,
                   duration: float, member_code: str = "B", fps: int = 30,
                   width: int = 540, height: int = 960,
                   inferred_times=frozenset(), missing_policy="bridge",
                   hold_seconds=.5) -> dict:
    """Render [0, duration) at constant fps, rounding duration up to one frame.

    Adjacent known samples up to 0.5 seconds apart can be interpolated. Default
    bridge mode also interpolates bounded explicit gaps. Hold mode freezes the
    last framing across absence until hold_seconds after the last observation,
    then uses the full stage. Identity correctness is the caller's responsibility.
    ``destination.parent`` must exist. Destination must not exist, including a
    dangling symlink. Failures clean up only this call's private temporary file.
    """
    source, destination = Path(source), Path(destination)
    if os.path.lexists(destination):
        raise FileExistsError("preview destination already exists")
    if not destination.parent.is_dir():
        raise FileNotFoundError("preview destination parent must already exist")
    if isinstance(duration, bool) or not math.isfinite(duration) or duration <= 0:
        raise ValueError("duration must be finite and positive")
    if any(isinstance(v, bool) or not isinstance(v, int) or v <= 0
           for v in (fps, width, height)):
        raise ValueError("fps and dimensions must be positive integers")
    if width % 2 or height % 2 or width*16 != height*9:
        raise ValueError("dimensions must be even and 9:16")
    if not isinstance(member_code, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,16}", member_code):
        raise ValueError("member_code must be a short anonymous code")
    if not isinstance(missing_policy, str) or missing_policy not in ("bridge", "hold"):
        raise ValueError("missing_policy must be bridge or hold")
    if (isinstance(hold_seconds, bool) or not isinstance(hold_seconds, (int, float))
            or not math.isfinite(hold_seconds) or hold_seconds < 0):
        raise ValueError("hold_seconds must be finite and nonnegative")
    previous = -1.
    for timestamp, box in samples:
        if (isinstance(timestamp, bool) or not math.isfinite(timestamp)
                or timestamp < 0 or timestamp <= previous):
            raise ValueError("sample times must be finite, nonnegative and strictly increasing")
        if box is not None and not isinstance(box, NormalizedBox):
            raise ValueError("samples must contain NormalizedBox or None")
        previous = timestamp
    times = tuple(t for t, _ in samples)
    video, has_audio = _probe(source)
    video_start = float(video.get("start_time", 0.))
    source_duration = float(video.get("duration", "nan"))
    if math.isfinite(source_duration) and duration > source_duration+1e-6:
        raise ValueError("requested duration exceeds source video")
    frame_count = math.ceil(duration*fps-1e-9)
    camera_boxes = _camera_boxes(samples, times, frame_count, fps,
                                 inferred_times=inferred_times,
                                 missing_policy=missing_policy, hold_seconds=hold_seconds,
                                 expire_scale=missing_policy == 'hold')
    actual_duration = frame_count/fps
    capture = cv2.VideoCapture(str(source))
    temporary = None
    process = None
    observed_frames = 0
    bridged_frames = 0
    last_composable_box = None
    last_composable_index = -math.floor(fps*.5)-1
    max_camera_hold_frames = max(1, math.floor(fps*.5))
    framing_counts = dict(portrait=0, reduced_margin=0, local_letterbox=0,
                          missing_track=0, geometry_unfit=0)
    try:
        if not capture.isOpened():
            raise ValueError("source video is unreadable")
        source_fps = capture.get(cv2.CAP_PROP_FPS)
        if not math.isfinite(source_fps) or source_fps <= 0:
            raise ValueError("source video has invalid fps")
        stable_crops = None
        if missing_policy == 'hold':
            held_frames = {i for i in range(frame_count) if camera_boxes[i][0] is not None
                           and _resolve_box_at(samples, times, i/fps,
                                               missing_policy='hold')[0] is None}
            stable_crops = _stable_crops(camera_boxes, int(capture.get(cv2.CAP_PROP_FRAME_WIDTH)),
                int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT)), fps, held_frames=held_frames)
        fd, name = tempfile.mkstemp(prefix=".fancam-preview-", suffix=".mp4",
                                    dir=destination.parent)
        os.close(fd)
        temporary = Path(name)
        command = ["ffmpeg", "-v", "error", "-nostdin", "-y", "-copyts",
                   "-f", "rawvideo", "-pixel_format", "bgr24", "-video_size",
                   f"{width}x{height}", "-framerate", str(fps), "-i", "pipe:0"]
        if has_audio:
            # Raw video starts at zero. Shift original audio by video start,
            # retaining delay/lead, then trim negative samples and pad silence.
            command += ["-itsoffset", str(-video_start), "-i", str(source)]
        command += ["-map", "0:v:0"]
        if has_audio:
            command += ["-map", "1:a:0", "-af", "aresample=async=1:first_pts=0,apad",
                        "-c:a", "aac", "-b:a", "128k"]
        command += ["-map_metadata", "-1", "-map_chapters", "-1", "-c:v", "libx264",
                    "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p",
                    "-t", str(actual_duration), "-movflags", "+faststart",
                    "-f", "mp4", str(temporary)]
        # Discard diagnostics rather than persisting or exposing source paths;
        # DEVNULL also prevents a full stderr pipe from deadlocking encoding.
        process = subprocess.Popen(command, stdin=subprocess.PIPE,
                                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        assert process.stdin is not None
        frame = None
        source_index = -1
        for output_index in range(frame_count):
            timestamp = output_index/fps
            target_index = math.floor(timestamp*source_fps+1e-7)
            # Sequential decoding only: skip unused frames without random seeks.
            while source_index < target_index:
                if not capture.grab():
                    raise RuntimeError("source ended before requested preview duration")
                source_index += 1
                if source_index == target_index:
                    ok, frame = capture.retrieve()
                    if not ok or frame is None:
                        raise RuntimeError("source frame could not be decoded")
            box, bridged = camera_boxes[output_index]
            # Hold mode already owns the absence deadline and exact framing.
            # Geometry fallback must not restart or extend that hold.
            if missing_policy == "bridge":
                box, geometry_inferred = _composable_camera_box(
                    box, last_composable_box, frame.shape[1], frame.shape[0],
                    age_frames=output_index-last_composable_index,
                    max_hold_frames=max_camera_hold_frames)
                bridged = bridged or geometry_inferred
                if box is not None and not bridged:
                    last_composable_box = box
                    last_composable_index = output_index
            if stable_crops is not None:
                bounds, framing_mode = stable_crops[output_index]
                focused = bounds is not None
                if focused:
                    x, y, right, bottom = bounds
                    rendered = _letterbox(frame[y:bottom, x:right], width, height)
                else:
                    rendered = _letterbox(frame, width, height)
            else:
                rendered, focused = _compose_frame(frame, box, width, height)
                framing_mode = 'portrait' if focused else (
                    'missing_track' if box is None else 'geometry_unfit')
            framing_counts[framing_mode] += 1
            if focused and bridged:
                bridged_frames += 1
            elif focused:
                observed_frames += 1
            label = (f"{member_code} | OCCLUDED" if focused and bridged else
                     f"{member_code} | PREVIEW" if focused else
                     "FULL STAGE | UNCERTAIN")
            font = cv2.FONT_HERSHEY_SIMPLEX
            scale = min(.65, max(.1, width/650))
            text_width = cv2.getTextSize(label, font, scale, 1)[0][0]
            scale *= min(1., (width-12)/max(1, text_width))
            cv2.putText(rendered, label, (6, max(12, round(26*width/540))),
                        font, scale, (0, 0, 0), 3, cv2.LINE_AA)
            cv2.putText(rendered, label, (6, max(12, round(26*width/540))),
                        font, scale, (255, 255, 255), 1, cv2.LINE_AA)
            process.stdin.write(rendered.tobytes())
        process.stdin.close()
        if process.wait(timeout=60) != 0 or temporary.stat().st_size == 0:
            raise RuntimeError("preview encoder failed")
        # link(2) is an atomic no-replace publication on this same filesystem.
        # rename/replace would overwrite a destination created during rendering.
        with temporary.open("rb") as encoded:
            os.fsync(encoded.fileno())
        os.link(temporary, destination)
        focused_frames = observed_frames+bridged_frames
        return {"frame_count": frame_count, "focused_frames": focused_frames,
                "observed_frames": observed_frames, "bridged_frames": bridged_frames,
                "fallback_frames": frame_count-focused_frames,
                "duration": actual_duration, "fps": fps, "width": width,
                "height": height, "has_audio": has_audio, "preview_only": True,
                "framing_counts": framing_counts}
    except (BrokenPipeError, subprocess.TimeoutExpired) as error:
        raise RuntimeError("preview encoder failed") from error
    finally:
        capture.release()
        if process is not None:
            if process.poll() is None:
                process.kill()
            if process.stdin is not None and not process.stdin.closed:
                try:
                    process.stdin.close()
                except BrokenPipeError:
                    pass
            process.wait()
        if temporary is not None:
            temporary.unlink(missing_ok=True)
