"""generation_steps / film_steps / storyboard / project_info on a throw-away book (fake_root + book fixtures)."""
import pytest

from conftest import write_csv
from studio_app import generation, planner, projects, takes
from studio_app.common import PlanError

KAGGLE = {"service": "kaggle", "gpu": "NvidiaTeslaT4", "kaggle_user": "pat"}


def plan(book, **kw):
    return planner.build_plan({"project": "demo", **KAGGLE, **kw})


class TestGenerationValidation:
    @pytest.mark.parametrize("patch,msg", [
        ({"service": "mars"}, "choose where the models run"),
        ({"gpu": "NoGpu"}, "is not an option"),
        ({"kaggle_user": "x"}, "Kaggle username"),
        ({"steps": {"keyframes": True}}, "image model"),
        ({"steps": {"keyframes": True}, "keyframe_model": "nope"}, "image model"),
        ({"steps": {"video": True}, "video_models": ["ltx_video"], "sync": "weird"}, "bad sync mode"),
        ({"steps": {"video": True}, "video_models": ["ltx_video"], "aspect": "5:7"}, "unknown film shape"),
        ({"steps": {"video": True}, "video_models": ["ltx_video"], "look": "nonsense"}, "unknown look"),
        ({"steps": {"video": True}, "video_models": ["ltx_video"], "batch": -1}, "batch"),
        ({"steps": {"video": True}, "video_models": ["ltx_video"], "movies": {"mode": "ids", "ids": []}}, "tick at least one movie"),
        ({"steps": {"keyframes": True}, "keyframe_model": "flux2_klein_4b", "granularity": "chapters"}, "Every shot"),
        ({"steps": {"keyframes": True}, "keyframe_model": "flux2_klein_4b", "service": "colab", "gpu": "T4"}, "Kaggle or this computer"),
    ])
    def test_refused(self, book, patch, msg):
        base = {"steps": {"video": True}, "video_models": ["ltx_video"], "movies": {"mode": "all"}}
        with pytest.raises(PlanError, match=msg):
            plan(book, **{**base, **patch})

    def test_needs_planned_movies(self, book):
        (book / "movies.json").write_text("{}")
        with pytest.raises(PlanError, match="no movies planned"):
            plan(book, steps={"video": True}, video_models=["ltx_video"], movies={"mode": "all"})


class TestGenerationSteps:
    def test_video_batches_and_labels(self, book):
        steps = plan(book, steps={"video": True}, video_models=["ltx_video"], movies={"mode": "all"}, batch=2)
        labels = [s["label"] for s in steps]
        assert labels[0].startswith("Film format") and "rows 1-2" in labels[1] and "rows 3-4" in labels[2]
        assert steps[1]["env"]["PROJECT"] == "demo" and steps[1]["env"]["KAGGLE_USER"] == "pat" and steps[1]["argv"][0].endswith("run_kaggle_model.sh")

    def test_range_limits_rows(self, book):
        steps = plan(book, steps={"video": True}, video_models=["ltx_video"], movies={"mode": "first", "n": 1}, range_start=2, range_end=3)
        assert [s["label"] for s in steps][1:] == ["Movie 1 video ltx_video: rows 2-3"]

    def test_keyframes_come_before_video_and_i2v_gets_the_keyframe_model(self, book):
        steps = plan(book, steps={"keyframes": True, "video": True}, keyframe_model="flux2_klein_4b", video_models=["ltx_video_i2v"], movies={"mode": "all"})
        labels = [s["label"] for s in steps]
        assert labels[1].startswith("Write keyframes.csv") and "keyframes flux2_klein_4b" in labels[2] and "video ltx_video_i2v" in labels[3]
        assert steps[3]["env"]["KEYFRAME_MODEL"] == "flux2_klein_4b"

    def test_character_pictures_need_a_series(self, book):
        with pytest.raises(PlanError, match="character pictures steer only"):
            plan(book, steps={"keyframes": True}, keyframe_model="sd35_large", keyframe_refs=True, movies={"mode": "all"})
        with pytest.raises(PlanError, match="no character series"):
            plan(book, steps={"keyframes": True}, keyframe_model="flux2_klein_4b", keyframe_refs=True, keyframe_series="ghosts", movies={"mode": "all"})

    def test_merge_and_mix_steps_use_validated_numbers(self, book):
        steps = plan(book, steps={"video": True, "merge": True, "mix": True}, video_models=["ltx_video"], movies={"mode": "all"},
                     sync="gentle", vol={"narration": 2, "sfx": 0.1, "music": 0.3}, duck=False)
        mix = next(s for s in steps if "final film" in s["label"])["argv"]
        assert mix[mix.index("--vol-narration") + 1] == "2.0" and "--no-duck" in mix and mix[mix.index("--sync") + 1] == "gentle"
        assert any("silent film" in s["label"] for s in steps)

    def test_volume_out_of_range_is_refused(self, book):
        with pytest.raises(PlanError, match="vol|between"):
            plan(book, steps={"mix": True}, video_models=["ltx_video"], movies={"mode": "all"}, vol={"narration": 99})

    def test_music_bed_makes_one_cue_per_chapter(self, book):
        write_csv(book / "audio_chapters.csv", [{"chapter": "1", "music": "calm"}])
        (book / "movies.json").write_text('{"shots": [{"id": 1, "rows": [1, 4], "first_chapter": "1", "last_chapter": "1"}]}')
        steps = plan(book, steps={"audio": True}, audio=["musicgen"], music_bed=True, movies={"mode": "all"})
        assert [s["label"] for s in steps][-1].startswith("Movie 1 music, one cue per chapter")


class TestFilm:
    OPT = {"film": True, "aspect": "16:9", **KAGGLE}

    def test_film_plan_skips_nothing_when_nothing_exists(self, book):
        steps = generation.film_steps({**self.OPT, "sync": "gentle"}, "demo")
        labels = [s["label"] for s in steps]
        assert labels[0].startswith("Film format") and "keyframes: rows 1-4" in labels[2]
        assert any("narration: rows 1-4" in x for x in labels) and labels[-1].endswith("final film")
        assert {"expand": next(s for s in steps if "expand" in s)["expand"]} == {"expand": "film_video"}

    def test_existing_files_are_skipped(self, book):
        kf = book / "images" / "flux2_klein_4b_keyframes"
        kf.mkdir(parents=True)
        for n in (1, 2, 3, 4):
            (kf / f"image-{n:04d}.png").write_bytes(b"x")
        labels = [s["label"] for s in generation.film_steps({**self.OPT, "sync": "gentle"}, "demo")]
        assert not any("keyframes: rows" in x for x in labels)

    def test_space_runs_cover_only_people_shots(self, book):
        steps = generation.film_steps({**self.OPT, "sync": "gentle", "film_space": True}, "demo")
        space = [s for s in steps if "Pika" in s["label"]]
        assert [s["argv"][-2:] for s in space] == [["1", "1"], ["3", "3"]] and space[0]["ok_codes"] == (0, 1)

    def test_video_steps_are_decided_late(self, book):
        clips = book / "videos" / "ltx_video_fast_i2v"
        clips.mkdir(parents=True)
        (clips / "shot-0002.mp4").write_bytes(b"x")
        out = generation.film_video_steps(self.OPT, "demo")
        assert [s["label"].split(": ")[1] for s in out] == ["rows 1-1", "rows 3-4"]

    @pytest.mark.parametrize("patch,msg", [({"service": "colab"}, "Kaggle or this computer"), ({"gpu": "bad"}, "not an option"), ({"kaggle_user": ""}, "Kaggle username")])
    def test_refusals(self, book, patch, msg):
        with pytest.raises(PlanError, match=msg):
            generation.film_steps({**self.OPT, "sync": "gentle", **patch}, "demo")

    def test_status_counts(self, book):
        (book / "scripts").mkdir()
        (book / "scripts" / "chapter-001.json").write_text("{}")
        (book / "films").mkdir()
        (book / "films" / "a.mp4").write_bytes(b"x")
        st = generation.film_status("demo")
        assert st["exists"] and st["chapters"] == 1 and st["shots"] == 4 and st["scripts"] == 1 and st["continuity"] and st["films"] == ["demo/films/a.mp4"]
        assert generation.film_status("ghost") == {"exists": False}
        with pytest.raises(PlanError):
            generation.film_status("../x")


def test_keyframe_size_follows_the_film_shape():
    w, h = generation.keyframe_size("flux2_klein_4b", "ltx_video_fast_i2v", "16:9")
    assert w % 64 == 0 and h % 64 == 0 and w > h
    w2, h2 = generation.keyframe_size("flux2_klein_4b", "ltx_video_fast_i2v", "9:16")
    assert h2 > w2 and abs(w * h - w2 * h2) / (w * h) < 0.25


def test_clean_stages():
    ok = generation.clean_stages([{"label": "young", "chapters": "1-12", "token": "x"}, {"label": "old", "chapters": "13-", "token": "y"}])
    assert [s["label"] for s in ok] == ["young", "old"]
    for bad in ({"label": "", "chapters": "1", "token": "x"}, {"label": "a", "chapters": "x", "token": "x"}, {"label": "a", "chapters": "1", "token": ""},
                {"label": "a", "chapters": "1", "token": "z" * 401}):
        with pytest.raises(PlanError):
            generation.clean_stages([bad])
    assert len(generation.clean_stages([{"label": f"s{i}", "chapters": "1", "token": "x"} for i in range(12)])) == 8


def test_sound_flags():
    assert generation.sound_flags({}, False) == []
    assert generation.sound_flags({"duck": False, "loudnorm": False}, True) == ["--no-duck", "--no-loudnorm", "--music-bed"]


class TestStoryboardAndProject:
    def test_storyboard_cards(self, book):
        clips = book / "videos" / "ltx_video"
        clips.mkdir(parents=True)
        (clips / "shot-0002.mp4").write_bytes(b"x")
        sb = takes.storyboard("demo", 1, 3)
        assert [c["n"] for c in sb["cards"]] == [1, 2, 3] and sb["rows"] == 4
        assert sb["cards"][1]["clips"] == {"ltx_video": "videos/ltx_video/shot-0002.mp4"} and sb["cards"][0]["narration"] == "line 1"
        assert takes.storyboard("demo", 0, 99999)["end"] == 4
        with pytest.raises(PlanError):
            takes.storyboard("ghost", 1, 2)

    def test_project_info(self, book):
        info = projects.project_info("demo")
        assert info["slug"] == "demo" and info["chapters"] == 1 and info["built"] and info["continuity"] and not info["not_started"]
        assert info["movies"]["shots"][0]["id"] == 1 and info["have"]["films"] == 0
        assert projects.project_info("ghost")["not_started"]
