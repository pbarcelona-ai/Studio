"""Tests for ComfyUI GGUF workflow builders and multi-reference routing fallback."""
from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from local_runners.comfyui_gguf_workflows import (
    build_flux2_klein_gguf_workflow,
    build_z_image_gguf_workflow,
    compute_flux2_dimensions,
    ready_gguf_models,
)
from studio_app import routes_post as rp


def test_ready_gguf_models_detects_flux2_and_z_image(tmp_path: Path) -> None:
    sd_dir = tmp_path / "sd_cli"
    sd_dir.mkdir(parents=True)
    assert ready_gguf_models(models_root=tmp_path) == []

    # Only z-image-turbo ready
    (sd_dir / "z_image_turbo-Q4_K.gguf").write_bytes(b"unet")
    (sd_dir / "Qwen3-4B-Instruct-2507-UD-Q4_K_XL.gguf").write_bytes(b"clip")
    (sd_dir / "ae.safetensors").write_bytes(b"vae")
    assert ready_gguf_models(models_root=tmp_path) == ["z-image-turbo"]
    assert ready_gguf_models(models_root=tmp_path, require_ref_support=True) == []

    # Add FLUX.2 Klein 4B + FLUX.2 VAE
    (sd_dir / "flux-2-klein-4b-Q8_0.gguf").write_bytes(b"flux2")
    (sd_dir / "flux2_ae.safetensors").write_bytes(b"flux2vae")
    assert ready_gguf_models(models_root=tmp_path, require_ref_support=True) == ["flux2-klein-4b"]
    assert ready_gguf_models(models_root=tmp_path) == ["z-image-turbo", "flux2-klein-4b"]


def test_build_flux2_klein_gguf_workflow_supports_multi_refs_and_init_image() -> None:
    wf = build_flux2_klein_gguf_workflow(
        prompt="3D Pixar portrait of Security Officer Kibble",
        width=1024,
        height=1024,
        seed=12345,
        ref_image_names=["kibble_front.png", "set_bridge.png"],
        init_image_name="anchor.png",
        denoise=0.55,
    )
    assert wf["1"]["class_type"] == "UnetLoaderGGUF"
    assert wf["2"]["class_type"] == "CLIPLoaderGGUF"
    assert wf["2"]["inputs"]["type"] == "flux2"
    assert wf["3"]["class_type"] == "VAELoader"
    assert wf["17"]["class_type"] == "ReferenceMultiLatent"
    assert wf["17"]["inputs"]["images.image0"] == ["20_0", 0]
    assert wf["17"]["inputs"]["images.image1"] == ["20_1", 0]
    assert wf["20_0"]["inputs"]["image"] == "kibble_front.png"
    assert wf["20_1"]["inputs"]["image"] == "set_bridge.png"
    assert wf["7"]["inputs"]["positive"] == ["17", 0]
    assert wf["7"]["inputs"]["negative"] == ["17", 1]
    assert wf["7"]["inputs"]["latent_image"] == ["27", 0]
    assert wf["7"]["inputs"]["denoise"] == pytest.approx(0.55)
    assert wf["25"]["inputs"]["image"] == "anchor.png"

    # Without refs or init image -> EmptyFlux2LatentImage at exact target aspect
    w16, h16 = compute_flux2_dimensions("16:9")
    wf_txt = build_flux2_klein_gguf_workflow(prompt="Saturn rings", width=w16, height=h16, seed=7)
    assert "17" not in wf_txt
    assert wf_txt["6"]["class_type"] == "EmptyFlux2LatentImage"
    assert wf_txt["6"]["inputs"]["width"] == 1344
    assert wf_txt["6"]["inputs"]["height"] == 768
    assert wf_txt["7"]["inputs"]["denoise"] == 1.0


def test_build_z_image_gguf_workflow_uses_lumina2_and_auraflow() -> None:
    wf = build_z_image_gguf_workflow(prompt="Cozy living room", width=1344, height=768, seed=99)
    assert wf["1"]["class_type"] == "UnetLoaderGGUF"
    assert wf["2"]["inputs"]["type"] == "lumina2"
    assert wf["11"]["class_type"] == "ModelSamplingAuraFlow"
    assert wf["6"]["class_type"] == "EmptySD3LatentImage"
    assert wf["7"]["inputs"]["sampler_name"] == "res_multistep"


def test_try_comfyui_image_runs_gguf_flux2_with_refs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import local_runners.comfyui_runner as cr_mod

    models_root = tmp_path / "models"
    sd_dir = models_root / "sd_cli"
    sd_dir.mkdir(parents=True)
    (sd_dir / "flux-2-klein-4b-Q8_0.gguf").write_bytes(b"flux2")
    (sd_dir / "Qwen3-4B-Instruct-2507-UD-Q4_K_XL.gguf").write_bytes(b"clip")
    (sd_dir / "flux2_ae.safetensors").write_bytes(b"vae")
    monkeypatch.setattr(rp, "ROOT", tmp_path)

    ref_img = tmp_path / "kibble_front.png"
    ref_img.write_bytes(b"\x89PNG\r\n\x1a\n" + b"refdata" * 30)

    captured: dict[str, Any] = {}

    class FakeComfyRunner:
        def is_installed(self) -> bool:
            return True

        def has_node(self, node_name: str) -> bool:
            return node_name in ("UnetLoaderGGUF", "CLIPLoaderGGUF")

        def upload_image(self, file_path: Path, max_mb: float | None = None) -> str:
            captured.setdefault("uploads", []).append(file_path.name)
            return f"uploaded_{file_path.name}"

        def run_workflow(self, workflow: dict[str, Any], *, output_dir: Path, **kw: Any) -> dict[str, Any]:
            captured["workflow"] = workflow
            out = output_dir / "out-00-flux2.png"
            out.write_bytes(b"\x89PNG\r\n\x1a\n" + b"rendered" * 40)
            return {"ok": True, "output_path": str(out), "outputs": [str(out)]}

    monkeypatch.setattr(cr_mod, "ComfyUIRunner", FakeComfyRunner)

    out_png = tmp_path / "security_officer_kibble_front.png"
    used = rp._try_comfyui_image(
        "Security Officer Kibble wearing crisp navy uniform",
        out_png,
        aspect_ratio="1:1",
        ref_images=[ref_img],
        seed=42,
        require_ref=True,
    )
    assert used == "comfyui:flux2-klein-4b"
    assert out_png.is_file() and b"rendered" in out_png.read_bytes()
    assert captured["uploads"] == ["kibble_front.png"]
    assert captured["workflow"]["17"]["class_type"] == "ReferenceMultiLatent"
    assert captured["workflow"]["20_0"]["inputs"]["image"] == "uploaded_kibble_front.png"


def test_sd_cli_winerror_4551_falls_back_to_comfyui_and_raises_clear_error_when_offline(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("STUDIO_ASSET_CACHE", "0")
    monkeypatch.setattr("run_gemini_omni.get_gemini_api_key", lambda: "")

    ref_img = tmp_path / "kibble_front.png"
    ref_img.write_bytes(b"\x89PNG\r\n\x1a\n" + b"ref" * 40)

    def blocked_sd(*_args: Any, **_kwargs: Any) -> str:
        err = OSError(13, "An Application Control policy has blocked this file", None, 4551)
        raise err

    # Case 1: ComfyUI is online -> seamlessly renders via ComfyUI GGUF!
    def working_comfy(prompt: str, out_png: Path, aspect_ratio: str = "1:1", **kw: Any) -> str:
        out_png.write_bytes(b"\x89PNG\r\n\x1a\n" + b"comfy-ok" * 40)
        return "comfyui:flux2-klein-4b"

    monkeypatch.setattr(rp, "_try_sd_cli_image", blocked_sd)
    monkeypatch.setattr(rp, "_try_comfyui_image", working_comfy)

    out1 = tmp_path / "kibble_ok.png"
    used = rp._render_keyframe_local_or_gemini("Security Officer Kibble", out1, aspect_ratio="1:1", ref_images=[ref_img])
    assert used == "comfyui:flux2-klein-4b"
    assert b"comfy-ok" in out1.read_bytes()

    # Case 2: ComfyUI is offline -> raises actionable PlanError instead of writing a blue placeholder PNG!
    monkeypatch.setattr(rp, "_try_comfyui_image", lambda *a, **kw: "")
    out2 = tmp_path / "kibble_offline.png"
    with pytest.raises(rp.PlanError, match="comfyui_autostart.log"):
        rp._render_keyframe_local_or_gemini("Security Officer Kibble", out2, aspect_ratio="1:1", ref_images=[ref_img])
    assert not out2.exists()


def test_comfyui_lifecycle_autostart_and_clean_stop(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import subprocess
    from local_runners import comfyui_lifecycle as lc

    # Reset managed state for test isolation
    lc.stop_managed_comfyui()

    # 1. Opt-out via env var
    monkeypatch.setenv("STUDIO_AUTOSTART_COMFYUI", "0")
    monkeypatch.setattr(lc, "is_comfyui_reachable", lambda url=None, timeout=0.8: False)
    assert lc.ensure_comfyui_started(root=tmp_path)["status"] == "disabled"
    monkeypatch.setenv("STUDIO_AUTOSTART_COMFYUI", "1")

    # 2. Already running externally -> never spawns duplicate
    monkeypatch.setattr(lc, "is_comfyui_reachable", lambda url=None, timeout=0.8: True)
    res_running = lc.ensure_comfyui_started(root=tmp_path)
    assert res_running["status"] == "already_running" and res_running["ready"] is True

    # 3. Not installed on disk -> clean no-op
    monkeypatch.setattr(lc, "is_comfyui_reachable", lambda url=None, timeout=0.8: False)
    assert lc.ensure_comfyui_started(root=tmp_path)["status"] == "not_installed"

    # 4. Installed on disk -> spawns headless child once, reuses handle on second call, stops cleanly on exit
    comfy_dir = tmp_path / ".local_ai" / "ComfyUI"
    comfy_dir.mkdir(parents=True)
    (comfy_dir / "main.py").write_text("# stub\n", encoding="utf-8")

    spawned: list[dict[str, Any]] = []

    class FakeProc:
        def __init__(self, cmd: list[str], **kw: Any) -> None:
            self.pid = 42424
            self.returncode: int | None = None
            self.terminated = False
            spawned.append({"cmd": cmd, "kw": kw})

        def poll(self) -> int | None:
            return self.returncode

        def terminate(self) -> None:
            self.terminated = True
            self.returncode = 0

        def wait(self, timeout: float | None = None) -> int:
            self.returncode = 0
            return 0

        def kill(self) -> None:
            self.returncode = -9

    monkeypatch.setattr(subprocess, "Popen", FakeProc)
    res1 = lc.ensure_comfyui_started(root=tmp_path, base_url="http://127.0.0.1:8188", wait_ready_s=0.0)
    assert res1["status"] == "started" and res1["pid"] == 42424
    assert len(spawned) == 1
    assert "--port" in spawned[0]["cmd"] and "8188" in spawned[0]["cmd"]

    # Second call while booting reuses the same process instead of spawning a second ComfyUI
    res2 = lc.ensure_comfyui_started(root=tmp_path, base_url="http://127.0.0.1:8188", wait_ready_s=0.0)
    assert res2["status"] == "starting" and len(spawned) == 1

    # Shutdown cleanly stops managed process
    assert lc.stop_managed_comfyui() is True
    assert lc.stop_managed_comfyui() is False


def test_flux2_comfyui_skips_init_latent_for_high_strength_photo_restyle(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import local_runners.comfyui_runner as cr_mod

    models_root = tmp_path / "models"
    sd_dir = models_root / "sd_cli"
    sd_dir.mkdir(parents=True)
    (sd_dir / "flux-2-klein-4b-Q8_0.gguf").write_bytes(b"flux2")
    (sd_dir / "Qwen3-4B-Instruct-2507-UD-Q4_K_XL.gguf").write_bytes(b"clip")
    (sd_dir / "flux2_ae.safetensors").write_bytes(b"vae")
    monkeypatch.setattr(rp, "ROOT", tmp_path)

    photo = tmp_path / "living_room_main_ref.jpg"
    photo.write_bytes(b"\x89PNG\r\n\x1a\n" + b"photo" * 40)
    captured: list[dict[str, Any]] = []

    class FakeComfyRunner:
        base_url = "http://127.0.0.1:8188"

        def is_installed(self) -> bool:
            return True

        def has_node(self, node_name: str) -> bool:
            return node_name in ("UnetLoaderGGUF", "CLIPLoaderGGUF")

        def upload_image(self, file_path: Path, max_mb: float | None = None) -> str:
            return f"up_{file_path.name}"

        def run_workflow(self, workflow: dict[str, Any], *, output_dir: Path, **kw: Any) -> dict[str, Any]:
            captured.append(workflow)
            out = output_dir / "out-00.png"
            out.write_bytes(b"\x89PNG\r\n\x1a\n" + b"pixar" * 40)
            return {"ok": True, "output_path": str(out), "outputs": [str(out)]}

    monkeypatch.setattr(cr_mod, "ComfyUIRunner", FakeComfyRunner)

    # High-strength style conversion (0.68) with same ref & init -> uses EmptyFlux2LatentImage (full 4 steps) + ReferenceMultiLatent
    out1 = tmp_path / "lr_pixar.png"
    rp._try_comfyui_image("Convert to 3D Pixar", out1, "16:9", ref_images=[photo], init_image=photo, init_strength=0.68)
    assert "6" in captured[0] and captured[0]["6"]["class_type"] == "EmptyFlux2LatentImage"
    assert captured[0]["7"]["inputs"]["denoise"] == 1.0
    assert captured[0]["17"]["class_type"] == "ReferenceMultiLatent"

    # Low-strength tight continuity edit (0.45) -> keeps VAEEncode init latent
    out2 = tmp_path / "lr_tight.png"
    rp._try_comfyui_image("Subtle lamp glow", out2, "16:9", ref_images=[photo], init_image=photo, init_strength=0.45)
    assert "27" in captured[1] and captured[1]["27"]["class_type"] == "VAEEncode"
    assert captured[1]["7"]["inputs"]["denoise"] == pytest.approx(0.45)


def test_turnaround_render_prefers_exact_step08_uploaded_ref_over_other_variant(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from types import SimpleNamespace

    proj_dir = tmp_path / "demo_book"
    (proj_dir / "assets" / "turnarounds").mkdir(parents=True)
    (proj_dir / "assets" / "cast_refs").mkdir(parents=True)
    monkeypatch.setattr(rp, "pdir", lambda slug, kind="book": proj_dir)

    # Another variant turnaround already exists ("kibble_front.png"), AND user explicitly uploaded "security_officer_kibble_ref.png"
    (proj_dir / "assets" / "turnarounds" / "kibble_front.png").write_bytes(b"\x89PNG\r\n\x1a\n" + b"toy" * 40)
    uploaded = proj_dir / "assets" / "cast_refs" / "security_officer_kibble_ref.png"
    uploaded.write_bytes(b"\x89PNG\r\n\x1a\n" + b"real-soldier" * 40)

    seen: dict[str, Any] = {}

    def fake_render(prompt: str, out_png: Path, ref_images: list[Path] | None = None, **kw: Any) -> str:
        seen["prompt"] = prompt
        seen["refs"] = [p.name for p in (ref_images or [])]
        out_png.write_bytes(b"\x89PNG\r\n\x1a\n" + b"pixar-soldier" * 40)
        return "comfyui:flux2-klein-4b"

    monkeypatch.setattr(rp, "_render_keyframe_local_or_gemini", fake_render)
    res = rp._v2_turnaround_render(
        SimpleNamespace(
            body={
                "project": "demo_book",
                "character": "Security Officer Kibble",
                "view": "front",
                "look": "pixar_3d",
                "desc": "Tactical security officer",
            }
        )
    )  # type: ignore[arg-type]
    assert seen["refs"] == ["security_officer_kibble_ref.png"]
    assert "3D Pixar" in seen["prompt"]
    assert res["character_control"]["reference_reason"] == "uploaded_cast_photo_restyle"


def test_step08_cast_photo_import_and_convert_to_film_style(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import base64
    from types import SimpleNamespace

    proj_dir = tmp_path / "projects" / "books" / "demo_book"
    proj_dir.mkdir(parents=True)
    monkeypatch.setattr(rp, "pdir", lambda slug, kind="book": proj_dir)
    monkeypatch.setattr("character_tokens.load_character", lambda slug, name: None)

    seen: dict[str, Any] = {}

    def fake_render(prompt: str, out_png: Path, ref_images: list[Path] | None = None, **kw: Any) -> str:
        seen["prompt"] = prompt
        seen["refs"] = [p.name for p in (ref_images or [])]
        seen["init_strength"] = kw.get("init_strength")
        out_png.parent.mkdir(parents=True, exist_ok=True)
        out_png.write_bytes(b"\x89PNG\r\n\x1a\n" + b"styled-front" * 40)
        return "comfyui:flux2-klein-4b"

    monkeypatch.setattr(rp, "_render_keyframe_local_or_gemini", fake_render)

    raw_photo = b"\x89PNG\r\n\x1a\n" + b"real-photo-bytes" * 40
    b64_photo = "data:image/png;base64," + base64.b64encode(raw_photo).decode("ascii")
    res = rp._v2_character_ref_upload(
        SimpleNamespace(
            body={
                "project": "demo_book",
                "character": "Security Officer Kibble",
                "image_base64": b64_photo,
                "convert_now": True,
                "style_id": "pixar_3d",
                "style_strength": 0.75,
                "style_notes": "olive tactical vest and sunglasses",
            }
        )
    )  # type: ignore[arg-type]

    assert res["status"] == "ok"
    assert res["ref_url"].endswith("/assets/cast_refs/security_officer_kibble_ref.png")
    assert res["converted_url"].endswith("/assets/turnarounds/security_officer_kibble_front.png")
    assert res["model"] == "comfyui:flux2-klein-4b"
    assert (proj_dir / "assets" / "cast_refs" / "security_officer_kibble_ref.png").read_bytes() == raw_photo
    assert b"styled-front" in (proj_dir / "assets" / "turnarounds" / "security_officer_kibble_front.png").read_bytes()
    assert seen["refs"] == ["security_officer_kibble_ref.png"]
    assert seen["init_strength"] == pytest.approx(0.75)
    assert "3D Pixar" in seen["prompt"]
    assert "olive tactical vest" in seen["prompt"]
