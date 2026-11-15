"""export_film.py with the real ffmpeg: presets, subtitle tracks (translated with a stand-in AI), extra audio tracks, errors."""
import re
import subprocess

import pytest

import export_film as ex

imageio_ffmpeg = pytest.importorskip("imageio_ffmpeg")
FFMPEG = imageio_ffmpeg.get_ffmpeg_exe()

SRT = "1\n00:00:00,000 --> 00:00:00,900\nHello there.\n\n2\n00:00:01,000 --> 00:00:01,900\nGoodbye.\n\n"


def ff(*args):
    subprocess.run([FFMPEG, "-y", "-loglevel", "error", *args], check=True)


def report(path):
    return subprocess.run([FFMPEG, "-i", str(path)], capture_output=True, text=True).stderr


@pytest.fixture()
def film(book):
    films = book / "films"
    films.mkdir()
    ff("-f", "lavfi", "-i", "testsrc=s=320x180:r=12:d=2", "-f", "lavfi", "-i", "sine=f=440:d=2", "-shortest", "-pix_fmt", "yuv420p", str(films / "cut.mp4"))
    (films / "cut.srt").write_text(SRT)
    return book


def stand_in_llm(calls=None, short=False):
    def llm(prompt, check):
        n = int(re.search(r"exactly (\d+) strings", prompt).group(1))
        if calls is not None:
            calls.append(prompt)
        data = {"lines": [f"[es] line {i}" for i in range(1, n + 1 - (1 if short else 0))]}
        check(data)
        return data
    return llm


class TestPresets:
    def test_language_codes(self):
        assert [ex.lang3(x) for x in ("en", "pt-BR", "es", "xx", "fil", "ZH")] == ["eng", "por", "spa", "und", "fil", "zho"]

    @pytest.mark.parametrize("preset,size,codec", [("youtube_1080p", "1920x1080", "h264"), ("festival", "1920x1080", "h264"), ("vertical_short", "1080x1920", "h264"),
                                                   ("web_small", "1280x720", "h264"), ("master_1080p", "1920x1080", "prores")])
    def test_each_preset_makes_the_right_file(self, film, preset, size, codec):
        res = ex.export(film, "cut.mp4", preset, [])
        rep = report(res["file"])
        assert size in rep and codec in rep and res["file"].endswith("." + ex.PRESETS[preset][7]) and 1.5 < res["seconds"] < 2.6

    def test_festival_is_24_fps_and_youtube_keeps_the_rate(self, film):
        assert "24 fps" in report(ex.export(film, "cut.mp4", "festival", [])["file"]) and "12 fps" in report(ex.export(film, "cut.mp4", "youtube_1080p", [])["file"])

    def test_a_4k_master_is_made(self, film):
        assert "3840x2160" in report(ex.export(film, "cut.mp4", "master_4k", [])["file"])

    def test_a_film_without_sound_still_exports(self, film):
        ff("-f", "lavfi", "-i", "color=c=red:s=64x48:r=12:d=1", "-pix_fmt", "yuv420p", str(film / "films" / "mute.mp4"))
        rep = report(ex.export(film, "mute.mp4", "youtube_1080p", [])["file"])
        assert "Video:" in rep and "Audio:" not in rep

    def test_the_vertical_crop_is_centred(self, film):
        assert ex.video_filter("vertical_short", {}).startswith("crop=") and "pad=" not in ex.video_filter("vertical_short", {})


class TestSubtitles:
    def test_the_films_captions_become_a_track_and_a_sidecar(self, film):
        res = ex.export(film, "cut.mp4", "youtube_1080p", [], title="My Film")
        rep = report(res["file"])
        assert res["subtitles"] == ["en"] and "Subtitle: mov_text" in rep and "(eng)" in rep and "title           : My Film" in rep
        assert (film / "films" / "cut_youtube_1080p.en.srt").read_text() == SRT

    def test_translated_tracks(self, film):
        calls = []
        res = ex.export(film, "cut.mp4", "youtube_1080p", ["es", "pt-BR"], stand_in_llm(calls))
        rep = report(res["file"])
        assert res["subtitles"] == ["en", "es", "pt-BR"] and rep.count("Subtitle:") == 3 and "(spa)" in rep and "(por)" in rep and "(eng)" in rep
        assert len(calls) == 2 and "Hello there." in calls[0]
        es = ex.parse_srt((film / "films" / "cut_youtube_1080p.es.srt").read_text())
        assert [c[1] for c in es] == ["00:00:00,000 --> 00:00:00,900", "00:00:01,000 --> 00:00:01,900"] and es[0][2] == "[es] line 1"

    def test_a_translation_that_loses_a_line_is_refused(self, film):
        with pytest.raises(ValueError, match="exactly 2"):
            ex.export(film, "cut.mp4", "youtube_1080p", ["es"], stand_in_llm(short=True))

    def test_batches(self):
        cues = [(str(i), "00:00:00,000 --> 00:00:01,000", f"t{i}") for i in range(1, 95)]
        calls = []
        out = ex.translate_cues(cues, "Spanish", lambda prompt, check: (calls.append(1), (lambda d: (check(d), d)[1])({"lines": [f"x{i}" for i in range(int(re.search(r"exactly (\d+)", prompt).group(1)))]}))[1])
        assert len(calls) == 3 and len(out) == 94 and out[40][2] == "x0"


class TestAudioTracks:
    def test_a_dubbed_track_is_added_with_its_language(self, film):
        (film / "audio").mkdir()
        ff("-f", "lavfi", "-i", "sine=f=330:d=2", str(film / "audio" / "dub_es.wav"))
        rep = report(ex.export(film, "cut.mp4", "youtube_1080p", [], audio_tracks=[("es", "audio/dub_es.wav")])["file"])
        assert rep.count("Audio:") == 2 and "(spa)" in rep


class TestErrors:
    def test_refusals(self, film, tmp_path):
        for args, msg in ((("cut.mp4", "dvd", []), "preset must be"), (("../x.mp4", "festival", []), "not a film"), (("missing.mp4", "festival", []), "not a film"),
                          (("cut.mp4", "festival", ["en us"]), "language code"), (("cut.mp4", "festival", ["es"]), "needs the AI engine")):
            with pytest.raises(ex.ExportError, match=msg):
                ex.export(film, *args)
        with pytest.raises(ex.ExportError, match="no captions"):
            (film / "films" / "cut.srt").unlink()
            ex.export(film, "cut.mp4", "festival", ["es"], stand_in_llm())
        with pytest.raises(ex.ExportError, match="letters, digits"):
            ex.export(film, "cut.mp4", "festival", [], out="bad name!")
        with pytest.raises(ex.ExportError, match="inside the book"):
            ex.export(film, "cut.mp4", "festival", [], audio_tracks=[("es", "../../etc/passwd")])
        (film / "films" / "broken.mp4").write_bytes(b"not a video")
        with pytest.raises(ex.ExportError, match="cannot read the picture size"):
            ex.export(film, "broken.mp4", "festival", [])

    def test_cli(self, film, run_script):
        code, out = run_script("export_film.py", "--project", "demo", "--film", "cut.mp4", "--preset", "web_small")
        assert code is None and "Small web copy" in out and (film / "films" / "cut_web_small.mp4").is_file()
        assert "not a film" in str(run_script("export_film.py", "--project", "demo", "--film", "nope.mp4", "--preset", "web_small")[0])


def test_a_translation_with_a_blank_line_or_an_arrow_cannot_break_the_srt():
    cues = [("1", "00:00:00,000 --> 00:00:01,000", "Hello")]
    out = ex.translate_cues(cues, "Spanish", lambda prompt, check: {"lines": ["Hola\n\n2\n00:00:01,000 --> 00:00:02,000\nextra"]})
    parsed = ex.parse_srt(ex.render_srt(out))
    assert len(parsed) == 1 and "-->" not in parsed[0][2]
