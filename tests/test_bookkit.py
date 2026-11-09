"""bookkit: text helpers, JSON extraction, shot allocation, character stages, prompt composition and the language-model wrappers (subprocess faked)."""
import json
import subprocess
from types import SimpleNamespace

import pytest

import bookkit as bk


class TestText:
    @pytest.mark.parametrize("raw,want", [("Hello World!", "hello_world"), ("  --A/B--  ", "a_b"), ("!!!", "book"), ("x" * 100, "x" * 40)])
    def test_slugify(self, raw, want):
        assert bk.slugify(raw) == want

    def test_project_dir_rejects_bad_names(self):
        for bad in ("A", "../x", "a b", ""):
            with pytest.raises(ValueError):
                bk.project_dir(bad)

    def test_words_and_sentences(self):
        assert bk.words("a b  c") == 3
        assert bk.sentences('He said "Go." Then left. Why?') == ['He said "Go."', "Then left.", "Why?"]
        assert bk.sentences("   ") == []

    def test_verse_numbers_are_dropped(self):
        assert bk.strip_verse_numbers("1 And it was good. 2 And God saw it.") == "And it was good. And God saw it."

    def test_continuity_file_is_named_after_the_folder(self, tmp_path):
        assert bk.continuity_file(tmp_path / "demo") == tmp_path / "demo" / "demo.json"

    def test_json_helpers(self, tmp_path):
        p = tmp_path / "a.json"
        assert bk.read_json(p, "dflt") == "dflt"
        bk.write_json(p, {"é": 1})
        assert bk.read_json(p) == {"é": 1} and "é" in p.read_text()


class TestExtractJson:
    def test_plain_fenced_and_chatty(self):
        assert bk.extract_json('{"a": 1}') == {"a": 1}
        assert bk.extract_json('```json\n{"a": {"b": 2}}\n```') == {"a": {"b": 2}}
        assert bk.extract_json('Sure! Here it is: {"a": "}"} hope that helps') == {"a": "}"}

    def test_escaped_quotes(self):
        assert bk.extract_json(r'{"a": "say \"hi\" {"}') == {"a": 'say "hi" {'}

    def test_no_object(self):
        with pytest.raises(ValueError, match="no JSON"):
            bk.extract_json("nothing here")

    def test_cut_off(self):
        with pytest.raises(ValueError, match="cut off"):
            bk.extract_json('{"a": [1, 2')


class TestShots:
    @pytest.mark.parametrize("w,wps,lo,hi,ov,want", [(1000, 100, 2, 12, None, 10), (50, 100, 2, 12, None, 2), (5000, 100, 2, 12, None, 12), (1000, 100, 2, 12, 7, 7), (10, 0, 1, 5, None, 5), (10, 5, 1, 5, 0, 2)])
    def test_shot_count(self, w, wps, lo, hi, ov, want):
        assert bk.shot_count(w, wps, lo, hi, ov) == want

    def test_slices_cover_the_text_in_order(self):
        text = " ".join(f"Sentence number {i} has some words." for i in range(10))
        parts = bk.slice_text(text, 3)
        assert len(parts) == 3 and " ".join(parts) == text

    def test_more_slices_than_sentences(self):
        assert len(bk.slice_text("One. Two.", 5)) == 2

    @pytest.mark.parametrize("spec,ch,want", [("5", 5, True), ("5", 6, False), ("5-12", 12, True), ("5-12", 13, False), ("5-", 999, True), (" 3 - 4 ", 4, True),
                                              ("x", 1, False), ("", 1, False), (None, 1, False), ("5", None, False)])
    def test_chapter_in(self, spec, ch, want):
        assert bk.chapter_in(spec, ch) is want


class TestCharacters:
    char = {"name": "Eve", "token": "young woman", "stages": [{"chapters": "5-", "token": "old woman"}, {"chapters": "bad", "token": "x"}, "junk", {"chapters": "1", "token": " "}]}

    def test_stage_applies_to_realistic_looks_only(self):
        assert bk.character_token(self.char, 6) == "old woman"
        assert bk.character_token(self.char, 2) == "young woman"
        assert bk.character_token(self.char, 6, "live_action") == "old woman"
        assert bk.character_token(self.char, 6, "anime") == "young woman" and bk.stage_for(self.char, 6, "anime") is None
        assert bk.character_token({"name": "x"}, 1) == ""

    def test_negative_prompt(self):
        assert bk.shot_negative() == bk.VIDEO_NEGATIVE
        assert bk.shot_negative(" gore, ").startswith("gore, ")


class TestComposePrompt:
    cont = {"visual_style": "oil painting.", "characters": [{"name": "Eve", "token": "Eve: a woman in red"}, {"name": "Adam", "token": "a tall man"}],
            "locations": [{"name": "Garden", "token": "a lush garden"}]}

    def test_all_parts_in_order(self):
        out = bk.compose_prompt("She walks.", ["eve", "Adam", "ghost"], self.cont, location="garden", global_positives="cinematic")
        assert out.startswith("cinematic, She walks., ") or out.startswith("cinematic, She walks")
        assert "EVE: a woman in red" in out and "ADAM: a tall man" in out and "SETTING: a lush garden" in out and "oil painting" in out
        assert out.count("EVE:") == 1 and "Eve: Eve" not in out and "ghost" not in out.lower()

    def test_respects_the_limit_dropping_location_then_characters(self):
        for limit in (300, 120, 60, 30):
            out = bk.compose_prompt("She walks through a very long and winding story.", ["Eve", "Adam"], self.cont, limit=limit, location="Garden")
            assert len(out) <= limit
        short = bk.compose_prompt("She walks.", ["Eve", "Adam"], self.cont, limit=80, location="Garden")
        assert "SETTING" not in short or "ADAM" in short


class TestEstimates:
    def test_a_clip_is_never_shorter_than_the_minimum(self):
        assert bk.estimate_seconds("") == bk.CLIP_SECONDS and bk.estimate_seconds(None) == bk.CLIP_SECONDS
        assert bk.estimate_seconds("word " * 100) > bk.CLIP_SECONDS

    def test_group_chapters_ends_on_chapter_ends(self):
        chs = [{"label": str(i), "rows": (i, i), "seconds": 60.0} for i in range(1, 11)]
        movies = bk.group_chapters(chs, 180)
        assert [c["label"] for m in movies for c in m] == [str(i) for i in range(1, 11)]       # nothing lost or repeated
        assert [[c["label"] for c in m] for m in movies] == [["1", "2", "3"], ["4", "5", "6"], ["7", "8", "9", "10"]]     # the short tail joins the last movie

    def test_single_movie_and_empty(self):
        assert bk.group_chapters([], 600) == []
        assert len(bk.group_chapters([{"label": "1", "rows": (1, 1), "seconds": 30.0}], 600)) == 1

    def test_cost_note(self, monkeypatch):
        monkeypatch.setitem(bk.COST, "usd", 0.0)
        assert bk.cost_note() == ""
        monkeypatch.setitem(bk.COST, "usd", 0.05)
        assert bk.cost_note() == ", $0.05 at list price"


class TestHfJson:
    def test_retries_once_with_the_error(self):
        replies = iter(["not json", '{"ok": true}'])
        seen = []

        def chat(msgs, model):
            seen.append(msgs)
            return next(replies)
        assert bk.hf_json([{"role": "user", "content": "q"}], chat=chat) == {"ok": True}
        assert "rejected" in seen[1][-1]["content"] and len(seen[1]) == 3

    def test_gives_up(self):
        with pytest.raises(RuntimeError, match="usable JSON"):
            bk.hf_json([{"role": "user", "content": "q"}], chat=lambda m, mo: "nope")

    def test_validation_failure_is_retried(self):
        replies = iter(['{"a": 1}', '{"a": 2}'])

        def check(d):
            if d["a"] != 2:
                raise ValueError("must be 2")
        assert bk.hf_json([], validate=check, chat=lambda m, mo: next(replies)) == {"a": 2}


class FakeRun:
    """Stands in for subprocess.run for the claude and codex CLIs."""

    def __init__(self, replies):
        self.replies, self.calls = list(replies), []

    def __call__(self, cmd, **kw):
        self.calls.append((cmd, kw))
        r = self.replies.pop(0)
        if isinstance(r, Exception):
            raise r
        return r


def cli(result="", code=0, cost=0.01, is_error=False, err=""):
    return SimpleNamespace(returncode=code, stdout=json.dumps({"result": result, "total_cost_usd": cost, "is_error": is_error}), stderr=err)


class TestLlmJson:
    @pytest.fixture(autouse=True)
    def have_cli(self, monkeypatch):
        monkeypatch.setattr(bk.shutil, "which", lambda name, path=None: f"/bin/{name}")
        monkeypatch.setitem(bk.COST, "usd", 0.0)
        monkeypatch.setitem(bk.COST, "calls", 0)

    def test_unknown_engine(self):
        with pytest.raises(RuntimeError, match="unknown engine"):
            bk.llm_json("p", "s", engine="gpt")

    def test_missing_command(self, monkeypatch):
        monkeypatch.setattr(bk.shutil, "which", lambda name, path=None: None)
        with pytest.raises(RuntimeError, match="not found"):
            bk.llm_json("p", "s")

    def test_claude_success_records_cost_and_defaults_the_model(self, monkeypatch):
        run = FakeRun([cli('{"a": 1}')])
        monkeypatch.setattr(bk.subprocess, "run", run)
        assert bk.llm_json("p", "sys") == {"a": 1}
        cmd, kw = run.calls[0]
        assert cmd[:3] == ["/bin/claude", "-p", "--model"] and cmd[3] == "sonnet" and kw["input"] == "p" and bk.COST["calls"] == 1 and bk.COST["usd"] == 0.01

    def test_bad_reply_is_retried_with_feedback(self, monkeypatch):
        run = FakeRun([cli("no json"), cli('{"a": 1}')])
        monkeypatch.setattr(bk.subprocess, "run", run)
        assert bk.llm_json("p", "s") == {"a": 1}
        assert "rejected" in run.calls[1][1]["input"]

    def test_gives_up_after_the_retries(self, monkeypatch):
        monkeypatch.setattr(bk.subprocess, "run", FakeRun([cli("x")] * 3))
        with pytest.raises(RuntimeError, match="after 3 tries"):
            bk.llm_json("p", "s")

    def test_cli_failures_are_reported(self, monkeypatch):
        monkeypatch.setattr(bk.subprocess, "run", FakeRun([cli(code=2, err="boom"), cli(is_error=True, result="bad"), cli(code=1, err="again")]))
        with pytest.raises(RuntimeError, match="again"):
            bk.llm_json("p", "s")

    def test_validation_message_goes_back_to_the_model(self, monkeypatch):
        run = FakeRun([cli('{"a": 1}'), cli('{"a": 2}')])
        monkeypatch.setattr(bk.subprocess, "run", run)

        def check(d):
            if d["a"] != 2:
                raise ValueError("a must be 2")
        assert bk.llm_json("p", "s", validate=check) == {"a": 2}
        assert "a must be 2" in run.calls[1][1]["input"]

    def test_hf_missing_token_is_not_retried(self, monkeypatch):
        calls = []

        def chat(msgs, model):
            calls.append(1)
            raise RuntimeError("HF_TOKEN is not set")
        monkeypatch.setattr(bk, "hf_chat", chat)
        with pytest.raises(RuntimeError, match="HF_TOKEN"):
            bk.llm_json("p", "s", engine="hf")
        assert len(calls) == 1

    def test_local_engine_uses_the_local_chat(self, monkeypatch):
        monkeypatch.setattr(bk, "local_chat", lambda msgs, model: '{"x": 1}')
        assert bk.llm_json("p", "s", engine="local") == {"x": 1}

    def test_pictures_cannot_go_through_the_chat_engines(self, tmp_path):
        img = tmp_path / "a.jpg"
        img.write_bytes(b"j")
        with pytest.raises(RuntimeError, match="hf_json"):
            bk.llm_json("p", "s", engine="hf", image=str(img))

    def test_codex_reads_the_reply_file(self, monkeypatch):
        def run(cmd, **kw):
            from pathlib import Path
            Path(cmd[cmd.index("-o") + 1]).write_text('{"c": 3}')
            return SimpleNamespace(returncode=0, stdout="", stderr="")
        monkeypatch.setattr(bk.subprocess, "run", run)
        assert bk.llm_json("p", "s", engine="codex") == {"c": 3}

    def test_claude_gets_a_private_copy_of_the_picture(self, monkeypatch, tmp_path):
        img = tmp_path / "a.jpg"
        img.write_bytes(b"j")
        run = FakeRun([cli('{"a": 1}')])
        monkeypatch.setattr(bk.subprocess, "run", run)
        bk.llm_json("p", "s", image=str(img))
        cmd, kw = run.calls[0]
        assert "Read" in cmd and "picture.jpg" in kw["input"] and kw["cwd"] != str(tmp_path)


def test_env_drops_python_variables_and_oss_cad(monkeypatch):
    monkeypatch.setenv("PYTHONHOME", "/x")
    monkeypatch.setenv("PATH", "/a:/opt/oss-cad-suite/bin:/b")
    env = bk._env()
    assert "PYTHONHOME" not in env and "oss-cad-suite" not in env["PATH"] and env["PATH"].endswith("/a:/b")


def test_timeout_propagates(monkeypatch):
    monkeypatch.setattr(bk.shutil, "which", lambda name, path=None: "/bin/claude")
    monkeypatch.setattr(bk.subprocess, "run", FakeRun([subprocess.TimeoutExpired("claude", 1)]))
    with pytest.raises(subprocess.TimeoutExpired):
        bk.llm_json("p", "s")
