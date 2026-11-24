"""Unit tests for scripts/local_runners/ (base, router, pantry, comfyui_runner, sd_cli_runner, wan2gp_runner)."""
from __future__ import annotations

import json
from pathlib import Path
import sys
from typing import Any

import pytest

_SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from local_runners.base import LocalRunner  # noqa: E402
from local_runners.comfyui_runner import parse_ws_preview_frame  # noqa: E402
from local_runners.pantry import Meter, apply_inputs, model_key, pick_outputs, resolve_values, validate_app  # noqa: E402
from local_runners.router import select_runner  # noqa: E402
from local_runners.sd_cli_runner import MODEL_CATALOG, SdCliRunner, describe_exit_code, pick_binary_asset, rank_windows_assets  # noqa: E402
from local_runners.wan2gp_runner import Wan2GPProgressParser, Wan2GPRunner, normalize_mcp_url  # noqa: E402


def test_local_runner_abc_and_router_selection() -> None:
    with pytest.raises(TypeError):
        LocalRunner()  # type: ignore[abstract]

    p_48g = {
        "platform": "win32",
        "backend": "cuda",
        "name": "NVIDIA GeForce RTX 5090",
        "vram_gb": 48.0,
        "ram_gb": 64.0,
        "compute_cap": "12.0",
        "is_blackwell": True,
        "tier": "full_48g",
        "supports_local_video": True,
        "supports_local_images": True,
        "default_image_backend": "comfyui",
        "default_video_backend": "comfyui",
        "legacy_cloud": False,
    }
    p_mac = {
        "platform": "darwin",
        "backend": "mps",
        "name": "Apple M2",
        "vram_gb": 8.0,
        "ram_gb": 8.0,
        "compute_cap": "MPS",
        "is_blackwell": False,
        "tier": "mac_8g_lite",
        "supports_local_video": False,
        "supports_local_images": True,
        "default_image_backend": "sd_cli",
        "default_video_backend": "none",
        "legacy_cloud": False,
    }

    assert select_runner("image", profile=p_48g).name == "comfyui"
    assert select_runner("video", profile=p_48g).name == "comfyui"
    assert select_runner("video", model_id="wan2gp:wan21-t2v-1.3b", profile=p_48g).name == "wan2gp"
    assert select_runner("image", model_id="sd_cli:z-image-turbo", profile=p_48g).name == "sd_cli"
    assert select_runner("image", profile=p_mac).name == "sd_cli"
    assert select_runner("audio", profile=p_mac).name == "local_audio"

    with pytest.raises(RuntimeError):
        select_runner("video", profile=p_mac)


def test_pantry_meter_and_bindings(tmp_path: Path) -> None:
    manifest: dict[str, Any] = {
        "id": "unit-app",
        "name": "Unit App",
        "section": "image",
        "pack": "core",
        "status": "ready",
        "workflow": "workflow.api.json",
        "min_vram_gb": 0,
        "platforms": ["win_cuda", "linux_cuda", "mac_metal"],
        "inputs": [
            {"id": "prompt", "type": "text", "label": "Prompt", "default": "hello", "bind": [{"node": "1", "field": "text"}]},
            {"id": "seed", "type": "seed", "label": "Seed", "default": -1, "bind": [{"node": "1", "field": "seed"}]},
        ],
        "outputs": [{"node": "2", "type": "image"}],
        "models": [
            {"repo": "org/m", "file": "dir/base.safetensors", "dir": "checkpoints", "gb": 2.0, "phase": "all"},
            {"repo": "org/l", "file": "style.safetensors", "dir": "loras", "gb": 0.2, "phase": "denoise"},
        ],
    }
    wf = {"1": {"class_type": "KSampler", "inputs": {"text": "", "seed": 0}}, "2": {"class_type": "SaveImage", "inputs": {}}}
    app_dir = tmp_path / "unit-app"
    app_dir.mkdir()
    (app_dir / "app.json").write_text(json.dumps(manifest), encoding="utf-8")
    (app_dir / "workflow.api.json").write_text(json.dumps(wf), encoding="utf-8")

    assert validate_app(app_dir) == []
    assert model_key(manifest) == "checkpoints/base.safetensors"

    vals = resolve_values(manifest, {"prompt": "world"})
    assert vals["prompt"] == "world"
    assert isinstance(vals["seed"], int) and vals["seed"] >= 0

    bound = apply_inputs(manifest, wf, vals)
    assert bound["1"]["inputs"]["text"] == "world"

    meter = Meter(expected_nodes=4)
    assert meter.update({"nodes_done": 1, "nodes_total": 1}) == pytest.approx(0.25)
    assert meter.update({"nodes_done": 2, "nodes_total": 4, "step": 5, "steps": 10}) == pytest.approx(0.625)

    items = [{"nodeId": "1", "name": "a.png"}, {"nodeId": "2", "name": "b.png"}]
    assert pick_outputs(items, ["2"]) == [{"nodeId": "2", "name": "b.png"}]


def test_ws_preview_frame_and_sd_cli_helpers(tmp_path: Path) -> None:
    import struct

    jpeg_frame = struct.pack(">II", 1, 1) + b"\xff\xd8\xff\xe0test\xff\xd9"
    parsed = parse_ws_preview_frame(jpeg_frame)
    assert parsed is not None
    assert parsed["content_type"] == "image/jpeg"

    assert "z-image-turbo" in MODEL_CATALOG
    ranked = rank_windows_assets(
        ["sd-master-win-cpu-x64.zip", "sd-master-win-vulkan-x64.zip", "sd-master-win-cuda12-x64.zip"],
        gpu="nvidia",
    )
    assert ranked[0] == "sd-master-win-cuda12-x64.zip"
    with pytest.raises(RuntimeError):
        pick_binary_asset("darwin", "x86_64", ["sd-darwin-arm64.zip"])
    assert "dll" in describe_exit_code(0xC0000135, "win32").lower()

    runner = SdCliRunner(bin_dir=tmp_path / "bin", models_dir=tmp_path / "models")
    assert runner.is_installed() is False


def test_wan2gp_progress_parser_and_url(tmp_path: Path) -> None:
    assert normalize_mcp_url("http://127.0.0.1:7866") == "http://127.0.0.1:7866/mcp"
    parser = Wan2GPProgressParser()
    ev1 = parser.feed("Loading Model\n[1/4] Denoising\n[4/4] Denoising\n")
    progs = [e["progress"] for e in ev1]
    assert progs == sorted(progs)
    assert Wan2GPRunner(install_dir=tmp_path / "missing").is_installed() is False


def test_qa_and_composer_unit_helpers(tmp_path: Path) -> None:
    import wave
    from composers.blender_world_runner import blender_status
    from composers.hyperframes_composer import _scaffold_hyperframes_html, hyperframes_status
    from composers.remotion_composer import remotion_status
    import post_tools
    from qa.composition_validator import CompositionValidator, probe_media_duration, validate_composition
    from qa.visual_qa import VisualQA

    # Create a tiny valid WAV file
    wav_path = tmp_path / "narration.wav"
    with wave.open(str(wav_path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(8000)
        wf.writeframes(b"\x00\x00" * 16000)
    assert probe_media_duration(wav_path) == pytest.approx(2.0, abs=0.05)
    assert probe_media_duration(tmp_path / "missing.wav") is None

    # Validate composition via dict and CompositionValidator wrapper
    clip_file = tmp_path / "clip.mp4"
    clip_file.write_bytes(b"0000")
    comp_json = tmp_path / "comp.json"
    comp_json.write_text(
        json.dumps(
            {
                "render_runtime": "hyperframes",
                "cuts": [{"id": "c1", "source": "clip.mp4", "in_seconds": 0.0, "out_seconds": 3.0}],
                "audio": {
                    "narration": {"src": "narration.wav"},
                    "music": {"src": "narration.wav"},
                },
            }
        ),
        encoding="utf-8",
    )
    res_valid = CompositionValidator().execute({"composition_path": str(comp_json), "assets_root": str(tmp_path)})
    assert res_valid["valid"] is True
    res_dict = validate_composition({"composition_path": str(comp_json)})
    assert res_dict["valid"] is True
    res_missing = validate_composition(tmp_path / "nonexistent.json")
    assert res_missing["valid"] is False

    # VisualQA wrapper on missing file & unknown operation
    vqa = VisualQA()
    assert vqa.execute({"input_path": str(tmp_path / "missing.mp4")})["success"] is False
    assert vqa.execute({"operation": "unknown", "input_path": str(clip_file)})["success"] is False

    # Face tracking parser formats
    ft_file = tmp_path / "faces.json"
    ft_file.write_text(
        json.dumps(
            {
                "faces": [
                    {"timestamp_seconds": 0.5, "bbox": {"x": 0.2, "y": 0.3, "width": 0.1, "height": 0.1}},
                    {"timestamp": 1.0, "faces": [{"x": 0.4, "y": 0.4, "w": 0.2, "h": 0.2}]},
                    {"timestamp": 1.5, "x": 0.5, "y": 0.5, "w": 0.1, "h": 0.1},
                ]
            }
        ),
        encoding="utf-8",
    )
    parsed_faces = post_tools._parse_face_tracking_file(ft_file)
    assert len(parsed_faces) == 3
    assert post_tools.build_atempo_chain(0.25) == "atempo=0.5,atempo=0.5000"

    # Composer status & HyperFrames HTML scaffold
    assert "available" in remotion_status()
    assert "available" in hyperframes_status()
    assert "available" in blender_status()
    idx_html = _scaffold_hyperframes_html(
        tmp_path / "hf_ws",
        {"ink_theater": True, "fps": 24, "edit_decisions": {"cuts": [{"out_seconds": 6.0}]}},
    )
    assert idx_html.is_file()
    assert "ink-theater.js" in idx_html.read_text(encoding="utf-8")


def test_studio_v2_local_gpu_routes(server) -> None:
    # 1. Step 10 Turnaround local render
    code_t, res_t = server.api(
        "POST",
        "/api/v2_turnaround_render",
        {
            "project": "demo",
            "character": "Tommy",
            "view": "front",
            "desc": "Young astronaut boy",
            "wardrobe": "Blue spacesuit",
            "engine": "local",
        },
    )
    assert code_t == 200, res_t
    assert res_t["status"] == "ok" and res_t["image_url"].endswith("tommy_front.png")

    # 2. Step 17 Keyframe local render + edit cascade
    code_k, res_k = server.api(
        "POST",
        "/api/v2_keyframe_render",
        {
            "project": "demo",
            "id": "S001-01",
            "prompt": "Tommy and Judah look out the spaceship window at Saturn's rings",
            "aspect_ratio": "16:9",
            "engine": "local",
        },
    )
    assert code_k == 200, res_k
    assert res_k["status"] == "ok" and res_k["physics_passed"] is True

    code_e, res_e = server.api(
        "POST",
        "/api/v2_keyframe_edit",
        {
            "project": "demo",
            "id": "S001-01",
            "edits": ["Add warm golden sunlight on the window frame"],
            "prompt": "Tommy and Judah look out the spaceship window at Saturn's rings",
            "engine": "local",
        },
    )
    assert code_e == 200, res_e
    assert res_e["status"] == "ok" and res_e["pending_edits"] == ["Add warm golden sunlight on the window frame"]

    # 3. Step 18 Video clip synthesis via local motion animatic
    code_v, res_v = server.api(
        "POST",
        "/api/v2_video_render",
        {
            "project": "demo",
            "id": "S001-01",
            "prompt": "Camera pans slowly toward Saturn",
            "duration": 2,
            "engine": "local_animatic",
        },
    )
    assert code_v == 200, res_v
    assert res_v["status"] == "ok" and res_v["video_url"].endswith("S001-01.mp4")
