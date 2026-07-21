import subprocess

from stage_lab_analysis.audio import extract_beats


def test_missing_audio_returns_non_blocking_empty_analysis(tmp_path, monkeypatch):
    def fail(*args, **kwargs):
        raise subprocess.CalledProcessError(1, args[0])

    monkeypatch.setattr("stage_lab_analysis.audio.subprocess.run", fail)

    result = extract_beats(tmp_path / "proxy.mp4", tmp_path)

    assert result.beats == ()
    assert result.tempo_bpm is None
