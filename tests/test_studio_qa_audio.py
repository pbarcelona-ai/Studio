"""Tests for two-pass loudnorm mastering, J-cut/L-cut EDL bridges, render QA, and TTS/STT audit."""
from __future__ import annotations

import json
import math
import struct
import subprocess
import wave
from pathlib import Path

import pytest

import edl
import export_film as ex
import render_qa as rqa
import tts_audit as ta

imageio_ffmpeg = pytest.importorskip("imageio_ffmpeg")
FFMPEG = imageio_ffmpeg.get_ffmpeg_exe()


def _ff(*args: str) -> None:
    subprocess.run([FFMPEG, "-y", "-loglevel", "error", *args], check=True)


def _write_wav(path: Path, seconds: float = 1.0, amp: float = 0.4, freq: float = 440.0,
               sr: int = 16000, lead_s: float = 0.0, trail_s: float = 0.0) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    n_lead = int(sr * lead_s)
    n_tone = int(sr * seconds)
    n_trail = int(sr * trail_s)
    samples = [0] * n_lead
    for i in range(n_tone):
        v = int(max(-32767, min(32767, round(amp * 32767 * math.sin(2 * math.pi * freq * i / sr)))))
        samples.append(v)
    samples.extend([0] * n_trail)
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes(struct.pack(f"<{len(samples)}h", *samples))
    return path


class TestTwoPassLoudnorm:
    def test_parse_valid_and_invalid_stats(self):
        sample_err = (
            "[Parsed_loudnorm_0 @ 0x0]\n"
            '{\n'
            '  "input_i": "-18.42",\n'
            '  "input_tp": "-3.10",\n'
            '  "input_lra": "6.50",\n'
            '  "input_thresh": "-28.80",\n'
            '  "target_offset": "0.15"\n'
            '}\n'
        )
        stats = ex.parse_loudnorm_stats(sample_err)
        assert stats is not None
        assert stats["input_i"] == "-18.42" and stats["target_offset"] == "0.15"
        flt = ex.loudnorm_filter(-14, stats)
        assert "linear=true" in flt and "measured_I=-18.42" in flt and "offset=0.15" in flt

        # Silent track reports -inf -> rejected so caller falls back to single-pass
        silent_err = '{"input_i": "-inf", "input_tp": "-inf", "input_lra": "0.0", "input_thresh": "-inf", "target_offset": "inf"}'
        assert ex.parse_loudnorm_stats(silent_err) is None
        assert ex.parse_loudnorm_stats("no json here") is None
        assert ex.parse_loudnorm_stats('{"input_i": "bad"}') is None
        assert ex.loudnorm_filter(-14, None) == "loudnorm=I=-14:TP=-1.5:LRA=11.0"

    def test_measure_loudness_real_ffmpeg(self, tmp_path):
        clip = tmp_path / "tone.mp4"
        _ff("-f", "lavfi", "-i", "testsrc=s=160x90:r=12:d=2", "-f", "lavfi", "-i", "sine=f=440:d=2",
            "-shortest", "-pix_fmt", "yuv420p", str(clip))
        stats = ex.measure_loudness(FFMPEG, clip, -14)
        assert stats is not None and float(stats["input_i"]) < 0
        cmd = ex.build_command(FFMPEG, clip, tmp_path / "out.mp4", "youtube_1080p",
                               {"width": 160, "height": 90, "fps": 12.0, "seconds": 2.0, "has_audio": True},
                               [], [], loudnorm_stats=stats)
        af = cmd[cmd.index("-af") + 1]
        assert "linear=true" in af and "measured_I=" in af

        # Silent audio gracefully returns None
        silent = tmp_path / "silent.mp4"
        _ff("-f", "lavfi", "-i", "testsrc=s=160x90:r=12:d=1", "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo",
            "-t", "1", "-pix_fmt", "yuv420p", str(silent))
        assert ex.measure_loudness(FFMPEG, silent, -14) is None


class TestEDLJLcuts:
    def _sample_cut(self) -> dict:
        return {
            "name": "main",
            "tracks": {
                "video": [
                    {"id": "v0001", "scene": "S001", "shot": 1, "row": 1, "seconds": 4.0, "trim_in": 0.0,
                     "transition": {"kind": "cut", "seconds": 0.0}, "volume": 1.0},
                    {"id": "v0002", "scene": "S001", "shot": 2, "row": 2, "seconds": 4.0, "trim_in": 0.0,
                     "transition": {"kind": "cut", "seconds": 0.0}, "volume": 1.0},
                    {"id": "v0003", "scene": "S002", "shot": 1, "row": 3, "seconds": 4.0, "trim_in": 0.0,
                     "transition": {"kind": "cut", "seconds": 0.0}, "volume": 1.0},
                ],
                "voice": [
                    {"id": "a0001", "attach": "v0001", "offset": 0.2, "seconds": 2.0, "volume": 1.0, "ref": 1},
                    {"id": "a0002", "attach": "v0002", "offset": 0.2, "seconds": 2.0, "volume": 1.0, "ref": 2},
                    {"id": "a0003", "attach": "v0003", "offset": 0.2, "seconds": 2.0, "volume": 1.0, "ref": 3},
                ],
                "music": [],
                "effects": [],
            },
            "volumes": {"video": 1.0, "voice": 1.0, "music": 0.35, "effects": 0.6},
            "duck_db": 12.0,
        }

    def test_j_cut_and_l_cut_timeline(self):
        c = self._sample_cut()
        edl.set_transition(c, "v0001", "j-cut", 0.8)
        edl.set_transition(c, "v0002", "l-cut", 1.0)
        tl = edl.timeline(c)
        # Video still hard-cuts without shortening total runtime
        assert tl["total"] == pytest.approx(12.0)
        assert tl["video"][1]["start"] == pytest.approx(4.0)
        # v0002 voice leads early by 0.8s into v0001 (4.0 + 0.2 - 0.8 = 3.4)
        v2_voice = next(a for a in tl["voice"] if a["id"] == "a0002")
        assert v2_voice["start"] == pytest.approx(3.4)
        # v0002 also has an l-cut of 1.0s into v0003, extending its end by 1.0s
        assert v2_voice["end"] == pytest.approx(3.4 + 2.0 + 1.0)

    def test_transition_validation(self):
        c = self._sample_cut()
        with pytest.raises(edl.EditError):
            edl.set_transition(c, "v0001", "wipe", 0.5)
        with pytest.raises(edl.EditError):
            edl.set_transition(c, "v0001", "j-cut", -1.0)
        with pytest.raises(edl.EditError):
            edl.set_transition(c, "v0001", "l-cut", 99.0)


class TestRenderQA:
    def test_good_video_and_contact_sheet(self, tmp_path):
        vid = tmp_path / "good.mp4"
        _ff("-f", "lavfi", "-i", "testsrc2=s=320x180:r=12:d=2", "-f", "lavfi", "-i", "sine=f=440:d=2",
            "-shortest", "-pix_fmt", "yuv420p", str(vid))
        sheet = tmp_path / "sheet.jpg"
        rep = rqa.inspect_video(vid, contact_sheet=sheet, samples=4, ffmpeg_bin=FFMPEG)
        assert rep["ok"] is True
        assert rep["errors"] == []
        assert rep["metrics"]["width"] == 320 and rep["metrics"]["height"] == 180
        assert rep["metrics"]["has_audio"] is True and rep["metrics"]["av_drift"] < 0.5
        assert len(rep["frames"]) == 4
        assert sheet.is_file() and sheet.stat().st_size > 1000

    def test_blank_and_frozen_video_flagged(self, tmp_path):
        black = tmp_path / "black.mp4"
        _ff("-f", "lavfi", "-i", "color=c=black:s=160x90:r=12:d=2", "-pix_fmt", "yuv420p", str(black))
        rep = rqa.inspect_video(black, samples=4, ffmpeg_bin=FFMPEG)
        assert rep["ok"] is False
        assert any("solid/blank" in e for e in rep["errors"])
        assert any("frozen" in w for w in rep["warnings"])

    def test_av_drift_warning(self, tmp_path):
        drift = tmp_path / "drift.mp4"
        _ff("-f", "lavfi", "-i", "testsrc2=s=160x90:r=12:d=2", "-f", "lavfi", "-i", "sine=f=440:d=4",
            "-pix_fmt", "yuv420p", str(drift))
        rep = rqa.inspect_video(drift, samples=3, max_av_drift=0.5, ffmpeg_bin=FFMPEG)
        assert rep["ok"] is True
        assert any("drift" in w for w in rep["warnings"])

    def test_cli_and_missing_file(self, tmp_path):
        assert rqa.main([str(tmp_path / "missing.mp4")]) == 2
        vid = tmp_path / "ok.mp4"
        _ff("-f", "lavfi", "-i", "testsrc2=s=160x90:r=12:d=1.5", "-pix_fmt", "yuv420p", str(vid))
        assert rqa.main([str(vid), "--samples", "3", "--contact-sheet", str(tmp_path / "c.jpg")]) == 0
        assert (tmp_path / "c.jpg").is_file()


class TestTTSAudit:
    def test_wer_and_wav_stats(self, tmp_path):
        assert ta.word_error_rate("Hello, world!", "hello world") == 0.0
        assert ta.word_error_rate("one two three four", "one two X four") == pytest.approx(0.25)
        assert ta.word_error_rate("", "") == 0.0

        good = _write_wav(tmp_path / "good.wav", seconds=1.0, amp=0.4, lead_s=0.1, trail_s=0.2)
        st = ta.wav_stats(good)
        assert st["duration"] == pytest.approx(1.3, abs=0.05)
        assert not st["silent"] and not st["clipped"]
        assert st["leading_silence"] >= 0.08 and st["trailing_silence"] >= 0.16

        silent = _write_wav(tmp_path / "silent.wav", seconds=0.5, amp=0.0)
        assert ta.wav_stats(silent)["silent"] is True

        clipped = _write_wav(tmp_path / "clipped.wav", seconds=0.5, amp=1.0)
        assert ta.wav_stats(clipped)["clipped"] is True

    def test_audit_book_sync_and_word_srt(self, tmp_path):
        pdir = tmp_path / "book"
        pdir.mkdir()
        (pdir / "audio_shots.csv").write_text(
            "shot,narration\n1,\"Who is there at the door?\"\n2,\"Nobody answered.\"\n",
            encoding="utf-8",
        )
        _write_wav(pdir / "audio" / "kokoro" / "narration-0001.wav", seconds=1.8, amp=0.4)
        _write_wav(pdir / "audio" / "kokoro" / "narration-0002.wav", seconds=1.1, amp=0.4)

        def fake_stt(path: Path) -> dict:
            if path.name.endswith("0001.wav"):
                return {
                    "text": "Who is there at the door",
                    "words": [
                        {"word": "Who", "start": 0.0, "end": 0.2, "prob": 0.99},
                        {"word": "is", "start": 0.2, "end": 0.4, "prob": 0.98},
                        {"word": "there", "start": 0.4, "end": 0.7, "prob": 0.99},
                        {"word": "at", "start": 0.7, "end": 0.9, "prob": 0.97},
                        {"word": "the", "start": 0.9, "end": 1.1, "prob": 0.98},
                        {"word": "door?", "start": 1.1, "end": 1.6, "prob": 0.99},
                    ],
                }
            return {"text": "totally wrong garbled speech here", "words": []}

        rep = ta.audit_book(pdir, transcriber=fake_stt, max_wer=0.35)
        assert rep["checked"] == 2 and rep["passed"] == 1 and rep["flagged"] == 1 and rep["ok"] is False
        assert rep["clips"][0]["ok"] is True and rep["clips"][0]["wer"] == 0.0
        assert rep["clips"][1]["ok"] is False and any("mismatch" in x for x in rep["clips"][1]["issues"])
        assert json.loads((pdir / "audio" / "tts_audit.json").read_text(encoding="utf-8"))["checked"] == 2

        cut = {
            "name": "main",
            "tracks": {
                "video": [
                    {"id": "v0001", "scene": "S001", "shot": 1, "row": 1, "seconds": 3.0, "trim_in": 0.0,
                     "transition": {"kind": "cut", "seconds": 0.0}, "volume": 1.0},
                    {"id": "v0002", "scene": "S001", "shot": 2, "row": 2, "seconds": 3.0, "trim_in": 0.0,
                     "transition": {"kind": "cut", "seconds": 0.0}, "volume": 1.0},
                ],
                "voice": [
                    {"id": "a0001", "attach": "v0001", "offset": 0.2, "seconds": 1.0, "volume": 1.0, "ref": 1},
                    {"id": "a0002", "attach": "v0002", "offset": 0.2, "seconds": 2.0, "volume": 1.0, "ref": 2},
                ],
                "music": [],
                "effects": [],
            },
            "volumes": {"video": 1.0, "voice": 1.0, "music": 0.35, "effects": 0.6},
            "duck_db": 12.0,
        }
        changed = ta.sync_voice_durations(cut, rep)
        assert changed == 2
        assert cut["tracks"]["voice"][0]["seconds"] == pytest.approx(1.8, abs=0.05)
        srt_out = ta.word_srt(cut, rep, max_words_per_cue=3)
        assert "Who is there" in srt_out and "at the door?" in srt_out and "Nobody answered." in srt_out

    def test_tts_audit_edge_cases_and_cli(self, fake_root, monkeypatch):
        pdir = fake_root / "projects" / "books" / "demo"
        pdir.mkdir(parents=True, exist_ok=True)
        # Missing, silent, and clipped wav checks
        missing = ta.audit_clip(pdir / "nope.wav", "hello")
        assert not missing["ok"] and not missing["exists"]
        sil = _write_wav(pdir / "sil.wav", seconds=0.4, amp=0.0)
        assert "silent" in " ".join(ta.audit_clip(sil, "hi")["issues"])
        clip = _write_wav(pdir / "clip.wav", seconds=0.4, amp=1.0)
        assert "clipping" in " ".join(ta.audit_clip(clip, "hi")["issues"])
        empty = _write_wav(pdir / "empty.wav", seconds=0.0, amp=0.0)
        assert ta.wav_stats(empty)["silent"] is True
        assert "empty" in " ".join(ta.audit_clip(empty, "hi")["issues"])

        # lines_json CSV format + CLI (--no-stt)
        (pdir / "audio_shots.csv").write_text(
            'shot,narration,lines_json\n1,,"[{""text"": ""Hello world""}]"\n',
            encoding="utf-8",
        )
        _write_wav(pdir / "audio" / "kokoro" / "narration-0001.wav", seconds=0.8, amp=0.4)
        assert ta.main(["demo", "--no-stt"]) == 0

        # sound_design + shot_list fallback when audio_shots.csv is absent
        (pdir / "audio_shots.csv").unlink()
        (pdir / "shots").mkdir(exist_ok=True)
        (pdir / "shots" / "shotlist.json").write_text(
            json.dumps({"scenes": [{"id": "S001", "shots": [{"n": 1, "seconds": 2.0}]}]}),
            encoding="utf-8",
        )
        (pdir / "sound").mkdir(exist_ok=True)
        (pdir / "sound" / "plan.json").write_text(
            json.dumps({"lines": [{"scene": "S001", "shot": 1, "text": "Fallback line"}]}),
            encoding="utf-8",
        )
        rep2 = ta.audit_book(pdir, transcriber=None, write_report=False)
        assert rep2["checked"] == 1 and rep2["ok"] is True

        # Optional faster-whisper returns None cleanly when unavailable
        monkeypatch.setitem(__import__("sys").modules, "faster_whisper", None)
        assert ta.whisper_word_transcriber() is None

