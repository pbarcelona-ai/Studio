"""Vision and prompt-writing helpers in llm.py with the model calls stubbed."""
import csv

import pytest
from PIL import Image

from studio_app import llm
from studio_app.common import PlanError


@pytest.fixture
def stub(monkeypatch):
    calls = {"llm": [], "hf": []}
    answer = {"value": {}}

    def fake_llm(prompt, system, model=None, engine=None, validate=None, **kw):
        calls["llm"].append({"prompt": prompt, "model": model, "engine": engine, **kw})
        if validate:
            validate(answer["value"])
        return answer["value"]

    def fake_hf(messages, model, check, chat=None):
        calls["hf"].append({"messages": messages, "model": model, "chat": chat})
        check(answer["value"])
        return answer["value"]
    monkeypatch.setattr(llm, "llm_json", fake_llm)
    monkeypatch.setattr(llm, "hf_json", fake_hf)
    return calls, answer


@pytest.fixture
def picture(book):
    f = book / "images" / "flux" / "image-001.png"
    f.parent.mkdir(parents=True)
    Image.new("RGB", (64, 48), "red").save(f)
    return "demo/images/flux/image-001.png"


class TestResultFile:
    @pytest.mark.parametrize("name", ["", "demo", "../x/a.png", "Bad Slug/a.png", "demo/../../etc/passwd.png"])
    def test_bad_names(self, book, name):
        with pytest.raises(PlanError):
            llm.result_file(name)

    def test_wrong_type_or_missing(self, book, picture):
        (book / "notes.txt").write_text("x")
        with pytest.raises(PlanError, match="not found"):
            llm.result_file("demo/notes.txt")
        with pytest.raises(PlanError, match="not found"):
            llm.result_file("demo/images/flux/none.png")

    def test_finds_the_picture(self, book, picture):
        assert llm.result_file(picture).name == "image-001.png"


def test_image_data_url_is_a_small_jpeg(book, picture):
    url = llm.image_data_url(llm.result_file(picture), px=32)
    assert url.startswith("data:image/jpeg;base64,")


class TestVisionModel:
    def test_defaults(self):
        assert llm.vision_model({}) == "" and llm.vision_model({"engine": "hf"}) == llm.HF_VISION_MODELS[0]
        assert llm.vision_model({"engine": "hf", "claude_model": "my/model"}) == "my/model"

    def test_unsafe_name(self):
        with pytest.raises(PlanError, match="model name"):
            llm.vision_model({"claude_model": "a b;rm"})


class TestVisionJson:
    def test_unknown_engine(self, book, picture):
        with pytest.raises(PlanError, match="unknown engine"):
            llm.vision_json({"engine": "x", "file": picture}, "s", "t", lambda d: None)

    def test_claude_gets_a_private_jpeg_that_is_removed(self, book, picture, stub):
        calls, answer = stub
        answer["value"] = {"ok": 1}
        assert llm.vision_json({"file": picture}, "s", "t", lambda d: None) == {"ok": 1}
        jpeg = calls["llm"][0]["image"]
        assert jpeg.endswith(".jpg") and not __import__("os").path.exists(jpeg)

    def test_hf_and_local_send_the_picture_inline(self, book, picture, stub):
        calls, answer = stub
        answer["value"] = {"ok": 1}
        llm.vision_json({"file": picture, "engine": "hf"}, "s", "t", lambda d: None)
        llm.vision_json({"file": picture, "engine": "local"}, "s", "t", lambda d: None)
        assert calls["hf"][0]["chat"] is None and calls["hf"][1]["chat"] is llm.local_chat
        assert calls["hf"][0]["messages"][1]["content"][1]["image_url"]["url"].startswith("data:image/jpeg")


class TestDescribeAndReview:
    def test_describe_video_prompt(self, book, picture, stub):
        _, answer = stub
        answer["value"] = {"prompt": "  A red field slowly pans as wind moves the grass.  "}
        out = llm.describe_image({"file": picture, "kind": "video", "note": "slow"})
        assert out == {"prompt": "A red field slowly pans as wind moves the grass."}

    def test_describe_rejects_short_prompts(self, book, picture, stub):
        _, answer = stub
        answer["value"] = {"prompt": "short"}
        with pytest.raises(ValueError):
            llm.describe_image({"file": picture})

    def test_review_needs_a_prompt(self, book, picture):
        with pytest.raises(PlanError, match="no prompt"):
            llm.review_result({"file": picture, "prompt": " "})

    def test_review_normalises_the_score(self, book, picture, stub):
        _, answer = stub
        answer["value"] = {"score": "7", "summary": " Good. ", "problems": ["a", "b", "c", "d"]}
        assert llm.review_result({"file": picture, "prompt": "a fox"}) == {"score": 7, "summary": "Good.", "problems": ["a", "b", "c"]}

    @pytest.mark.parametrize("bad", [{"score": 11, "summary": "x"}, {"score": 5}, {"score": "high", "summary": "x"}])
    def test_review_rejects_bad_replies(self, book, picture, stub, bad):
        stub[1]["value"] = bad
        with pytest.raises(ValueError):
            llm.review_result({"file": picture, "prompt": "a fox"})


class TestEnhance:
    base = {"project": "demo", "row": 1, "original_prompt": "a woman walks in a garden", "instruction": "make it night"}

    @pytest.mark.parametrize("patch,msg", [({"project": "../x"}, "bad project"), ({"original_prompt": ""}, "no original"), ({"instruction": " "}, "no enhancement"),
                                           ({"project": "nothere"}, "not found")])
    def test_refused(self, book, stub, patch, msg):
        with pytest.raises(PlanError, match=msg):
            llm.enhance_prompt({**self.base, **patch})

    def test_preview_changes_nothing(self, book, stub):
        stub[1]["value"] = {"updated_prompt": "a woman walks in a garden at night", "feedback": "ok"}
        before = (book / "all_shots.csv").read_text()
        out = llm.enhance_prompt({**self.base, "preview_only": True})
        assert out["updated_prompt"].startswith("a woman walks in a garden at night") and llm.NEG_TAIL in out["updated_prompt"]
        assert (book / "all_shots.csv").read_text() == before

    def test_global_positives_are_kept(self, book, stub):
        from studio_app.projects import save_global_params
        save_global_params("demo", "35mm film", "")
        stub[1]["value"] = {"updated_prompt": "a woman walks in a garden at night"}
        assert "35mm film" in llm.enhance_prompt({**self.base, "preview_only": True})["updated_prompt"]

    def test_apply_saves_what_the_preview_showed(self, book, stub):
        stub[1]["value"] = {"updated_prompt": "a woman walks in a garden at night"}
        out = llm.enhance_prompt(self.base)
        assert out["feedback"] == "Prompt updated and saved to CSV"
        rows = list(csv.DictReader(open(book / "all_shots.csv")))
        assert rows[0]["prompt"] == out["updated_prompt"] and rows[1]["prompt"] == "a mountain at dawn"

    def test_reply_without_prompt_is_invalid(self, book, stub):
        stub[1]["value"] = {"updated_prompt": "short"}
        with pytest.raises(ValueError):
            llm.enhance_prompt(self.base)


class TestGallery:
    def test_empty_for_unknown_project(self, fake_root):
        assert llm.gallery("nothere") == []

    def test_lists_results_with_their_prompts(self, book):
        v = book / "videos" / "ltx_video" / "shot-0002.mp4"
        v.parent.mkdir(parents=True)
        v.write_bytes(b"v")
        (book / "films").mkdir()
        (book / "films" / "film.mp4").write_bytes(b"f")
        items = llm.gallery("demo")
        by_kind = {i["kind"]: i for i in items}
        assert by_kind["video"]["prompt"] == "a mountain at dawn" and by_kind["video"]["row"] == 2 and by_kind["film"]["name"] == "film.mp4"
