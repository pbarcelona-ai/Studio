"""Size checks and row helpers in single_prompts, plus llm.local_llm_status / clip_prompt with the network and hardware faked."""
import json
import platform

import pytest

from conftest import write_csv
from studio_app import llm, single_prompts as sp
from studio_app.common import PlanError


class TestSnap:
    @pytest.mark.parametrize("value,mult,lo,hi,want", [(500, 16, 256, 1024, 496), (10, 16, 256, 1024, 256), (5000, 16, 256, 1024, 1024), (33, 8, 8, 100, 32)])
    def test_snap(self, value, mult, lo, hi, want):
        assert sp.snap(value, mult, lo, hi) == want


class TestT4Checks:
    def test_other_gpus_skip_the_check(self):
        sp.wan_t4_check("L4", 4096, 4096, 400)
        sp.image_t4_check("A100", 4096, 4096, "sd35_large")

    def test_wan_default_size_fits_a_t4(self):
        sp.wan_t4_check("T4", 512, 288, 33)

    def test_wan_too_big_is_refused_with_a_suggestion(self):
        with pytest.raises(PlanError, match="attention matrix.*512x288 with 33 frames"):
            sp.wan_t4_check("NvidiaTeslaT4", 1280, 720, 121)

    def test_14b_suggests_a_smaller_size(self):
        with pytest.raises(PlanError, match="448x256 with 25 frames"):
            sp.wan_t4_check("T4", 1280, 720, 121, "wan22_t2v_a14b")

    def test_image_model_without_attention_limit_passes(self):
        sp.image_t4_check("T4", 4096, 4096, "flux2_klein_4b")

    def test_sd35_large_big_is_refused(self):
        with pytest.raises(PlanError, match="sd35_large at 2048x2048"):
            sp.image_t4_check("T4", 2048, 2048, "sd35_large")


class TestPromptSetSlug:
    def test_bad_name(self, fake_root):
        with pytest.raises(PlanError, match="name the prompt set"):
            sp.prompt_set_slug({"set": "A b"}, True)

    def test_good_name_is_lower_cased(self, fake_root):
        assert sp.prompt_set_slug({"set": " My_Set "}, True) == "my_set"

    def test_a_book_is_not_a_prompt_set(self, book):
        with pytest.raises(PlanError):
            sp.prompt_set_slug({"set": "demo"}, True)


class TestPromptRows:
    def test_needs_a_prompt(self, fake_root):
        with pytest.raises(PlanError, match="at least one prompt"):
            sp.prompt_rows({"prompts": "  \n "}, "s", "image", "flux2_klein_4b", 1)

    def test_limits(self, fake_root):
        with pytest.raises(PlanError, match="up to 100"):
            sp.prompt_rows({"prompts": "\n".join(["x"] * 101)}, "s", "image", "flux2_klein_4b", 1)
        with pytest.raises(PlanError, match="up to 100"):
            sp.prompt_rows({"prompts": "x" * 2001}, "s", "image", "flux2_klein_4b", 1)

    def test_variations_multiply_rows(self, fake_root):
        rows = sp.prompt_rows({"prompts": "a cat\na dog", "opts": {"variations": 3}}, "s", "image", "flux2_klein_4b", 1)
        assert len(rows) == 6
        assert any("cat" in r["prompt"] for r in rows) and any("dog" in r["prompt"] for r in rows)


def test_append_rows_keeps_old_rows_and_extra_columns(tmp_path):
    p = tmp_path / "p.csv"
    write_csv(p, [{"id": "1", "prompt": "a", "note": "keep"}])
    sp.append_rows(p, ["id", "prompt"], [{"id": "2", "prompt": "b"}])
    text = p.read_text().splitlines()
    assert text[0].split(",")[:2] == ["id", "prompt"] and "note" in text[0]
    assert len(text) == 3 and "keep" in text[1]


class TestLocalLlmStatus:
    @pytest.fixture(autouse=True)
    def fresh(self, monkeypatch):
        monkeypatch.setitem(llm._LOCAL_CACHE, "value", None)
        monkeypatch.setenv("STUDIO_LOCAL_LLM", "1")           # skip the hardware checks; the server answer is faked below

    def serve(self, monkeypatch, body=None, exc=None):
        import urllib.request

        class Resp:
            def __enter__(self): return self
            def __exit__(self, *a): return False
            def read(self): return json.dumps(body).encode()

        def fake(url, timeout=0):
            if exc:
                raise exc
            return Resp()
        monkeypatch.setattr(urllib.request, "urlopen", fake)

    def test_ready_when_a_server_lists_models(self, monkeypatch):
        self.serve(monkeypatch, {"data": [{"id": "qwen"}, {"id": "llama"}]})
        v = llm.local_llm_status()
        assert v["ready"] and v["models"] == ["qwen", "llama"] and v["reason"] == ""

    def test_server_without_models(self, monkeypatch):
        self.serve(monkeypatch, {"data": []})
        v = llm.local_llm_status()
        assert not v["ready"] and "no models yet" in v["reason"]

    def test_no_server(self, monkeypatch):
        self.serve(monkeypatch, exc=OSError("refused"))
        v = llm.local_llm_status()
        assert not v["ready"] and "no local model server" in v["reason"]

    def test_result_is_cached_until_forced(self, monkeypatch):
        self.serve(monkeypatch, {"data": [{"id": "a"}]})
        first = llm.local_llm_status()
        self.serve(monkeypatch, exc=OSError("gone"))
        assert llm.local_llm_status() is first
        assert not llm.local_llm_status(force=True)["ready"]

    def test_small_memory_is_reported(self, monkeypatch):
        monkeypatch.delenv("STUDIO_LOCAL_LLM")
        monkeypatch.setattr(platform, "system", lambda: "Linux")
        monkeypatch.setattr(llm.os, "sysconf", lambda name: 4096 if name == "SC_PAGE_SIZE" else 2 * 2**30 // 4096)
        monkeypatch.setattr(llm.shutil, "which", lambda n: None)
        v = llm.local_llm_status(force=True)
        assert not v["ready"] and "2 GB of memory" in v["reason"] and "no NVIDIA GPU" in v["reason"]


class TestClipPrompt:
    def test_bad_name(self, fake_root):
        with pytest.raises(PlanError, match="bad project name"):
            llm.clip_prompt("../x", 1)

    def test_missing_project(self, fake_root):
        with pytest.raises(PlanError, match="project not found"):
            llm.clip_prompt("nothere", 1)

    def test_reads_the_row(self, book):
        got = llm.clip_prompt("demo", 1)
        assert isinstance(got["prompt"], str)

    def test_out_of_range_is_empty(self, book):
        assert llm.clip_prompt("demo", 999) == {"prompt": ""}
