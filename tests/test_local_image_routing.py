"""Tests for Step 10/17 local-first image routing (ComfyUI -> sd-cli -> Gemini) and placeholder cache protection."""
from __future__ import annotations

from pathlib import Path

from local_runners.asset_cache import AssetCache, compute_cache_key
from local_runners.sd_cli_runner import SdCliRunner
from studio_app import routes_post as rp


def test_sd_cli_ready_models_requires_auxiliary_files(tmp_path):
    runner = SdCliRunner(bin_dir=tmp_path / "bin", models_dir=tmp_path / "models")
    (tmp_path / "models").mkdir()
    assert runner.ready_models() == []
    # Partial z-image-turbo without llm/vae is not ready
    (tmp_path / "models" / "z_image_turbo-Q4_K.gguf").write_bytes(b"stub")
    assert runner.ready_models() == []
    # Complete z-image-turbo is ready and ranked ahead of sd1
    (tmp_path / "models" / "Qwen3-4B-Instruct-2507-UD-Q4_K_XL.gguf").write_bytes(b"stub")
    (tmp_path / "models" / "ae.safetensors").write_bytes(b"stub")
    (tmp_path / "models" / "DreamShaper_8_pruned.safetensors").write_bytes(b"stub")
    assert runner.ready_models() == ["z-image-turbo", "dreamshaper-8"]


def test_placeholder_is_never_cached_and_stale_placeholder_cache_is_ignored(tmp_path, monkeypatch):
    cache = AssetCache(cache_dir=tmp_path / "cache")
    monkeypatch.setenv("STUDIO_ASSET_CACHE", "1")
    monkeypatch.setattr("local_runners.asset_cache.get_default_asset_cache", lambda: cache)
    monkeypatch.setattr("run_gemini_omni.get_gemini_api_key", lambda: "")
    monkeypatch.setattr(rp, "_try_comfyui_image", lambda prompt, out_png, aspect_ratio="16:9", **kw: "")
    monkeypatch.setattr(rp, "_try_sd_cli_image", lambda prompt, out_png, aspect_ratio="16:9", **kw: "")

    out1 = tmp_path / "placeholder.png"
    model1 = rp._render_keyframe_local_or_gemini("portrait of BITS", out1, aspect_ratio="1:1", engine="auto")
    assert model1 == "local_storyboard_synth" and out1.is_file()

    # Placeholder must NOT have been written to AssetCache
    ckey = compute_cache_key(
        "v2_image_render",
        "1.0",
        {"prompt": "portrait of BITS", "aspect_ratio": "1:1", "engine": "auto", "refs": []},
        output_path=str(out1),
    )
    assert cache.try_restore(ckey, tmp_path / "probe.png") is None

    # Even if an old placeholder entry already exists in cache, it must be ignored once a real local runner is available
    cache.store(ckey, out1, tool_name="v2_image_render", model="local_storyboard_synth")

    def fake_sd(prompt: str, out_png: Path, aspect_ratio: str = "16:9", **kw) -> str:
        out_png.write_bytes(b"\x89PNG\r\n\x1a\n" + b"real-image" * 30)
        return "sd_cli:z-image-turbo"

    monkeypatch.setattr(rp, "_try_sd_cli_image", fake_sd)
    out2 = tmp_path / "real.png"
    model2 = rp._render_keyframe_local_or_gemini("portrait of BITS", out2, aspect_ratio="1:1", engine="auto")
    assert model2 == "sd_cli:z-image-turbo"
    assert b"real-image" in out2.read_bytes()


def test_auto_mode_prefers_local_over_gemini_and_falls_back_comfyui_to_sd_cli(tmp_path, monkeypatch):
    monkeypatch.setenv("STUDIO_ASSET_CACHE", "0")
    monkeypatch.setattr("run_gemini_omni.get_gemini_api_key", lambda: "AIzaFakeKey1234567890")
    calls: list[str] = []

    def fake_comfy(prompt: str, out_png: Path, aspect_ratio: str = "16:9", **kw) -> str:
        calls.append("comfyui")
        return ""

    def fake_sd(prompt: str, out_png: Path, aspect_ratio: str = "16:9", **kw) -> str:
        calls.append("sd_cli")
        out_png.write_bytes(b"\x89PNG\r\n\x1a\n" + b"sd" * 80)
        return "sd_cli:z-image-turbo"

    def fail_gemini(*args, **kwargs) -> str:
        raise AssertionError("Gemini should not be called when local succeeds")

    monkeypatch.setattr(rp, "_try_comfyui_image", fake_comfy)
    monkeypatch.setattr(rp, "_try_sd_cli_image", fake_sd)
    monkeypatch.setattr(rp, "_render_keyframe_gemini", fail_gemini)

    out = tmp_path / "char.png"
    used = rp._render_keyframe_local_or_gemini("BITS portrait", out, aspect_ratio="1:1", engine="auto")
    assert used == "sd_cli:z-image-turbo"
    assert calls == ["comfyui", "sd_cli"]


def test_sd_cli_ready_models_ref_support_requires_flux2_weights(tmp_path):
    runner = SdCliRunner(bin_dir=tmp_path / "bin", models_dir=tmp_path / "models")
    mdir = tmp_path / "models"
    mdir.mkdir()
    # Only z-image-turbo present -> no ref-capable model ready
    (mdir / "z_image_turbo-Q4_K.gguf").write_bytes(b"stub")
    (mdir / "Qwen3-4B-Instruct-2507-UD-Q4_K_XL.gguf").write_bytes(b"stub")
    (mdir / "ae.safetensors").write_bytes(b"stub")
    assert runner.ready_models(require_ref_support=True) == []
    # Add FLUX.2-klein-4B + FLUX.2 VAE -> ref-capable model is ready
    (mdir / "flux-2-klein-4b-Q8_0.gguf").write_bytes(b"stub")
    (mdir / "flux2_ae.safetensors").write_bytes(b"stub")
    assert runner.ready_models(require_ref_support=True) == ["flux2-klein-4b"]


def test_try_sd_cli_image_selects_ref_model_and_honors_require_ref(tmp_path, monkeypatch):
    import local_runners.sd_cli_runner as sd_mod

    front = tmp_path / "bits_front.png"
    front.write_bytes(b"\x89PNG\r\n\x1a\n" + b"front-ref" * 30)
    captured: list[dict] = []

    class FakeRunner:
        def __init__(self, has_ref_model: bool) -> None:
            self._has_ref = has_ref_model

        def is_installed(self) -> bool:
            return True

        def ready_models(self, *, require_ref_support: bool = False) -> list[str]:
            if require_ref_support:
                return ["flux2-klein-4b"] if self._has_ref else []
            return ["z-image-turbo", "flux2-klein-4b"] if self._has_ref else ["z-image-turbo"]

        def run(self, spec: dict) -> dict:
            captured.append(spec)
            Path(spec["output_path"]).write_bytes(b"\x89PNG\r\n\x1a\n" + b"out" * 60)
            return {"ok": True, "model": spec["model"]}

    # When no ref-capable model exists and require_ref=True, returns "" instead of ignoring the ref
    monkeypatch.setattr(sd_mod, "SdCliRunner", lambda: FakeRunner(has_ref_model=False))
    out_missing = tmp_path / "missing_ref.png"
    assert rp._try_sd_cli_image("rotate", out_missing, "1:1", ref_images=[front], require_ref=True) == ""
    assert not captured

    # When flux2-klein-4b is ready, it is automatically selected and receives ref_images
    monkeypatch.setattr(sd_mod, "SdCliRunner", lambda: FakeRunner(has_ref_model=True))
    out_ok = tmp_path / "bits_three_quarter.png"
    used = rp._try_sd_cli_image("rotate", out_ok, "1:1", ref_images=[front], require_ref=True)
    assert used == "sd_cli:flux2-klein-4b"
    assert len(captured) == 1
    assert captured[0]["model"] == "flux2-klein-4b"
    assert captured[0]["ref_images"] == [str(front)]


def test_turnaround_three_quarter_and_profile_require_front_reference(tmp_path, monkeypatch):
    from types import SimpleNamespace
    import pytest

    proj_dir = tmp_path / "demo_book"
    (proj_dir / "assets" / "turnarounds").mkdir(parents=True)
    monkeypatch.setattr(rp, "pdir", lambda slug, kind="book": proj_dir)

    # Without front image, both three_quarter and profile must fail clearly
    for view in ("three_quarter", "profile"):
        req = SimpleNamespace(body={"project": "demo_book", "character": "BITS", "view": view, "desc": "rag doll"})
        with pytest.raises(rp.PlanError, match="Front View"):
            rp._v2_turnaround_render(req)  # type: ignore[arg-type]

    # Once Front View exists, both three_quarter and profile pass it as ref_images with require_ref=True
    front = proj_dir / "assets" / "turnarounds" / "bits_front.png"
    front.write_bytes(b"\x89PNG\r\n\x1a\n" + b"front" * 50)
    seen: list[dict] = []

    def fake_render(prompt, out_png, aspect_ratio="16:9", ref_images=None, engine="auto", **kw):
        seen.append({"prompt": prompt, "out_png": out_png, "ref_images": list(ref_images or []), **kw})
        out_png.write_bytes(b"\x89PNG\r\n\x1a\n" + b"rotated" * 50)
        return "sd_cli:flux2-klein-4b"

    monkeypatch.setattr(rp, "_render_keyframe_local_or_gemini", fake_render)
    for view in ("three_quarter", "profile"):
        req = SimpleNamespace(body={"project": "demo_book", "character": "BITS", "view": view, "desc": "rag doll"})
        res = rp._v2_turnaround_render(req)  # type: ignore[arg-type]
        assert res["status"] == "ok"
        assert res["refs_used"] == 1
        assert res["model"] == "sd_cli:flux2-klein-4b"

    assert len(seen) == 2
    assert all(call["ref_images"] == [front] and call["require_ref"] is True for call in seen)


def test_cache_invalidates_when_front_reference_image_changes(tmp_path, monkeypatch):
    cache = AssetCache(cache_dir=tmp_path / "cache")
    monkeypatch.setenv("STUDIO_ASSET_CACHE", "1")
    monkeypatch.setattr("local_runners.asset_cache.get_default_asset_cache", lambda: cache)
    monkeypatch.setattr("run_gemini_omni.get_gemini_api_key", lambda: "")
    monkeypatch.setattr(rp, "_try_comfyui_image", lambda *a, **kw: "")

    front = tmp_path / "front.png"
    front.write_bytes(b"\x89PNG\r\n\x1a\n" + b"version-A" * 40)
    calls = {"n": 0}

    def fake_sd(prompt, out_png, aspect_ratio="1:1", **kw):
        calls["n"] += 1
        out_png.write_bytes(b"\x89PNG\r\n\x1a\n" + f"render-{calls['n']}".encode() * 30)
        return "sd_cli:flux2-klein-4b"

    monkeypatch.setattr(rp, "_try_sd_cli_image", fake_sd)
    out = tmp_path / "three_quarter.png"
    m1 = rp._render_keyframe_local_or_gemini("rotate bits", out, "1:1", ref_images=[front], require_ref=True)
    assert m1 == "sd_cli:flux2-klein-4b" and calls["n"] == 1

    # Same front image -> cache hit
    m2 = rp._render_keyframe_local_or_gemini("rotate bits", out, "1:1", ref_images=[front], require_ref=True)
    assert m2.startswith("cache:") and calls["n"] == 1

    # Front image updated -> cache MUST miss and re-render from new front reference
    front.write_bytes(b"\x89PNG\r\n\x1a\n" + b"version-B" * 40)
    m3 = rp._render_keyframe_local_or_gemini("rotate bits", out, "1:1", ref_images=[front], require_ref=True)
    assert m3 == "sd_cli:flux2-klein-4b" and calls["n"] == 2
