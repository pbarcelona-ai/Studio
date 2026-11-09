"""Golden tests for the hand-written mp4 / wav duration readers (checked against files made by real encoders)."""
import struct
import subprocess
import wave

import pytest

from studio_app import media


def make_wav(path, seconds, rate=16000, extra_chunk=False):
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(b"\x00\x00" * int(rate * seconds))
    if extra_chunk:                                     # a LIST chunk between fmt and data, as many tools write
        raw = path.read_bytes()
        i = raw.index(b"data")
        extra = b"LIST" + struct.pack("<I", 4) + b"INFO"
        path.write_bytes(raw[:i] + extra + raw[i:])


@pytest.mark.parametrize("seconds,rate", [(0.5, 16000), (2.0, 24000), (1.25, 44100)])
def test_wav_durations(tmp_path, seconds, rate):
    p = tmp_path / "a.wav"
    make_wav(p, seconds, rate)
    assert media.media_seconds(p) == pytest.approx(seconds, abs=0.01)


def test_wav_with_extra_chunk(tmp_path):
    p = tmp_path / "b.wav"
    make_wav(p, 1.0, extra_chunk=True)
    assert media.media_seconds(p) == pytest.approx(1.0, abs=0.01)


def test_broken_files_give_none_not_errors(tmp_path):
    for name, data in (("trunc.wav", b"RIFF\x00\x00\x00\x00WAVEfmt "), ("junk.wav", b"hello"), ("junk.mp4", b"\x00" * 40), ("empty.mp4", b"")):
        p = tmp_path / name
        p.write_bytes(data)
        assert media.media_seconds(p) is None, name
    assert media.media_seconds(tmp_path / "missing.wav") is None


def ffmpeg_exe():
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        pytest.skip("imageio-ffmpeg is not installed")


@pytest.mark.parametrize("seconds", [1.0, 2.5])
def test_mp4_duration_matches_the_encoder(tmp_path, seconds):
    exe = ffmpeg_exe()
    p = tmp_path / "v.mp4"
    subprocess.run([exe, "-y", "-loglevel", "error", "-f", "lavfi", "-i", f"testsrc=size=64x64:rate=10:duration={seconds}",
                    "-pix_fmt", "yuv420p", str(p)], check=True)
    assert media.media_seconds(p) == pytest.approx(seconds, abs=0.15)


def test_cache_follows_the_file(tmp_path):
    p = tmp_path / "c.wav"
    make_wav(p, 1.0)
    assert media.media_seconds(p) == pytest.approx(1.0, abs=0.01)
    make_wav(p, 2.0)
    assert media.media_seconds(p) == pytest.approx(2.0, abs=0.01)
