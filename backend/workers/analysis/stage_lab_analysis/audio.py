from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import subprocess


@dataclass(frozen=True, slots=True)
class BeatAnalysis:
    tempo_bpm: float | None
    beats: tuple[float, ...]


def extract_beats(video: Path, workspace: Path) -> BeatAnalysis:
    wav = workspace / ".analysis-audio.wav"
    try:
        subprocess.run(
            ["ffmpeg", "-y", "-v", "error", "-i", str(video), "-vn", "-ac", "1", "-ar", "22050", str(wav)],
            check=True,
            capture_output=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return BeatAnalysis(None, ())
    try:
        import librosa
        signal, _ = librosa.load(str(wav), sr=22050, mono=True)
        _, beat_frames = librosa.beat.beat_track(y=signal, sr=22050)
        beats = tuple(float(value) for value in librosa.frames_to_time(beat_frames, sr=22050))
        tempo = librosa.feature.tempo(y=signal, sr=22050)
        return BeatAnalysis(float(tempo[0]) if len(tempo) else None, beats)
    except Exception:
        return BeatAnalysis(None, ())
    finally:
        wav.unlink(missing_ok=True)
