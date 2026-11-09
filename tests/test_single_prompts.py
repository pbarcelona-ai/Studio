"""prompt_plan (commit and preview), size snapping, reference pictures, face-check step and idea expansion."""
import csv
import json

import pytest
from PIL import Image

from studio_app import single_prompts as sp
from studio_app.common import PlanError

KAGGLE = {"service": "kaggle", "gpu": "NvidiaTeslaT4", "kaggle_user": "pat"}


def opt(**kw):
    return {"set": "myset", "kind": "image", "model": "flux2_klein_4b", "prompts": "a cat\na dog", **KAGGLE, **kw}


def rows_of(root, name="all_images.csv"):
    return list(csv.DictReader(open(root / "projects" / "prompts" / "myset" / name)))


class TestValidation:
    @pytest.mark.parametrize("patch,msg", [
        ({"kind": "audio"}, "choose video or image"), ({"model": "nope"}, "unknown model"), ({"service": "mars"}, "choose where"),
        ({"gpu": "NoGpu"}, "is not an option"), ({"kaggle_user": "x"}, "Kaggle username"), ({"set": "A b"}, "name the prompt set"),
        ({"prompts": ""}, "at least one prompt"), ({"look": "nonsense"}, "unknown look"),
        ({"kind": "video", "model": "ltx_video_i2v"}, "animates a book"),
    ])
    def test_refused(self, fake_root, patch, msg):
        with pytest.raises(PlanError, match=msg):
            sp.prompt_plan(opt(**patch), False)

    def test_preview_writes_nothing(self, fake_root):
        steps = sp.prompt_plan(opt(), False)
        assert steps and not (fake_root / "projects" / "prompts" / "myset").exists()


class TestCommit:
    def test_rows_are_appended_and_numbered(self, fake_root):
        steps = sp.prompt_plan(opt(), True)
        assert [r["prompt"] for r in rows_of(fake_root)] == ["a cat", "a dog"] and [r["shot"] for r in rows_of(fake_root)] == ["1", "2"]
        assert json.loads((fake_root / "projects" / "prompts" / "myset" / "promptset.json").read_text()) == {"type": "prompts"}
        assert len(steps) >= 1 and "rows 1-2" in steps[0]["label"]
        sp.prompt_plan(opt(prompts="a bird"), True)
        assert [r["shot"] for r in rows_of(fake_root)] == ["1", "2", "3"]          # a second run adds to the set

    def test_overwrite_starts_again(self, fake_root):
        sp.prompt_plan(opt(), True)
        sp.prompt_plan(opt(prompts="only", opts={"overwrite": True}), True)
        assert [r["prompt"] for r in rows_of(fake_root)] == ["only"]

    def test_batches_make_several_steps(self, fake_root):
        steps = sp.prompt_plan(opt(prompts="\n".join(f"prompt number {i}" for i in range(6)), batch=2), True)
        assert len(steps) == 3

    def test_video_rows_have_frames_snapped(self, fake_root):
        sp.prompt_plan(opt(kind="video", model="ltx_video", opts={"width": 700, "height": 400, "frames": 50}), True)
        r = rows_of(fake_root, "all_shots.csv")[0]
        assert (int(r["width"]) % 32, int(r["height"]) % 32, (int(r["frames"]) - 1) % 8) == (0, 0, 0)

    def test_variations_and_seed(self, fake_root):
        sp.prompt_plan(opt(prompts="a cat", opts={"variations": 3, "seed": 10}), True)
        assert [r["seed"] for r in rows_of(fake_root)] == ["10", "11", "12"]

    def test_look_is_applied(self, fake_root):
        from studio_app.single_prompts import model_advisor
        look = next(iter(model_advisor.LOOKS))
        sp.prompt_plan(opt(look=look), True)
        assert rows_of(fake_root)[0]["prompt"] != "a cat"


class TestT4Limits:
    def test_wan_too_big_for_a_t4_is_refused_before_anything_is_written(self, fake_root):
        with pytest.raises(PlanError, match="attention matrix"):
            sp.prompt_plan(opt(kind="video", model="wan", opts={"width": 1280, "height": 720, "frames": 121}), True)
        assert not (fake_root / "projects" / "prompts" / "myset").exists()


class TestReference:
    def test_none_without_a_reference(self, fake_root):
        assert sp.character_reference(opt(), "flux2_klein_4b", "kaggle") is None

    def test_bad_series(self, fake_root):
        model = next(iter(sp.REF_IMAGE_MODELS))
        with pytest.raises(PlanError, match="bad series"):
            sp.character_reference({"opts": {"reference": {"series": "../x", "name": "eve"}}}, model, "kaggle")

    def test_small_picture_is_shrunk(self, tmp_path):
        src, dst = tmp_path / "a.png", tmp_path / "b.png"
        Image.new("RGB", (1000, 800), "blue").save(src)
        sp.save_small_picture(src, dst, side=100)
        assert max(Image.open(dst).size) == 100

    def test_unreadable_picture_is_copied(self, tmp_path):
        src, dst = tmp_path / "a.png", tmp_path / "b.png"
        src.write_bytes(b"not an image")
        sp.save_small_picture(src, dst)
        assert dst.read_bytes() == b"not an image"


class TestOpenFolder:
    def test_refuses_bad_input(self, fake_root):
        with pytest.raises(PlanError):
            sp.open_folder("../x", "eve")
        with pytest.raises(PlanError):
            sp.open_folder("series", " ")

    def test_no_file_manager(self, fake_root, monkeypatch):
        monkeypatch.setattr(sp.shutil, "which", lambda n: None)
        with pytest.raises(PlanError, match="cannot open folders"):
            sp.open_folder("series", "eve")

    def test_opens_and_returns_a_relative_path(self, fake_root, monkeypatch):
        ran = []
        monkeypatch.setattr(sp.shutil, "which", lambda n: "/usr/bin/" + n)
        monkeypatch.setattr(sp.subprocess, "run", lambda cmd, **kw: ran.append(cmd))
        out = sp.open_folder("series", "eve")
        assert ran and not out.startswith("/")


class TestFaceCheck:
    def test_needs_a_book_and_series(self, book):
        with pytest.raises(PlanError, match="pick a book"):
            sp.face_check_step({"project": "nothere", "series": "s"})
        with pytest.raises(PlanError, match="character series"):
            sp.face_check_step({"project": "demo", "series": "../x"})

    def test_step(self, book):
        s = sp.face_check_step({"project": "demo", "series": "heroes", "start": 2, "end": 4})
        assert s["argv"][s["argv"].index("--start") + 1] == "2" and s["argv"][s["argv"].index("--end") + 1] == "4"
        assert "face_check.py" in s["argv"] and s["label"] == "Check faces, shots 2-4"


class TestExpandIdea:
    @pytest.fixture
    def llm(self, monkeypatch):
        seen = {}

        def fake(prompt, system, model=None, engine=None, validate=None):
            seen["prompt"] = prompt
            out = {"prompts": [f"a long vivid prompt number {i} about the idea" for i in range(seen.get("n", 3))]}
            validate(out)
            return out
        monkeypatch.setattr(sp, "llm_json", fake)
        return seen

    @pytest.mark.parametrize("patch,msg", [({"kind": "x"}, "choose video or image"), ({"idea": ""}, "short idea"), ({"idea": "x" * 1001}, "short idea")])
    def test_refused(self, fake_root, llm, patch, msg):
        with pytest.raises(PlanError, match=msg):
            sp.expand_idea({"kind": "video", "idea": "rain", **patch})

    def test_returns_the_requested_number(self, fake_root, llm):
        out = sp.expand_idea({"kind": "video", "idea": "rain on a city", "count": 3})
        assert len(out) == 3 and all(isinstance(x, str) for x in out)
        assert "rain on a city" in llm["prompt"]

    def test_global_parameters_reach_the_prompt(self, book, llm):
        from studio_app.projects import save_global_params
        save_global_params("demo", "35mm film", "blurry")
        out = sp.expand_idea({"kind": "image", "idea": "rain", "project": "demo", "count": 3})
        assert "35mm film" in llm["prompt"] and all("35mm film" in p for p in out)


class TestSizeRules:
    """prompt_rows snaps width, height and length to what each model accepts."""
    O = {"width": 777, "height": 333, "frames": 50, "steps": 20, "guidance": 4, "negative": "ugly", "seed": 5}

    def rows(self, kind, model, **o):
        return sp.prompt_rows({"prompts": "a\nb", "opts": {**self.O, **o}}, "myset", kind, model, 1)

    @pytest.mark.parametrize("model,w,h,frames", [("ltx_video", 768, 320, 49), ("wan", 784, 336, 49), ("wan22_ti2v_5b", 768, 320, 49), ("hunyuan_video", 784, 336, 49)])
    def test_video_models(self, model, w, h, frames):
        r = self.rows("video", model)[0]
        assert (r["width"], r["height"], r["frames"]) == (w, h, frames) and r["steps"] == 20 and r["seed"] == 5

    def test_hunyuan_has_no_negative_and_cogvideox_has_fixed_sizes(self):
        assert self.rows("video", "hunyuan_video")[0]["negative"] == ""
        r = self.rows("video", "cogvideox")[0]
        assert (r["width"], r["height"], r["frames"]) == ("", "", "")

    def test_images(self):
        r = self.rows("image", "flux2_klein_4b")[0]
        assert (r["width"], r["height"]) == (784, 336) and r["negative"] == "ugly"
        assert self.rows("image", "tpu_flux_jax")[0]["negative"] == ""
        mage = self.rows("image", "tpu_mage_flow")[0]
        assert mage["width"] == mage["height"] == 768 and mage["steps"] == "" and mage["guidance"] == ""

    def test_variations_get_consecutive_seeds_and_rows(self):
        rs = self.rows("image", "flux2_klein_4b", variations=3)
        assert [r["shot"] for r in rs] == [1, 2, 3, 4, 5, 6] and [r["seed"] for r in rs[:3]] == [5, 6, 7] and rs[3]["prompt"] == "b"

    def test_blank_boxes_stay_blank(self):
        r = sp.prompt_rows({"prompts": "a", "opts": {}}, "myset", "image", "flux2_klein_4b", 1)[0]
        assert (r["width"], r["height"], r["steps"], r["guidance"], r["seed"]) == ("", "", "", "", "")

    @pytest.mark.parametrize("prompts,msg", [("", "type at least one prompt"), ("\n".join(["x"] * 101), "up to 100 prompts"), ("y" * 2001, "up to 100 prompts")])
    def test_prompt_limits(self, prompts, msg):
        with pytest.raises(PlanError, match=msg):
            sp.prompt_rows({"prompts": prompts}, "myset", "image", "flux2_klein_4b", 1)


class TestPlanRefusals:
    @pytest.mark.parametrize("change,msg", [
        ({"kind": "film"}, "choose video or image"), ({"model": "nope"}, "unknown model"), ({"model": "ltx_video_i2v", "kind": "video"}, "animates a book's keyframes"),
        ({"service": "azure"}, "choose where the models run"), ({"gpu": "Quantum"}, "is not an option for kaggle"), ({"kaggle_user": "x"}, "Kaggle username"),
    ])
    def test_refused(self, fake_root, change, msg):
        with pytest.raises(PlanError, match=msg):
            sp.prompt_plan(opt(**change), False)

    def test_a_blocked_gpu_is_explained(self, fake_root, monkeypatch):
        monkeypatch.setattr(sp, "gpu_blocker", lambda service, gpu: "no suitable GPU")
        with pytest.raises(PlanError, match="no suitable GPU"):
            sp.prompt_plan(opt(), False)

    def test_a_book_cannot_be_used_as_a_prompt_set(self, book):
        with pytest.raises(PlanError, match="is a book"):
            sp.prompt_plan(opt(set="demo"), False)

    def test_a_bad_series_is_refused(self, fake_root):
        with pytest.raises(PlanError, match="bad series name"):
            sp.character_reference(opt(opts={"reference": {"series": "Bad Name", "name": "Eve"}}), "flux2_klein_4b", "kaggle")
