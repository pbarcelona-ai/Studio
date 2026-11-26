"""Tests for the 4 free local consistency upgrades:
1. FLUX.1 Kontext Dev & FLUX.2 Klein 9B GGUF catalog + edit preference ordering in SdCliRunner.
2. Native `--mask` flag passed to sd-cli during pixel-locked masked inpainting.
3. Free local Ollama Vision QA (Qwen2.5-VL / Gemma 3) replacing paid Gemini Vision QA.
4. ComfyUI `apps/angles` camera-angle mapping & `POST /api/v2_keyframe_angle_shift` routing.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts"))


def test_sd_cli_kontext_and_klein_9b_ranking_and_mask_argv(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from local_runners import sd_cli_runner as sdr

    mdir = tmp_path / "models"
    bdir = tmp_path / "bin"
    mdir.mkdir()
    bdir.mkdir()
    exe = bdir / ("sd-cli.exe" if sys.platform == "win32" else "sd-cli")
    exe.write_bytes(b"stub")

    runner = sdr.SdCliRunner(bin_dir=bdir, models_dir=mdir)

    # Install FLUX.2 Klein 4B + FLUX.2 Klein 9B (alternate quant!) + FLUX.1 Kontext Dev (alternate quant!)
    for fn in (
        "flux-2-klein-4b-Q8_0.gguf",
        "flux-2-klein-9b-Q4_K_M.gguf",
        "Qwen3-4B-Instruct-2507-UD-Q4_K_XL.gguf",
        "flux2_ae.safetensors",
        "flux1-kontext-dev-Q8_0.gguf",
        "clip_l.safetensors",
        "t5xxl_fp8_e4m3fn.safetensors",
        "ae.safetensors",
    ):
        (mdir / fn).write_bytes(b"stub")

    # General multi-ref prefers fast 4-step Klein 9B, then Kontext Dev, then Klein 4B
    assert runner.ready_models(require_ref_support=True) == ["flux2-klein-9b", "flux1-kontext-dev", "flux2-klein-4b"]
    # Edit / locked-camera mode prefers FLUX.1 Kontext Dev FIRST!
    assert runner.ready_models(require_ref_support=True, prefer_edit=True) == [
        "flux1-kontext-dev",
        "flux2-klein-9b",
        "flux2-klein-4b",
    ]
    desc = {m["id"]: m for m in runner.describe_consistency_models()}
    assert desc["flux1-kontext-dev"]["ready"] is True
    assert desc["flux2-klein-9b"]["ready"] is True
    assert desc["flux1-kontext-dev"]["missing_files"] == []

    # Verify argv construction for flux1-kontext-dev with --mask, -i, -r, --clip_l, --t5xxl, --guidance
    captured_argv: list[str] = []
    out_png = tmp_path / "out.png"
    init_png = tmp_path / "init.png"
    mask_png = tmp_path / "mask.png"
    ref_png = tmp_path / "ref.png"
    for p in (init_png, mask_png, ref_png):
        p.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 256)

    class _FakeStdout:
        def read(self, _n: int = 256) -> bytes:
            return b""

    class _FakeProc:
        pid = 12345
        stdout = _FakeStdout()

        def wait(self) -> int:
            out_png.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 256)
            return 0

    def _fake_popen(argv: list[str], **_kwargs: Any) -> _FakeProc:
        captured_argv.extend(argv)
        return _FakeProc()

    monkeypatch.setattr(sdr.subprocess, "Popen", _fake_popen)
    monkeypatch.setattr(sdr, "acquire_media_lease", lambda **_kw: None)

    runner.run(
        {
            "model": "flux1-kontext-dev",
            "prompt": "keep exact room, Judah licks bowl",
            "aspect_ratio": "16:9",
            "seed": 42,
            "init_image": str(init_png),
            "strength": 0.45,
            "mask_image": str(mask_png),
            "ref_images": [str(ref_png)],
            "output_path": str(out_png),
        }
    )

    assert "--clip_l" in captured_argv
    assert "--t5xxl" in captured_argv
    assert "--guidance" in captured_argv
    assert "--mask" in captured_argv
    assert str(mask_png) in captured_argv
    assert "-i" in captured_argv
    assert "-r" in captured_argv


def test_ollama_vision_qa_replaces_gemini_in_free_local_mode(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from studio_app import local_vision_qa, routes_post

    png = tmp_path / "frame.png"
    ref = tmp_path / "ref.png"
    png.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 256)
    ref.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 256)

    class _FakeResp:
        def __init__(self, payload: dict[str, Any]) -> None:
            self._data = json.dumps(payload).encode("utf-8")

        def read(self) -> bytes:
            return self._data

        def __enter__(self) -> _FakeResp:
            return self

        def __exit__(self, *_args: Any) -> None:
            return None

    def _fake_urlopen(req: Any, timeout: float = 10.0) -> _FakeResp:
        url = str(getattr(req, "full_url", req))
        if url.endswith("/api/tags"):
            return _FakeResp({"models": [{"name": "llama3.2:latest"}, {"name": "qwen2.5vl:7b"}]})
        assert url.endswith("/api/chat")
        body = json.loads(req.data.decode("utf-8"))
        assert body["model"] == "qwen2.5vl:7b"
        assert len(body["messages"][0]["images"]) == 2
        return _FakeResp(
            {
                "message": {
                    "content": json.dumps(
                        {
                            "passed": False,
                            "issues": ["dog paw clips through wooden table"],
                            "continuity_issues": ["window moved to left wall"],
                        }
                    )
                }
            }
        )

    monkeypatch.setattr(local_vision_qa.urllib.request, "urlopen", _fake_urlopen)
    monkeypatch.setattr(routes_post, "_inspect_keyframe_local_qa", lambda _p: {"passed": True, "issues": []})

    gemini_called = {"n": 0}
    monkeypatch.setattr(
        routes_post,
        "_inspect_keyframe_physics",
        lambda *_a, **_kw: (gemini_called.__setitem__("n", gemini_called["n"] + 1) or {"passed": True, "issues": []}),
    )

    # Even if an api_key exists, engine="auto" MUST use free local Ollama Vision QA and NEVER bill Gemini!
    qa = routes_post._inspect_keyframe_free_first(png, "Judah in living room", "auto", "fake-gemini-key", ref_image=ref)
    assert qa["engine"] == "ollama:qwen2.5vl:7b"
    assert qa["passed"] is False
    assert "dog paw clips through wooden table" in qa["issues"]
    assert "window moved to left wall" in qa["continuity_issues"]
    assert gemini_called["n"] == 0


def test_angles_camera_mapping_and_angle_shift_route(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from PIL import Image
    from studio_app import keyframe_context, routes_post

    # 1. Verify camera mapping to ComfyUI `apps/angles` move strings
    mv_top = keyframe_context.map_shot_to_angles_move({"type": "INSERT", "angle": "top-down overhead view"})
    assert "top-down" in mv_top.lower()
    mv_low = keyframe_context.map_shot_to_angles_move({"type": "MS", "height": "low"})
    assert "low-angle" in mv_low.lower()
    mv_fwd = keyframe_context.map_shot_to_angles_move({"type": "CU"}, {"type": "WS"})
    assert "forward" in mv_fwd.lower()

    # 2. Verify `POST /api/v2_keyframe_angle_shift` routes angle_move cleanly to renderer
    slug = "angle_test_book"
    pd = tmp_path / "projects" / "books" / slug
    (pd / "shots").mkdir(parents=True, exist_ok=True)
    (pd / "keyframes").mkdir(parents=True, exist_ok=True)
    (pd / "shots" / "shotlist.json").write_text(
        json.dumps(
            {
                "scenes": [
                    {
                        "id": "S001",
                        "heading": "INT. LIVING ROOM - DAY",
                        "shots": [{"n": 1, "type": "WS"}, {"n": 2, "type": "MS"}],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    img = Image.new("RGB", (128, 128), (50, 100, 180))
    for y in range(20, 40):
        for x in range(20, 40):
            img.putpixel((x, y), ((x * 9) % 255, (y * 13) % 255, 200))
    img.save(pd / "keyframes" / "S001-01.png", format="PNG")

    import character_tokens
    import run_gemini_omni
    monkeypatch.setattr(character_tokens, "PROJECTS", tmp_path / "projects")
    monkeypatch.setattr(character_tokens, "CHARACTERS_ROOT", tmp_path / "projects" / "characters")
    monkeypatch.setattr(run_gemini_omni, "get_gemini_api_key", lambda: "")
    monkeypatch.setattr(routes_post, "pdir", lambda s, kind="book": tmp_path / "projects" / "books" / s)

    captured: dict[str, Any] = {}

    def _fake_comfy(
        prompt: str,
        out_png: Path,
        aspect_ratio: str = "16:9",
        ref_images: list[Path] | None = None,
        view: str = "",
        angle_move: str = "",
    ) -> str:
        captured["angle_move"] = angle_move
        captured["refs"] = [p.name for p in (ref_images or [])]
        img.save(out_png, format="PNG")
        return "comfyui:angles"

    monkeypatch.setattr(routes_post, "_try_comfyui_image", _fake_comfy)

    class _FakePost:
        def __init__(self, body: dict[str, Any]) -> None:
            self.body = body

    res = routes_post._v2_keyframe_angle_shift(
        _FakePost({"project": slug, "id": "S001-02", "move": "rotate_left_45", "details": "Show the toybox corner"})
    )  # type: ignore[arg-type]
    assert res["model"] == "comfyui:angles"
    assert "45 degrees to the left" in captured["angle_move"]
    assert captured["refs"][0] == "S001-01.png"
