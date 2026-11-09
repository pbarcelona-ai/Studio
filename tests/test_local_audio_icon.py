"""local_audio.py (CPU narration/music: the model runs are stubbed) and make_icon.py (the favicon writer; the icon itself needs a macOS font)."""
import re
import subprocess
import sys
from pathlib import Path

import pytest

import local_audio as la


class TestLocalAudio:
    def test_spans(self):
        assert la.spans([1, 2, 3, 7, 9, 10]) == [(1, 3), (7, 7), (9, 10)] and la.spans([]) == []

    def test_the_kokoro_worker_is_read_from_make_audio_not_imported(self):
        src = la.kokoro_worker()
        compile(src, "kokoro_worker.py", "exec")
        assert "kokoro" in src.lower()

    def test_narration_makes_only_the_missing_lines_in_runs(self, book, monkeypatch, capsys):
        (book / "audio_shots.csv").write_text("chapter,shot,narration\n" + "".join(f"1,{i},t\n" for i in range(1, 6)))
        out = book / "audio" / "kokoro"
        out.mkdir(parents=True)
        for n in (2, 5):
            (out / f"narration-{n:04d}.wav").write_bytes(b"x")
        calls = []
        monkeypatch.setattr(subprocess, "run", lambda argv, check=False, **k: calls.append(argv[2:]))
        la.narration(book)
        assert [(c[1], c[2]) for c in calls] == [("1", "1"), ("3", "4")] and all(c[0].endswith("audio_shots.csv") for c in calls)
        for n in (1, 3, 4):
            (out / f"narration-{n:04d}.wav").write_bytes(b"x")
        calls.clear()
        la.narration(book)
        assert calls == [] and "all 5 line(s) are here" in capsys.readouterr().out

    def test_music_with_every_cue_present(self, book, capsys):
        (book / "audio_chapters.csv").write_text("chapter,music\n1,calm\n")
        out = book / "audio" / "musicgen_chapters"
        out.mkdir(parents=True)
        (out / "music-0001.wav").write_bytes(b"x")
        la.music(book)
        assert "all 1 cue(s) are here" in capsys.readouterr().out

    def test_main_checks_its_arguments(self, book, monkeypatch):
        for argv, msg in ((["local_audio.py"], "kokoro"), (["local_audio.py", "demo", "bark"], "kokoro"), (["local_audio.py", "ghost", "kokoro"], "no such book"),
                          (["local_audio.py", "Bad Name", "kokoro"], "bad project name")):
            monkeypatch.setattr(sys, "argv", argv)
            with pytest.raises(SystemExit, match=msg):
                la.main()
        monkeypatch.setattr(sys, "argv", ["local_audio.py", "demo", "musicgen"])
        (book / "audio_chapters.csv").write_text("chapter,music\n1,calm\n")
        (book / "audio" / "musicgen_chapters").mkdir(parents=True)
        (book / "audio" / "musicgen_chapters" / "music-0001.wav").write_bytes(b"x")
        la.main()


PIL = pytest.importorskip("PIL")
import make_icon as mi  # noqa: E402


@pytest.fixture()
def icon_png(tmp_path):
    from PIL import Image
    p = tmp_path / "icon.png"
    Image.new("RGBA", (mi.SIZE, mi.SIZE), (200, 30, 30, 255)).save(p)
    return p


class TestIcon:
    def test_favicon_block_embeds_three_pictures(self, icon_png):
        block = mi.favicon_block(icon_png)
        assert block.startswith("<!-- favicon:start") and block.endswith("<!-- favicon:end -->") and block.count("data:image/png;base64,") == 3 and 'sizes="180x180"' in block

    def test_write_favicon_adds_then_replaces_the_block(self, icon_png, tmp_path):
        page = tmp_path / "index.html"
        page.write_text("<html><head><title>x</title></head><body></body></html>")
        mi.write_favicon(page, icon_png)
        first = page.read_text()
        assert first.count("favicon:start") == 1 and first.index("favicon:end") < first.index("</head>")
        mi.write_favicon(page, icon_png)
        assert page.read_text().count("favicon:start") == 1 and "<title>x</title>" in page.read_text()

    def test_data_uri_is_a_real_png(self):
        from PIL import Image
        import base64
        import io
        uri = mi.data_uri(Image.new("RGB", (40, 40), "red"), 16)
        assert Image.open(io.BytesIO(base64.b64decode(uri.split(",", 1)[1]))).size == (16, 16)

    @pytest.mark.skipif(not Path(mi.FONT).is_file(), reason="needs the macOS Arial Black font")
    def test_make_draws_the_icon_and_calls_iconutil(self, tmp_path, monkeypatch):
        calls = []
        monkeypatch.setattr(mi.subprocess, "run", lambda argv, check=False, **k: calls.append(argv))
        png, icns = mi.make(tmp_path / "out")
        assert png.is_file() and calls[0][:3] == ["iconutil", "-c", "icns"] and len(list((tmp_path / "out" / "icon.iconset").glob("*.png"))) == 10
        from PIL import Image
        assert Image.open(png).size == (mi.SIZE, mi.SIZE)

    @pytest.mark.skipif(not Path(mi.FONT).is_file(), reason="needs the macOS Arial Black font")
    def test_the_letters_touch(self):
        p, s = mi.glyph_mask("P"), mi.glyph_mask("S")
        x, y = mi.p_bowl_corner(p)
        sx, sy = mi.s_top_left(s)
        assert 0 <= x < p.width and 0 <= y < p.height and 0 <= sx < s.width and re.fullmatch(r"\d+", str(sy))
        assert mi.build().size[0] > p.width
