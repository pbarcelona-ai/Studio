"""mix_film.py end to end with the real ffmpeg (the one bundled with imageio-ffmpeg) and tiny clips."""
import csv
import json
import re
import subprocess

import pytest

imageio_ffmpeg = pytest.importorskip("imageio_ffmpeg")
FFMPEG = imageio_ffmpeg.get_ffmpeg_exe()


def ff(*args):
    subprocess.run([FFMPEG, "-y", "-loglevel", "error", *args], check=True)


def seconds(path):
    err = subprocess.run([FFMPEG, "-i", str(path)], capture_output=True, text=True).stderr
    h, m, s = re.search(r"Duration:\s*(\d+):(\d+):(\d+\.\d+)", err).groups()
    return int(h) * 3600 + int(m) * 60 + float(s)


@pytest.fixture(scope="module")
def media(tmp_path_factory):
    d = tmp_path_factory.mktemp("media")
    ff("-f", "lavfi", "-i", "testsrc=s=64x48:r=12:d=1", "-pix_fmt", "yuv420p", str(d / "a.mp4"))
    ff("-f", "lavfi", "-i", "color=c=red:s=64x48:r=12:d=1", "-pix_fmt", "yuv420p", str(d / "b.mp4"))
    ff("-f", "lavfi", "-i", "color=c=blue:s=96x64:r=24:d=1", "-pix_fmt", "yuv420p", str(d / "big.mp4"))
    ff("-f", "lavfi", "-i", "sine=f=440:d=1.6", str(d / "narr.wav"))
    ff("-f", "lavfi", "-i", "sine=f=220:d=1", str(d / "sfx.wav"))
    ff("-f", "lavfi", "-i", "sine=f=330:d=5", str(d / "music.wav"))
    return d


@pytest.fixture()
def film(book, media):
    """books/demo with three 1-second clips, narration on shots 1 and 2, sfx on 1, music on 3, and chapter music."""
    v = book / "videos" / "ltx_video"
    v.mkdir(parents=True)
    for n, src in ((1, "a"), (2, "b"), (3, "a")):
        (v / f"shot-{n:04d}.mp4").write_bytes((media / f"{src}.mp4").read_bytes())
    for sub, name, n, src in (("kokoro", "narration", 1, "narr"), ("kokoro", "narration", 2, "narr"), ("mmaudio", "sfx", 1, "sfx"),
                              ("musicgen", "music", 3, "music"), ("musicgen_chapters", "music", 1, "music")):
        (book / "audio" / sub).mkdir(parents=True, exist_ok=True)
        (book / "audio" / sub / f"{name}-{n:04d}.wav").write_bytes((media / f"{src}.wav").read_bytes())
    with open(book / "audio_shots.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["chapter", "shot", "lines_json", "narration", "sfx", "music"])
        for i in (1, 2, 3):
            w.writerow(["1", i, json.dumps([["NARRATOR", f"Caption number {i}."]]), f"Caption number {i}.", "", ""])
    return book


def mix(run_script, *args):
    code, out = run_script("mix_film.py", "--project", "demo", "--model", "ltx_video", *args)
    assert code is None, out
    return out


class TestMix:
    def test_default_stretches_for_the_narration_and_writes_captions(self, film, run_script):
        out = mix(run_script)
        f = film / "films" / "ltx_video_mixed.mp4"
        assert "mixed 3 clips" in out and "stems used {'narration': 2, 'sfx': 1, 'music': 1}" in out and f.is_file()
        assert seconds(f) > 4.0                         # shots 1 and 2 are stretched to hold 1.6 s of narration + pad (2 s each) + 1 s
        srt = f.with_suffix(".srt").read_text()
        assert "Caption number 1." in srt and "Caption number 3." not in srt and "-->" in srt

    def test_trim_keeps_the_clip_length_and_range_selects(self, film, run_script):
        mix(run_script, "--sync", "trim", "--no-loudnorm", "--start", "1", "--end", "2", "--out", "t.mp4")
        assert 1.8 < seconds(film / "films" / "t.mp4") < 2.4

    def test_speed_and_gentle_modes(self, film, run_script):
        mix(run_script, "--sync", "speed", "--no-loudnorm", "--out", "s.mp4")
        mix(run_script, "--sync", "gentle", "--no-loudnorm", "--no-duck", "--out", "g.mp4")
        assert 2.8 < seconds(film / "films" / "s.mp4") < 3.4 and seconds(film / "films" / "g.mp4") > 3.2

    def test_fade_transition(self, film, run_script):
        mix(run_script, "--transition", "fade", "--fade", "0.2", "--no-loudnorm", "--out", "f.mp4")
        assert (film / "films" / "f.mp4").is_file()

    def test_dissolve_overlaps_the_clips(self, film, run_script):
        mix(run_script, "--transition", "dissolve", "--fade", "0.3", "--no-loudnorm", "--sync", "trim", "--out", "d.mp4")
        assert seconds(film / "films" / "d.mp4") < 2.95

    def test_music_bed_loops_the_chapter_cue(self, film, run_script):
        out = mix(run_script, "--music-bed", "--sync", "trim", "--out", "bed.mp4")
        assert "stems used {'narration': 2, 'sfx': 1, 'music': 1}" in out and (film / "films" / "bed.mp4").is_file()

    def test_music_bed_without_a_cue_says_so(self, film, run_script):
        (film / "audio" / "musicgen_chapters" / "music-0001.wav").unlink()
        assert "no usable music cue" in mix(run_script, "--music-bed", "--sync", "trim", "--out", "nobed.mp4")

    def test_match_colour(self, film, run_script):
        assert "colour:" in mix(run_script, "--match-colour", "--sync", "trim", "--no-loudnorm", "--out", "c.mp4")

    def test_selection_with_trims_and_title_cards(self, film, run_script):
        sel = {"clips": [{"row": 3, "video": "videos/ltx_video/shot-0003.mp4", "narration": None, "sfx": None, "music": None, "trim_start": 0.2, "trim_end": 0.2},
                         {"row": 1, "video": "videos/ltx_video/shot-0001.mp4", "narration": "audio/kokoro/narration-0001.wav"}],
               "title": "The Story", "end_title": "The End"}
        (film / "films").mkdir(exist_ok=True)
        (film / "films" / "_selection.json").write_text(json.dumps(sel))
        out = mix(run_script, "--selection", "films/_selection.json", "--no-loudnorm")
        assert "mixed" in out and (film / "films" / "selected_film.mp4").is_file()

    def test_selection_cannot_leave_the_project(self, film, run_script, tmp_path):
        (film / "films").mkdir(exist_ok=True)
        (film / "films" / "_selection.json").write_text(json.dumps({"clips": [{"row": 1, "video": "../../../../etc/hosts"}]}))
        code, out = run_script("mix_film.py", "--project", "demo", "--selection", "films/_selection.json")
        assert "not a file inside the project" in code

    def test_several_models_are_brought_to_one_size(self, film, media, run_script):
        other = film / "videos" / "wan"
        other.mkdir()
        (other / "shot-0002.mp4").write_bytes((media / "big.mp4").read_bytes())
        (film / "videos" / "ltx_video" / "shot-0002.mp4").unlink()
        out = run_script("mix_film.py", "--project", "demo", "--models", "ltx_video,wan", "--sync", "trim", "--no-loudnorm")[1]
        assert "brought to 96x64" in out and (film / "films" / "ltx_video_mixed.mp4").is_file()

    def test_burn_captions(self, film, run_script):
        out = mix(run_script, "--burn-captions", "--sync", "trim", "--no-loudnorm", "--out", "burn.mp4")
        assert "captions drawn into the picture" in out or "captions could not be drawn" in out


class TestMixErrors:
    def test_bad_options(self, film, run_script):
        assert "--music-bed is for films" in run_script("mix_film.py", "--music-bed", "--chapters")[0]
        assert "--fade must be" in run_script("mix_film.py", "--fade", "9")[0]

    def test_no_clips(self, book, run_script):
        code = run_script("mix_film.py", "--project", "demo", "--model", "ghost")[0]
        assert code and "no" in str(code).lower()


class TestHelpers:
    def test_atempo_chain(self):
        import sys
        src = open(sys.modules["bookkit"].__file__.replace("bookkit.py", "mix_film.py")).read()
        start = src.index("def atempo_chain")
        ns: dict = {}
        exec(src[start:src.index("def colour_of")], ns)
        assert ns["atempo_chain"](1.5) == "atempo=1.5000" and ns["atempo_chain"](5) == "atempo=2.0,atempo=2.0,atempo=1.2500"
