"""HTTP routes for Phase 5 multi-runtime composers (/api/composers/*), pre-render QA (/api/qa/check), and post tools (/api/post/*)."""
from __future__ import annotations

from pathlib import Path
import shutil
import subprocess
from typing import Any

from composers.blender_world_runner import blender_status, run_blender
from composers.hyperframes_composer import hyperframes_status, render_hyperframes
from composers.remotion_composer import remotion_status, render_remotion
import post_tools
from qa.composition_validator import validate_composition
from qa.slideshow_risk import score_slideshow_risk
from qa.visual_qa import run_visual_qa

from .api import Request, route
from .common import PlanError


def _guard_traversal(*values: Any) -> None:
    for val in values:
        if not val:
            continue
        s = str(val)
        parts = s.replace("\\", "/").split("/")
        if ".." in parts:
            raise PlanError(f"Path traversal is not allowed: {s}")


def _ffmpeg_compose(body: dict[str, Any]) -> dict[str, Any]:
    ffmpeg_bin = shutil.which("ffmpeg")
    if not ffmpeg_bin:
        raise PlanError("FFmpeg binary is not available on PATH")

    cuts = body.get("cuts")
    if not isinstance(cuts, list) or not cuts:
        raise PlanError("cuts must be a non-empty list for FFmpeg composition")

    output_str = str(body.get("output_path") or "").strip()
    if not output_str:
        raise PlanError("output_path is required for FFmpeg composition")
    _guard_traversal(output_str)
    output_path = Path(output_str)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    temp_dir = output_path.parent / ".ffmpeg_compose_tmp"
    temp_dir.mkdir(parents=True, exist_ok=True)
    try:
        seg_files: list[Path] = []
        for idx, cut in enumerate(cuts):
            if not isinstance(cut, dict):
                raise PlanError(f"Invalid cut at index {idx}")
            src_str = str(cut.get("source") or "").strip()
            _guard_traversal(src_str)
            src_path = Path(src_str)
            if not src_path.is_file():
                raise PlanError(f"Cut source not found: {src_str}")
            in_s = float(cut.get("in_seconds", 0.0) or 0.0)
            out_s = float(cut.get("out_seconds", 0.0) or 0.0)
            dur = max(0.1, out_s - in_s) if out_s > in_s else 1.0
            seg_path = temp_dir / f"seg_{idx:04d}.mp4"
            cmd = [
                ffmpeg_bin,
                "-v",
                "error",
                "-y",
                "-i",
                str(src_path),
                "-t",
                f"{dur:.3f}",
                "-c:v",
                "libx264",
                "-pix_fmt",
                "yuv420p",
                "-c:a",
                "aac",
                "-b:a",
                "128k",
                str(seg_path),
            ]
            proc = subprocess.run(cmd, stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=120)
            if proc.returncode != 0:
                raise PlanError(f"FFmpeg segment failed: {proc.stderr}")
            seg_files.append(seg_path)

        list_file = temp_dir / "concat.txt"
        with list_file.open("w", encoding="utf-8") as fh:
            for sf in seg_files:
                safe = str(sf.resolve()).replace("\\", "/").replace("'", "'\\''")
                fh.write(f"file '{safe}'\n")

        concat_cmd = [
            ffmpeg_bin,
            "-v",
            "error",
            "-y",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(list_file),
            "-c",
            "copy",
            str(output_path),
        ]
        proc = subprocess.run(concat_cmd, stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=120)
        if proc.returncode != 0:
            raise PlanError(f"FFmpeg concat failed: {proc.stderr}")
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)

    return {
        "ok": True,
        "success": True,
        "runtime": "ffmpeg",
        "output_path": str(output_path),
        "cuts_count": len(cuts),
    }


@route("GET", "/api/composers/status")
def api_composers_status(_r: Request) -> dict[str, Any]:
    ffmpeg_bin = shutil.which("ffmpeg")
    rem_st = remotion_status()
    hf_st = hyperframes_status()
    bl_st = blender_status()
    runtimes = {
        "ffmpeg": {"available": ffmpeg_bin is not None, "path": ffmpeg_bin},
        "remotion": rem_st,
        "hyperframes": hf_st,
        "blender": bl_st,
    }
    return {"runtimes": runtimes, **runtimes}


@route("POST", "/api/composers/render")
def api_composers_render(r: Request) -> dict[str, Any]:
    body = r.body
    runtime = str(body.get("runtime") or "ffmpeg").strip().lower()
    _guard_traversal(
        body.get("output_path"),
        body.get("workspace_path"),
        body.get("composer_dir"),
        body.get("blend_path"),
        body.get("composition_path"),
    )

    if runtime == "ffmpeg":
        return _ffmpeg_compose(body)
    if runtime == "remotion":
        try:
            return render_remotion(body)
        except (ValueError, RuntimeError) as exc:
            raise PlanError(str(exc)) from exc
    if runtime == "hyperframes":
        try:
            return render_hyperframes(body)
        except (ValueError, RuntimeError) as exc:
            raise PlanError(str(exc)) from exc
    if runtime == "blender":
        try:
            res = run_blender(body)
        except (ValueError, RuntimeError) as exc:
            raise PlanError(str(exc)) from exc
        if not res.get("success", True) or res.get("ok") is False:
            raise PlanError(str(res.get("error") or "Blender render failed"))
        return res

    raise PlanError(f"Unknown composer runtime {runtime!r}; expected ffmpeg, remotion, hyperframes, or blender")


@route("POST", "/api/qa/check")
def api_qa_check(r: Request) -> dict[str, Any]:
    body = r.body
    _guard_traversal(body.get("composition_path"), body.get("input_path"), body.get("assets_root"))

    scenes = body.get("scenes")
    render_runtime = body.get("render_runtime")
    renderer_family = body.get("renderer_family")
    edit_decisions = body.get("edit_decisions") if isinstance(body.get("edit_decisions"), dict) else None

    result: dict[str, Any] = {"ok": True}

    if isinstance(scenes, list):
        risk = score_slideshow_risk(
            scenes,
            edit_decisions=edit_decisions,
            renderer_family=renderer_family,
            render_runtime=render_runtime,
        )
        result["slideshow_risk"] = risk
        result["verdict"] = risk["verdict"]
        result["average"] = risk["average"]
        result["dimensions"] = risk["dimensions"]
        if risk["verdict"] == "fail":
            result["blocked"] = True

    comp_path = body.get("composition_path")
    if comp_path:
        comp_res = validate_composition(
            str(comp_path),
            assets_root=body.get("assets_root"),
            render_runtime=render_runtime,
        )
        result["composition"] = comp_res
        result["valid"] = bool(comp_res.get("valid", False))
        result["passed"] = bool(comp_res.get("passed", False))
        result["errors"] = comp_res.get("errors", [])
        result["warnings"] = comp_res.get("warnings", [])
    else:
        result.setdefault("valid", result.get("verdict") != "fail")
        result.setdefault("passed", result.get("verdict") != "fail")

    if body.get("input_path"):
        vqa_res = run_visual_qa(
            {
                "operation": body.get("operation", "probe"),
                "input_path": body["input_path"],
                "timestamps": body.get("timestamps"),
                "output_dir": body.get("output_dir"),
                "expected": body.get("expected"),
            }
        )
        result["visual_qa"] = vqa_res

    return result


@route("POST", "/api/post/silence-cut")
def api_post_silence_cut(r: Request) -> dict[str, Any]:
    body = r.body
    _guard_traversal(body.get("input_path"), body.get("output_path"))
    try:
        res = post_tools.silence_cutter(body)
    except (ValueError, RuntimeError) as exc:
        raise PlanError(str(exc)) from exc
    if not res.get("success", True):
        raise PlanError(str(res.get("error") or "silence_cutter failed"))
    return res


@route("POST", "/api/post/auto-reframe")
def api_post_auto_reframe(r: Request) -> dict[str, Any]:
    body = r.body
    _guard_traversal(body.get("input_path"), body.get("output_path"), body.get("face_tracking_json"))
    try:
        res = post_tools.auto_reframe(body)
    except (ValueError, RuntimeError) as exc:
        raise PlanError(str(exc)) from exc
    if not res.get("success", True):
        raise PlanError(str(res.get("error") or "auto_reframe failed"))
    return res
