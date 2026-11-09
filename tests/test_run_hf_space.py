"""run_hf_space.py: how each Space is called, and a whole run against a stand-in for gradio_client."""
import sys
import types

import pytest

import hf_spaces
import run_hf_space as rh


@pytest.fixture()
def gradio(monkeypatch):
    mod = types.ModuleType("gradio_client")
    mod.handle_file = lambda p: ("file", p)
    calls = []

    class Client:
        results = []

        def __init__(self, space, verbose=False, token=None, **kw):
            calls.append(("init", space, token))

        def predict(self, api_name=None, **kw):
            calls.append(("predict", api_name, kw))
            r = Client.results.pop(0)
            if isinstance(r, Exception):
                raise r
            return r
    mod.Client = Client
    monkeypatch.setitem(sys.modules, "gradio_client", mod)
    mod.calls = calls
    return mod


class TestHelpers:
    def test_snap_and_num(self):
        assert rh.snap(1000, 32, 256, 2048) == 992 and rh.snap(10, 32, 256, 2048) == 256 and rh.snap(9999, 32, 256, 2048) == 2048
        assert rh.num({"a": " 5 "}, "a", 1, int) == 5 and rh.num({}, "a", 1.5) == 1.5 and rh.num({"a": ""}, "a", None) is None

    def test_as_path_accepts_strings_lists_and_dicts(self):
        assert rh.as_path("a.png") == "a.png" and rh.as_path(["a.png", "x"]) == "a.png" and rh.as_path({"video": {"path": "v.mp4"}}) == "v.mp4"
        with pytest.raises(ValueError):
            rh.as_path({"nothing": 1})

    def test_keyframe_folder(self, tmp_path, monkeypatch):
        monkeypatch.delenv("KEYFRAME_MODEL", raising=False)
        assert rh.keyframe_folder(tmp_path).name == "none_keyframes"
        (tmp_path / "images" / "a_keyframes").mkdir(parents=True)
        assert rh.keyframe_folder(tmp_path).name == "a_keyframes"
        monkeypatch.setenv("KEYFRAME_MODEL", "flux")
        assert rh.keyframe_folder(tmp_path).name == "flux_keyframes"


class TestBuildCall:
    ROW = {"prompt": "a lake", "seed": "5", "width": "1000", "height": "600", "steps": "8", "guidance": "2.5", "negative": " blur "}

    def test_flux(self):
        api, kw = rh.build_call("flux1_dev", hf_spaces.SPACES["flux1_dev"], self.ROW)
        assert api == "/infer" and kw["width"] == 992 and kw["height"] == 608 and kw["num_inference_steps"] == 8 and kw["seed"] == 5 and kw["guidance_scale"] == 2.5 and not kw["randomize_seed"]

    def test_defaults_fill_blank_boxes_and_a_missing_seed_is_random(self):
        _, kw = rh.build_call("flux1_schnell", hf_spaces.SPACES["flux1_schnell"], {"prompt": "x"})
        assert kw["width"] == 1024 and kw["num_inference_steps"] == 4 and "guidance_scale" not in kw and isinstance(kw["seed"], int)

    def test_sd35_and_klein(self):
        _, kw = rh.build_call("sd35_large", hf_spaces.SPACES["sd35_large"], self.ROW)
        assert kw["negative_prompt"] == "blur" and kw["guidance_scale"] == 2.5
        _, kw = rh.build_call("flux2_klein_4b", hf_spaces.SPACES["flux2_klein_4b"], self.ROW)
        assert kw["mode_choice"] == "Distilled (4 steps)" and kw["input_images"] == []

    def test_qwen_picks_the_nearest_aspect_ratio(self):
        _, kw = rh.build_call("qwen_image_21_uc", hf_spaces.SPACES["qwen_image_21_uc"], {"prompt": "x", "width": "1344", "height": "768", "steps": "99"})
        assert "16:9" in kw["aspect_ratio"] and kw["steps"] == 40

    def test_pika_needs_gradio_and_reads_the_keyframe(self, gradio):
        _, kw = rh.build_call("pika_h3_flex_i2v", hf_spaces.SPACES["pika_h3_flex_i2v"], {"prompt": "x", "_keyframe": "k.png", "aspect": "21:9"})
        assert kw["first_image"] == ("file", "k.png") and kw["aspect"] == "21:9" and kw["seconds"] == 5
        _, kw = rh.build_call("pika_h3_flex_i2v", hf_spaces.SPACES["pika_h3_flex_i2v"], {"prompt": "x", "_keyframe": "k.png", "aspect": "7:3"})
        assert kw["aspect"] == "16:9"

    def test_cogvideox_and_unknown_style(self):
        assert rh.build_call("cogvideox_5b", hf_spaces.SPACES["cogvideox_5b"], {"prompt": "x", "seed": "1"})[1]["seed_value"] == 1
        with pytest.raises(SystemExit, match="no call style"):
            rh.build_call("m", {"style": "nope", "defaults": {}, "api": "/x"}, {"prompt": "x"})

    def test_every_listed_space_can_be_called(self, gradio):
        for name, spec in hf_spaces.SPACES.items():
            row = {"prompt": "x", "_keyframe": "k.png"}
            api, kw = rh.build_call(name, spec, row)
            assert api.startswith("/") and kw["prompt"] == "x" if "prompt" in kw else True


@pytest.fixture()
def prompts(fake_root):
    d = fake_root / "projects" / "prompts" / "set1"
    d.mkdir()
    (d / "promptset.json").write_text("{}")
    (d / "all_images.csv").write_text("prompt,seed\none,1\ntwo,2\nthree,3\n")
    return d


class TestMain:
    def run(self, monkeypatch, *argv):
        monkeypatch.setattr(sys, "argv", ["run_hf_space.py", *argv])
        rh.main()

    def test_makes_pictures_skips_existing_and_stops_when_the_quota_ends(self, prompts, gradio, monkeypatch, capsys):
        from PIL import Image
        made = prompts.parent / "made.png"
        Image.new("RGB", (8, 8), "red").save(made)
        monkeypatch.setenv("PROJECT", "set1")
        monkeypatch.setenv("HF_TOKEN", "hf_secret")
        monkeypatch.delenv("SHOTS_CSV", raising=False)
        out = prompts / "images" / "flux1_schnell"
        out.mkdir(parents=True)
        (out / "image-0001.png").write_bytes(b"x")
        gradio.Client.results = [(str(made), 1), RuntimeError("ZeroGPU quota exceeded. Try again in 0:25:00")]
        self.run(monkeypatch, "image_flux1_schnell", "1", "3")
        text = capsys.readouterr().out
        assert "[1/3] already there" in text and "[2/3] ok" in text and "[3/3] FAILED" in text and "comes back in 0:25:00" in text and "hf_secret" not in text
        assert (out / "image-0002.png").is_file() and not (out / "image-0003.png").exists() and ("init", "black-forest-labs/FLUX.1-schnell", "hf_secret") in gradio.calls

    def test_all_failures_exit_one(self, prompts, gradio, monkeypatch):
        monkeypatch.setenv("PROJECT", "set1")
        monkeypatch.delenv("HF_TOKEN", raising=False)
        gradio.Client.results = [RuntimeError("boom")] * 3
        with pytest.raises(SystemExit) as e:
            self.run(monkeypatch, "flux1_schnell", "1", "3")
        assert e.value.code == 1

    def test_video_is_copied_and_chapters_get_their_own_folder(self, prompts, gradio, monkeypatch, tmp_path):
        monkeypatch.setenv("PROJECT", "set1")
        (prompts / "all_chapters.csv").write_text("prompt\none\n")
        monkeypatch.setenv("SHOTS_CSV", "all_chapters.csv")
        clip = tmp_path / "c.mp4"
        clip.write_bytes(b"video")
        gradio.Client.results = [{"video": str(clip)}]
        self.run(monkeypatch, "cogvideox_5b", "1", "1")
        assert (prompts / "videos" / "cogvideox_5b_chapters" / "shot-0001.mp4").read_bytes() == b"video"

    def test_a_pika_row_without_a_keyframe_fails_that_row(self, prompts, gradio, monkeypatch, capsys):
        monkeypatch.setenv("PROJECT", "set1")
        monkeypatch.setenv("SHOTS_CSV", "all_images.csv")
        monkeypatch.delenv("KEYFRAME_MODEL", raising=False)
        with pytest.raises(SystemExit):
            self.run(monkeypatch, "pika_h3_flex_i2v", "1", "1")
        assert "no keyframe" in capsys.readouterr().out

    def test_argument_errors(self, prompts, monkeypatch):
        with pytest.raises(SystemExit):
            self.run(monkeypatch, "flux1_schnell")
        with pytest.raises(SystemExit, match="no Hugging Face Space"):
            self.run(monkeypatch, "nomodel", "1", "2")
        monkeypatch.delenv("PROJECT", raising=False)
        with pytest.raises(SystemExit, match="set PROJECT"):
            self.run(monkeypatch, "flux1_schnell", "1", "2")
        monkeypatch.setenv("PROJECT", "ghostset")
        with pytest.raises(SystemExit, match="no such project"):
            self.run(monkeypatch, "flux1_schnell", "1", "2")
