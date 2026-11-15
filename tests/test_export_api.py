"""The Export card's routes and the credits routes."""
import subprocess

import pytest

imageio_ffmpeg = pytest.importorskip("imageio_ffmpeg")
FFMPEG = imageio_ffmpeg.get_ffmpeg_exe()


@pytest.fixture()
def films(book):
    d = book / "films"
    d.mkdir()
    subprocess.run([FFMPEG, "-y", "-loglevel", "error", "-f", "lavfi", "-i", "testsrc=s=160x90:r=12:d=1", "-pix_fmt", "yuv420p", str(d / "cut.mp4")], check=True)
    (d / "cut.srt").write_text("1\n00:00:00,000 --> 00:00:00,900\nHi.\n\n")
    (d / "_selection.json").write_text("{}")
    return book


class TestRoutes:
    def test_list(self, server, films):
        out = server.api("GET", "/api/exports?project=demo")[1]
        assert [f["name"] for f in out["films"]] == ["cut.mp4"] and out["films"][0]["captions"] is True and "youtube_1080p" in [p["id"] for p in out["presets"]]
        assert server.api("GET", "/api/exports?project=ghost")[0] == 400

    def test_the_export_step(self, server, films):
        body = {"project": "demo", "film": "cut.mp4", "preset": "festival", "languages": "es, fr", "title": " My  Film ", "audio_tracks": [{"lang": "es", "file": "audio/dub.wav"}]}
        from studio_app.export import export_step
        step = export_step(body)
        assert step["label"] == "Export cut.mp4 as Festival screener with subtitles in es, fr"
        a = step["argv"]
        assert a[:6] == ["uv", "run", "--with", "imageio-ffmpeg", "python", "export_film.py"] and a[a.index("--languages") + 1] == "es,fr" and "--engine" in a
        assert a[a.index("--audio-track") + 1] == "es=audio/dub.wav" and a[a.index("--title") + 1] == "My Film"
        assert "--languages" not in export_step({"project": "demo", "film": "cut.mp4", "preset": "web_small"})["argv"]

    def test_bad_requests(self, server, films):
        from studio_app.common import PlanError
        from studio_app.export import export_step
        base = {"project": "demo", "film": "cut.mp4", "preset": "festival"}
        for patch in ({"preset": "dvd"}, {"film": "../x.mp4"}, {"film": "gone.mp4"}, {"languages": "en us!"}, {"languages": "a1,b2,c3,d4,e5,f6,g7,h8,i9"},
                      {"audio_tracks": [{"lang": "es", "file": "../x.wav"}]}, {"audio_tracks": [{"lang": "e!", "file": "a.wav"}]}):
            with pytest.raises(PlanError):
                export_step({**base, **patch})
        assert server.api("POST", "/api/export", {**base, "preset": "dvd"})[0] == 400

    def test_credits(self, server, films):
        out = server.api("GET", "/api/credits?project=demo")[1]
        assert out["credits"]["crew"] == [] and "PG" in out["ratings"] and "Characters" in out["preview"]
        out = server.api("POST", "/api/credits", {"project": "demo", "credits": {"based_on": "The Book", "rating": "PG", "crew": [{"role": "Colour", "name": "C. Grader"}]}})[1]
        assert out["credits"]["based_on"] == "The Book" and "C. Grader" in out["preview"] and out["preview"][:2] == ["Based on", "The Book"]
        assert server.api("POST", "/api/credits", {"project": "demo", "credits": {"rating": "XXX"}})[0] == 400
        assert server.api("POST", "/api/credits", {"project": "ghost", "credits": {}})[0] == 400

    def test_film_flags(self):
        from studio_app.generation import sound_flags
        assert sound_flags({"credits": True, "grade": True}, False) == ["--grade", "--credits"]
