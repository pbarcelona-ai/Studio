"""Music that follows the scenes: the cue prompts, audio_scenes.csv, the run steps and the mix."""
import csv
import json

import pytest

import adaptation as ad
from test_adaptation import GOOD, make_plan  # noqa: F401  (GOOD is used by the approved fixture)

imageio_ffmpeg = pytest.importorskip("imageio_ffmpeg")
from test_mix_film import film, media, mix, seconds  # noqa: E402,F401  (fixtures: three 1-second clips with narration, sfx and music)


class TestPrompt:
    SCENE = {"summary": "Eve and Adam walk out of the garden at dusk and the gate closes behind them for the last time", "time_of_day": "dusk", "keep": "full"}

    def test_parts_and_limit(self):
        p = ad.scene_music_prompt(self.SCENE, "slow strings and low harp.", ["solemn cello", "Solemn cello.", "distant choir", "ignored third"])
        assert p.startswith("cinematic score, slow strings and low harp; dusk scene; played out, building; Eve and Adam walk")
        assert p.count("solemn cello") + p.count("Solemn cello") == 1 and "distant choir" in p and "ignored third" not in p
        long = ad.scene_music_prompt({**self.SCENE, "summary": "word " * 100}, "t", ["m " * 200], limit=100)
        assert len(long) <= 100

    def test_unknown_time_and_no_theme(self):
        assert ad.scene_music_prompt({"summary": "A man walks", "time_of_day": "unknown"}, "", []) == "cinematic score; steady; A man walks"


@pytest.fixture()
def scored(book):
    """books/demo with a plan (scenes S001-S004 over chapters 1-6) and two scripted chapters."""
    ad.save(book, make_plan())
    (book / "scripts").mkdir()
    for ch, music in ((1, "harp, calm"), (2, "drums, tense")):
        shots = [{"n": i, "prompt": "p", "negative": "", "characters": [], "location": "", "continues": False, "speaker": "NARRATOR", "narration": f"line {i}", "voice": "",
                  "sfx": "wind", "music": music} for i in range(1, 4)]
        (book / "scripts" / f"chapter-00{ch}.json").write_text(json.dumps({"chapter": ch, "shots": shots}))
    return book


def rows(path):
    with open(path, newline="") as f:
        return list(csv.DictReader(f))


class TestBuild:
    def test_cues_per_scene_and_scene_column(self, scored, run_script):
        code, out = run_script("book_build.py", "demo")
        assert code is None and "music cues per scene" in out
        shots, scenes = rows(scored / "audio_shots.csv"), rows(scored / "audio_scenes.csv")
        assert [r["scene"] for r in shots] == ["demo-S001"] * 3 + ["demo-S001"] * 3          # chapters 1 and 2 are both taken from scene S001
        assert [r["chapter"] for r in scenes] == ["demo-S001"] and "harp, calm" in scenes[0]["music"] and "drums, tense" in scenes[0]["music"]
        assert scenes[0]["music"].startswith("cinematic score")

    def test_no_plan_no_scene_file_and_a_stale_file_is_removed(self, scored, run_script):
        run_script("book_build.py", "demo")
        (scored / "adaptation" / "adaptation.json").unlink()
        run_script("book_build.py", "demo")
        assert not (scored / "audio_scenes.csv").exists() and "scene" not in rows(scored / "audio_shots.csv")[0]


class TestSteps:
    @pytest.fixture()
    def approved(self, scored, run_script):
        import screenplay as sp
        plan = ad.load(scored)
        for s in plan["scenes"]:
            sp.save_scene(scored, s["id"], GOOD, edited=False)
        sp.approve(scored, plan)
        (scored / "movies.json").write_text(json.dumps({"shots": [{"id": 1, "rows": [1, 6], "first_chapter": "demo-001", "last_chapter": "demo-002"}], "chapters": []}))
        run_script("book_build.py", "demo")
        return scored

    def test_audio_steps_make_the_scene_cues(self, server, approved):
        st, out = server.api("POST", "/api/plan", {"project": "demo", "music_scenes": True, "music_bed": True, "granularity": "shots", "service": "kaggle", "gpu": "NvidiaTeslaT4", "kaggle_user": "tester",
                                                    "audio": ["musicgen"], "movies": {"mode": "all"}, "steps": {"audio": True}})
        assert st == 200, out
        cmds = [s["cmd"] for s in out["steps"]]
        assert any("audio_scenes.csv" in c and "audio_musicgen" in c for c in cmds)

    def test_scene_music_needs_the_scene_list(self, server, approved):
        (approved / "audio_scenes.csv").unlink()
        st, out = server.api("POST", "/api/plan", {"project": "demo", "music_scenes": True, "granularity": "shots", "service": "kaggle", "gpu": "NvidiaTeslaT4", "kaggle_user": "tester",
                                                    "audio": ["musicgen"], "movies": {"mode": "all"}, "steps": {"audio": True}})
        assert st == 400 and "scene music list" in out["error"]


class TestMix:
    @pytest.fixture()
    def scenes_film(self, film, media):  # noqa: F811  (the fixtures imported above)
        """The film fixture's three shots, scenes S001 (shots 1-2) and S002 (shot 3), one cue each."""
        with open(film / "audio_shots.csv", "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["chapter", "shot", "lines_json", "narration", "sfx", "music", "scene"])
            for i, scene in ((1, "demo-S001"), (2, "demo-S001"), (3, "demo-S002")):
                w.writerow(["1", i, json.dumps([["NARRATOR", f"Caption number {i}."]]), f"Caption number {i}.", "", "", scene])
        with open(film / "audio_scenes.csv", "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["chapter", "shot", "lines_json", "narration", "sfx", "music"])
            w.writerow(["demo-S001", 1, "[]", "", "", "calm"])
            w.writerow(["demo-S002", 1, "[]", "", "", "tense"])
        (film / "audio" / "musicgen_scenes").mkdir()
        for n in (1, 2):
            (film / "audio" / "musicgen_scenes" / f"music-{n:04d}.wav").write_bytes((media / "music.wav").read_bytes())
        return film

    def test_each_scene_gets_its_own_cue(self, scenes_film, run_script):
        out = mix(run_script, "--music-scenes", "--sync", "trim", "--out", "scenes.mp4")
        assert "'music': 2" in out and (scenes_film / "films" / "scenes.mp4").is_file() and 2.5 < seconds(scenes_film / "films" / "scenes.mp4") < 3.5

    def test_a_missing_scene_cue_is_named(self, scenes_film, run_script):
        (scenes_film / "audio" / "musicgen_scenes" / "music-0002.wav").unlink()
        out = mix(run_script, "--music-scenes", "--sync", "trim", "--out", "half.mp4")
        assert "no usable music cue for chapter row 2 (music-0002.wav)" in out and "'music': 1" in out

    def test_options_conflict(self, run_script):
        assert "not both" in run_script("mix_film.py", "--music-bed", "--music-scenes")[0]
        assert "--music-scenes" in run_script("mix_film.py", "--music-scenes", "--chapters")[0]
