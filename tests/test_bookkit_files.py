"""bookkit functions that work on a book's files: movie plan, scene edits, film format, voice cast."""
import csv
import json

import pytest

import bookkit as bk
from conftest import write_csv


def rows(path):
    return list(csv.DictReader(open(path, newline="")))


@pytest.fixture
def d(tmp_path):
    p = tmp_path / "demo"
    p.mkdir()
    return p


class TestBuildMovies:
    def make(self, d, chapters=3, shots=4, narration="word " * 20):
        write_csv(d / "all_shots.csv", [{"chapter": f"c{c}", "shot": s, "prompt": "p"} for c in range(1, chapters + 1) for s in range(1, shots + 1)])
        write_csv(d / "audio_shots.csv", [{"chapter": f"c{c}", "shot": s, "narration": narration} for c in range(1, chapters + 1) for s in range(1, shots + 1)])

    def test_every_row_lands_in_exactly_one_movie(self, d):
        self.make(d, chapters=6)
        plan = bk.build_movies(d, minutes=1.0)
        movies = plan["shots"]
        assert plan["minutes"] == 1.0 and (d / "movies.json").exists()
        covered = [r for m in movies for r in range(m["rows"][0], m["rows"][1] + 1)]
        assert covered == list(range(1, 25))
        assert all(m["clips"] == m["rows"][1] - m["rows"][0] + 1 for m in movies)
        assert [m["id"] for m in movies] == list(range(1, len(movies) + 1))

    def test_no_csv_means_no_plan_for_that_mode(self, d):
        self.make(d)
        assert "chapters" not in bk.build_movies(d)

    def test_read_csv_of_a_missing_file(self, d):
        assert bk.read_csv(d / "none.csv") == []


class TestSceneFields:
    @pytest.fixture(autouse=True)
    def csvs(self, d):
        write_csv(d / "all_shots.csv", [{"chapter": "c1", "shot": 1, "prompt": "old"}, {"chapter": "c1", "shot": 2, "prompt": "other"}])
        write_csv(d / "audio_shots.csv", [{"chapter": "c1", "shot": 1, "narration": "said", "lines_json": json.dumps([["Eve", "said", "af_bella"]])},
                                          {"chapter": "c1", "shot": 2, "narration": "x", "lines_json": "[]"}])

    def test_set_prompt_changes_one_row(self, d):
        assert bk.set_scene_field(d, "c1", 1, "prompt", "new") == 1
        assert [r["prompt"] for r in rows(d / "all_shots.csv")] == ["new", "other"]

    def test_same_value_changes_nothing(self, d):
        assert bk.set_scene_field(d, "c1", 1, "prompt", "old") == 0

    def test_narration_keeps_the_speaker_and_voice(self, d):
        bk.set_scene_field(d, "c1", 1, "narration", "now this")
        assert json.loads(rows(d / "audio_shots.csv")[0]["lines_json"]) == [["Eve", "now this", "af_bella"]]

    def test_narration_with_unreadable_lines_falls_back_to_narrator(self, d):
        write_csv(d / "audio_shots.csv", [{"chapter": "c1", "shot": 1, "narration": "a", "lines_json": "{bad"}])
        bk.set_scene_field(d, "c1", 1, "narration", "b")
        assert json.loads(rows(d / "audio_shots.csv")[0]["lines_json"]) == [["NARRATOR", "b"]]

    def test_saved_edits_are_reapplied_after_a_rebuild(self, d):
        (d / "prompt_edits.json").write_text(json.dumps({"c1#1": {"chapter": "c1", "shot": 1, "fields": {"prompt": {"original": "old", "edited": "mine"}}}}))
        write_csv(d / "all_shots.csv", [{"chapter": "c1", "shot": 1, "prompt": "rebuilt"}])        # the rebuild put the original back
        assert bk.apply_prompt_edits(d) == 1 and rows(d / "all_shots.csv")[0]["prompt"] == "mine"

    def test_no_edits_file(self, d):
        assert bk.apply_prompt_edits(d) == 0


class TestFilmFormat:
    @pytest.fixture(autouse=True)
    def csvs(self, d):
        write_csv(d / "all_shots.csv", [{"chapter": "c1", "shot": 1, "continues": "1"}, {"chapter": "c1", "shot": 2, "continues": ""}])

    def test_default(self, d):
        assert bk.read_film_format(d) == {"aspect": "", "chain": False}

    def test_saved_and_written_into_the_csv(self, d):
        aspect = next(iter(bk.ASPECTS))
        assert bk.apply_film_format(d, aspect=aspect, chain=True) == {"aspect": aspect, "chain": True}
        r = rows(d / "all_shots.csv")
        assert [x["aspect"] for x in r] == [aspect, aspect] and [x["chain"] for x in r] == ["1", ""]        # only shots that continue the action chain
        assert bk.read_film_format(d) == {"aspect": aspect, "chain": True}

    def test_options_left_out_stay(self, d):
        aspect = next(iter(bk.ASPECTS))
        bk.apply_film_format(d, aspect=aspect, chain=True)
        assert bk.apply_film_format(d, chain=False) == {"aspect": aspect, "chain": False}
        assert bk.apply_film_format(d, aspect="") == {"aspect": "", "chain": False}

    def test_unknown_aspect(self, d):
        with pytest.raises(ValueError, match="unknown aspect"):
            bk.apply_film_format(d, aspect="7:3")

    def test_garbage_in_the_file_is_ignored(self, d):
        (d / bk.FILM_FORMAT_FILE).write_text(json.dumps({"aspect": "bogus", "chain": 1}))
        assert bk.read_film_format(d) == {"aspect": "", "chain": True}


class TestVoices:
    @pytest.mark.parametrize("word,want", [("af_bella", "af_bella"), ("nonsense", ""), ("", ""), (None, ""), ("AF_BELLA", "")])
    def test_voice_id(self, word, want):
        assert bk.voice_id(word) == want

    def test_voice_words_map_to_kokoro_ids(self):
        assert all(bk.KOKORO_VOICE_RE.match(bk.voice_id(w)) for w in ("male", "female") if bk.voice_id(w))

    def test_read_cast_drops_invalid_voices(self, d):
        (d / bk.VOICE_CAST_FILE).write_text(json.dumps({"cast": {"Eve": "af_bella", "Bob": "robot", "N": 5}}))
        assert bk.read_voice_cast(d) == {"Eve": "af_bella"}

    def test_cast_of_the_wrong_shape(self, d):
        (d / bk.VOICE_CAST_FILE).write_text(json.dumps({"cast": ["x"]}))
        assert bk.read_voice_cast(d) == {}

    def test_apply_revoices_matching_speakers_only(self, d):
        write_csv(d / "audio_shots.csv", [
            {"chapter": "c", "shot": 1, "lines_json": json.dumps([["Eve", "hi", "af_bella"], ["NARRATOR", "x"]])},
            {"chapter": "c", "shot": 2, "lines_json": json.dumps([["Adam", "yo"]])},
            {"chapter": "c", "shot": 3, "lines_json": "not json"},
            {"chapter": "c", "shot": 4, "lines_json": json.dumps({"not": "a list"})}])
        assert bk.apply_voice_cast(d, {"Nobody": "", "Ghost": "bm_george"}) == []                    # a blank voice or an absent speaker changes nothing
        changed = bk.apply_voice_cast(d, {" EVE ": "bf_emma"})                                       # speaker names match ignoring case and spaces
        assert changed == [1]
        assert json.loads(rows(d / "audio_shots.csv")[0]["lines_json"]) == [["Eve", "hi", "bf_emma"], ["NARRATOR", "x"]]
        assert bk.apply_voice_cast(d, {"eve": "bf_emma"}) == []                                     # already applied: nothing changes

    def test_empty_cast_changes_nothing(self, d):
        assert bk.apply_voice_cast(d, {}) == []
