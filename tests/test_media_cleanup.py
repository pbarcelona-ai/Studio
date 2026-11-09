"""media_inventory / film_step / cleanup_scan / files_inventory / trash_files on a throw-away Studio folder."""
import os
import time

import pytest

from studio_app import cleanup, media
from studio_app.common import PlanError


@pytest.fixture()
def downloaded(book):
    for n in (1, 2, 3):
        (book / "videos" / "ltx_video").mkdir(parents=True, exist_ok=True)
        (book / "videos" / "ltx_video" / f"shot-{n:04d}.mp4").write_bytes(b"v" * n)
    (book / "audio" / "kokoro").mkdir(parents=True)
    for n in (1, 2):
        (book / "audio" / "kokoro" / f"narration-{n:04d}.wav").write_bytes(b"w")
    (book / "audio" / "kokoro" / "sfx-0001.wav").write_bytes(b"w")
    return book


class TestInventory:
    def test_lists_rows_per_folder_with_prompt_text(self, downloaded):
        inv = media.media_inventory("demo")
        assert inv["videos"] == {"videos/ltx_video": [1, 2, 3]}
        assert inv["narration"] == {"audio/kokoro": [1, 2]} and inv["sfx"] == {"audio/kokoro": [1]} and inv["music"] == {}
        assert inv["texts"]["videos/ltx_video"]["2"] == "1: a mountain at dawn"
        assert set(inv["seconds"]["videos/ltx_video"]) == {"1", "2", "3"}

    def test_unknown_project(self, fake_root):
        with pytest.raises(PlanError):
            media.media_inventory("ghost")


class TestFilmStep:
    OPT = {"project": "demo", "video_source": "videos/ltx_video", "sources": {"narration": "audio/kokoro"}, "rows": [{"n": 2, "narration": True}, {"n": 1}], "name": "cut1"}

    def test_builds_the_selection_in_page_order(self, downloaded):
        slug, selection, step = media.film_step({**self.OPT, "title": "My\x00 Film\n", "transition": "fade", "fade": 0.8, "burn_captions": True})
        assert slug == "demo" and [c["row"] for c in selection["clips"]] == [2, 1]
        assert selection["clips"][0]["narration"] == "audio/kokoro/narration-0002.wav" and selection["clips"][1]["narration"] is None
        assert selection["title"] == "My  Film"
        argv = step["argv"]
        assert argv[argv.index("--out") + 1] == "cut1.mp4" and "--burn-captions" in argv and argv[argv.index("--transition") + 1] == "fade"
        assert (downloaded / "films").is_dir()

    @pytest.mark.parametrize("patch,msg", [
        ({"name": "../evil"}, "film name"), ({"video_source": "videos/none"}, "where the video clips"),
        ({"sources": {"sfx": "audio/none"}}, "unknown sfx folder"), ({"rows": []}, "at least one clip"),
        ({"rows": [{"n": 9}]}, "row 9 has no clip"), ({"rows": [{"n": 1}, {"n": 1}]}, "listed twice"),
        ({"sync": "bogus"}, "bad sync"), ({"transition": "wipe"}, "bad transition"), ({"fade": 9}, "fade"),
        ({"rows": [{"n": 1, "trim_start": 99}]}, "trim_start")])
    def test_refusals(self, downloaded, patch, msg):
        with pytest.raises(PlanError, match=msg):
            media.film_step({**self.OPT, **patch})


class TestCleanupScan:
    def categories(self):
        return {c["id"]: [i["path"] for i in c["items"]] for c in cleanup.cleanup_scan()}

    def test_finds_each_kind_of_leftover(self, downloaded, fake_root):
        (fake_root / "scripts" / "__pycache__").mkdir(parents=True)
        (fake_root / "scripts" / "__pycache__" / "x.pyc").write_bytes(b"1")
        (fake_root / "books" / "half.pdf.part").write_bytes(b"1")
        (downloaded / "films").mkdir()
        (downloaded / "films" / "_selection.json").write_text("{}")
        (downloaded / "videos" / "empty_model").mkdir()
        (downloaded / "videos" / "ltx_video" / "shot-0099.mp4").write_bytes(b"x")          # numbered past the 4 prompts
        (downloaded / "logs").mkdir()
        (downloaded / "logs" / "run.log").write_text("x")
        found = self.categories()
        assert found["pycache"] == ["scripts/__pycache__"]
        assert "books/half.pdf.part" in found["temp"] and "projects/books/demo/films/_selection.json" in found["temp"]
        assert found["empty"] == ["projects/books/demo/videos/empty_model"]
        assert found["stale"] == ["projects/books/demo/videos/ltx_video/shot-0099.mp4"]
        assert found["logs"] == ["projects/books/demo/logs/run.log"]

    def test_keeps_the_three_newest_notebooks_and_always_lists_tpu(self, fake_root):
        now = time.time()
        for i in range(5):
            f = fake_root / f"Studio_Kaggle_video_m{i}.ipynb"
            f.write_text("{}")
            os.utime(f, (now - 100 + i, now - 100 + i))
        (fake_root / "Studio_Kaggle_tpu_wan.ipynb").write_text("{}")
        (fake_root / "colab_generate_video_m0.py").write_text("")
        (fake_root / "colab_generate_video_m4.py").write_text("")
        listed = sorted(self.categories()["notebooks"])
        assert listed == ["Studio_Kaggle_tpu_wan.ipynb", "Studio_Kaggle_video_m0.ipynb", "Studio_Kaggle_video_m1.ipynb", "colab_generate_video_m0.py"]

    def test_cleanup_delete_moves_only_what_the_scan_found(self, downloaded, fake_root):
        (fake_root / "scripts" / "__pycache__").mkdir(parents=True)
        (fake_root / "scripts" / "__pycache__" / "x.pyc").write_bytes(b"123")
        res = cleanup.cleanup_delete(["pycache", "../../etc"])
        assert res["moved"] == 1 and not (fake_root / "scripts" / "__pycache__").exists()
        assert (fake_root / "scripts").is_dir() and (downloaded / "all_shots.csv").exists()


class TestFilesInventory:
    def test_groups_by_folder_with_row_text(self, downloaded):
        inv = cleanup.files_inventory("demo")
        assert [f["name"] for f in inv["videos/ltx_video"]] == ["shot-0001.mp4", "shot-0002.mp4", "shot-0003.mp4"]
        assert inv["videos/ltx_video"][0]["text"] == "1: a woman walks in a garden"
        assert inv["audio/kokoro"][0]["text"].startswith("1: line 1")

    def test_trash_files_moves_chosen_and_tidies_empty_folders(self, downloaded, fake_root):
        res = cleanup.trash_files("demo", "audio/kokoro", ["narration-0001.wav", "narration-0002.wav", "sfx-0001.wav", "not-listed.wav"])
        assert res["moved"] == 3 and not (downloaded / "audio" / "kokoro").exists()
        with pytest.raises(PlanError, match="unknown folder"):
            cleanup.trash_files("demo", "audio/zzz", ["a"])
        with pytest.raises(PlanError, match="at least one file"):
            cleanup.trash_files("demo", "videos/ltx_video", ["nope.mp4"])
