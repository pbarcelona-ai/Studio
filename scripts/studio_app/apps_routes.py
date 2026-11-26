"""HTTP API routes for bundled declarative ComfyUI Apps, HF Model Packs, HF token verification, and Canvas Studio shot exports."""
from __future__ import annotations

import base64
import csv
import json
from pathlib import Path
import re
import shutil
from typing import Any

from bookkit import SLUG_RE
from layout import project_dir as pdir
from local_runners import model_packs
from local_runners.comfyui_runner import ComfyUIRunner
from local_runners.pantry import resolve_values

from . import config, gpus, handler
from .api import HttpError, Request, route
from .common import PlanError


def _read_csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))

_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")
_MODEL_SLUG_RE = re.compile(r"^[A-Za-z0-9_.-]{1,64}$")
_NEON_ROOT = Path(__file__).resolve().parents[2]


def _apps_root() -> Path:
    cand = config.ROOT / "apps"
    if cand.is_dir():
        return cand
    return _NEON_ROOT / "apps"


def _packs_root() -> Path:
    cand = config.ROOT / "packs"
    if cand.is_dir():
        return cand
    return _NEON_ROOT / "packs"


def _models_root() -> Path:
    env_dir = model_packs.os.environ.get("STUDIO_MODELS_DIR") or model_packs.os.environ.get("FREEFIELD_MODELS_DIR")
    if env_dir:
        return Path(env_dir)
    return config.ROOT / "models"


def _token_user_path() -> Path:
    tok_path = model_packs._studio_token_path()
    return tok_path.with_name(f"{tok_path.name}.user")


def _get_saved_user() -> str:
    p = _token_user_path()
    if p.is_file():
        try:
            return p.read_text(encoding="utf-8").strip()
        except OSError:
            return ""
    return ""


def _save_token_user(user: str) -> None:
    p = _token_user_path()
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(str(user or "").strip() + "\n", encoding="utf-8")
    except OSError:
        pass


def _current_platform_tag(profile: dict[str, Any]) -> str:
    tier = str(profile.get("tier") or "")
    platform_str = str(profile.get("platform") or "")
    backend = str(profile.get("backend") or "")
    if tier == "mac_8g_lite" or backend == "mps" or platform_str.startswith("darwin"):
        return "mac_metal"
    if platform_str.startswith("win"):
        return "win_cuda"
    if platform_str.startswith("linux"):
        return "linux_cuda"
    return "win_cuda"


def _is_app_compatible(manifest: dict[str, Any], profile: dict[str, Any]) -> bool:
    min_vram = float(manifest.get("min_vram_gb") or 0.0)
    avail_vram = float(profile.get("vram_gb") or 0.0)
    platforms = list(manifest.get("platforms") or ["win_cuda", "linux_cuda"])
    ptag = _current_platform_tag(profile)
    section = str(manifest.get("section") or "")
    if section == "video" and not bool(profile.get("supports_local_video", True)):
        return False
    if ptag not in platforms:
        return False
    return not (avail_vram > 0 and min_vram > avail_vram)


def _load_app_manifest(app_id: str) -> tuple[Path, dict[str, Any]]:
    if not isinstance(app_id, str) or not _ID_RE.fullmatch(app_id):
        raise HttpError(400, f"Invalid app_id: {app_id!r}")
    apps_dir = _apps_root().resolve()
    app_dir = (apps_dir / app_id).resolve()
    if apps_dir not in app_dir.parents or not (app_dir / "app.json").is_file():
        raise HttpError(404, f"App not found: {app_id}")
    manifest = json.loads((app_dir / "app.json").read_text(encoding="utf-8"))
    manifest.setdefault("id", app_id)
    manifest.setdefault("min_vram_gb", 0)
    manifest.setdefault("platforms", ["win_cuda", "linux_cuda"])
    return app_dir, manifest


@route("GET", "/api/apps")
def _list_apps(r: Request) -> dict[str, Any]:
    section_filter = r.q("section", "").strip().lower()
    profile = gpus.gpu_profile()
    apps_dir = _apps_root()
    apps: list[dict[str, Any]] = []
    if apps_dir.is_dir():
        for app_json in sorted(apps_dir.glob("*/app.json")):
            try:
                manifest = json.loads(app_json.read_text(encoding="utf-8"))
            except (OSError, ValueError, TypeError):
                continue
            aid = str(manifest.get("id") or app_json.parent.name)
            sec = str(manifest.get("section") or "utility")
            if section_filter and sec.lower() != section_filter:
                continue
            manifest.setdefault("id", aid)
            manifest.setdefault("min_vram_gb", 0)
            manifest.setdefault("platforms", ["win_cuda", "linux_cuda"])
            compat = _is_app_compatible(manifest, profile)
            apps.append({
                "id": aid,
                "name": str(manifest.get("name") or aid),
                "section": sec,
                "pack": str(manifest.get("pack") or "core"),
                "status": str(manifest.get("status") or "ready"),
                "summary": str(manifest.get("summary") or manifest.get("description") or ""),
                "description": str(manifest.get("description") or manifest.get("summary") or ""),
                "min_vram_gb": manifest["min_vram_gb"],
                "platforms": list(manifest["platforms"]),
                "compatible": compat,
            })
    return {"apps": apps, "gpu_profile": profile}


@route("GET", "/api/apps/<app_id>")
def _get_app(r: Request) -> dict[str, Any]:
    app_id = r.p("app_id")
    _, manifest = _load_app_manifest(app_id)
    profile = gpus.gpu_profile()
    out = dict(manifest)
    out["compatible"] = _is_app_compatible(manifest, profile)
    return out


@route("GET", "/api/apps/<app_id>/workflow")
def _get_app_workflow(r: Request) -> dict[str, Any]:
    app_id = r.p("app_id")
    app_dir, manifest = _load_app_manifest(app_id)
    wf_name = str(manifest.get("workflow") or "workflow.api.json")
    wf_path = (app_dir / wf_name).resolve()
    if app_dir not in wf_path.parents or not wf_path.is_file():
        raise HttpError(404, f"Workflow not found for {app_id}")
    return json.loads(wf_path.read_text(encoding="utf-8"))


@route("POST", "/api/apps/<app_id>/run")
def _run_app(r: Request) -> dict[str, Any]:
    app_id = r.p("app_id")
    app_dir, manifest = _load_app_manifest(app_id)
    profile = gpus.gpu_profile()
    if not _is_app_compatible(manifest, profile):
        raise PlanError(
            f"App '{app_id}' is not compatible with current hardware profile "
            f"(tier={profile.get('tier')}, vram_gb={profile.get('vram_gb')} GB, "
            f"requires min_vram_gb={manifest.get('min_vram_gb')} GB, "
            f"supports_local_video={profile.get('supports_local_video')})"
        )

    raw_inputs = r.body.get("inputs") if "inputs" in r.body else r.body.get("values")
    if raw_inputs is None:
        raw_inputs = {}
    if not isinstance(raw_inputs, dict):
        raise PlanError("inputs must be a JSON object")
    raw_inputs = dict(raw_inputs)

    out_dir = config.ROOT / "my_downloads" / app_id
    out_dir.mkdir(parents=True, exist_ok=True)

    # Support browser data-URI uploads & relative workspace paths (e.g. Step 08/10 cast refs) for media inputs
    for inp in manifest.get("inputs") or []:
        iid = str(inp.get("id") or "")
        itype = str(inp.get("type") or "").lower()
        val = raw_inputs.get(iid)
        if itype in ("image", "video", "audio") and isinstance(val, str) and val.strip():
            sval = val.strip()
            if sval.startswith("data:") and "," in sval:
                hdr_part, b64_part = sval.split(",", 1)
                ext = ".png" if itype == "image" else (".mp4" if itype == "video" else ".wav")
                if "jpeg" in hdr_part or "jpg" in hdr_part:
                    ext = ".jpg"
                elif "webp" in hdr_part:
                    ext = ".webp"
                in_dir = out_dir / "inputs"
                in_dir.mkdir(parents=True, exist_ok=True)
                saved_in = in_dir / f"{iid}{ext}"
                saved_in.write_bytes(base64.b64decode(b64_part))
                raw_inputs[iid] = str(saved_in)
            elif not Path(sval).is_absolute():
                cand = (config.ROOT / sval.lstrip("/")).resolve()
                if cand.is_file():
                    raw_inputs[iid] = str(cand)

    for inp in manifest.get("inputs") or []:
        iid = str(inp.get("id") or "")
        if bool(inp.get("required")):
            val = raw_inputs.get(iid)
            if val is None or (isinstance(val, str) and not val.strip()):
                raise PlanError(f"Missing required input '{iid}' for app '{app_id}'")

    try:
        _ = resolve_values(manifest, raw_inputs)
    except ValueError as exc:
        raise PlanError(str(exc)) from exc

    runner = ComfyUIRunner()

    def _on_progress(ev: dict[str, Any]) -> None:
        if ev.get("event") == "preview" and ev.get("data_base64"):
            handler.publish_preview({
                "content_type": str(ev.get("content_type") or "image/jpeg"),
                "data_base64": str(ev["data_base64"]),
            })

    try:
        res = runner.run(
            {
                "app_dir": str(app_dir),
                "values": raw_inputs,
                "output_dir": str(out_dir),
                "profile": profile,
            },
            on_progress=_on_progress,
        )
    except (ValueError, RuntimeError, OSError) as exc:
        msg = str(exc)
        if "10061" in msg or "Connection refused" in msg or "actively refused" in msg:
            raise PlanError(
                f"ComfyUI server is not running at {runner.base_url}. "
                "Start your local ComfyUI server first, then click Run App again."
            ) from exc
        raise PlanError(msg) from exc

    return {
        "status": "completed",
        "app_id": app_id,
        "run_id": res.get("prompt_id") or "run-1",
        "prompt_id": res.get("prompt_id") or "",
        "outputs": res.get("outputs") or [],
        "output_path": res.get("output_path") or "",
    }


def _save_to_shot_dest(
    *,
    project: str,
    shot: Any,
    kind: str,
    model: str,
    payload: bytes,
    as_take: bool = False,
) -> dict[str, Any]:
    if not isinstance(project, str) or not SLUG_RE.match(project):
        raise PlanError("Invalid project slug")
    proj_dir = pdir(project, "book")
    if not proj_dir.is_dir():
        raise HttpError(404, f"Project not found: {project}")

    if isinstance(shot, bool) or not isinstance(shot, int) or shot < 1:
        raise PlanError("shot must be a positive integer")

    shots_csv = proj_dir / "all_shots.csv"
    if shots_csv.is_file():
        rows = _read_csv_rows(shots_csv)
        if shot > len(rows):
            raise PlanError(f"shot {shot} is out of bounds (1..{len(rows)})")

    if kind not in ("keyframe", "image", "video"):
        raise PlanError(f"Unsupported shot output kind: {kind!r}")

    if not isinstance(model, str) or not _MODEL_SLUG_RE.fullmatch(model):
        raise PlanError(f"Invalid model identifier: {model!r}")

    if kind in ("keyframe", "image"):
        folder = proj_dir / "images" / f"{model}_keyframes"
        ext = ".png"
        prefix = "image"
    else:
        folder = proj_dir / "videos" / model
        ext = ".mp4"
        prefix = "shot"

    folder.mkdir(parents=True, exist_ok=True)
    dest = folder / f"{prefix}-{shot:04d}{ext}"
    take_saved = ""
    if dest.is_file() and (as_take or dest.read_bytes() != payload):
        takes_dir = folder / "takes"
        takes_dir.mkdir(parents=True, exist_ok=True)
        idx = 1
        while (takes_dir / f"{prefix}-{shot:04d}-t{idx}{ext}").exists():
            idx += 1
        take_path = takes_dir / f"{prefix}-{shot:04d}-t{idx}{ext}"
        shutil.copy2(dest, take_path)
        take_saved = str(take_path)

    dest.write_bytes(payload)
    return {
        "ok": True,
        "project": project,
        "shot": shot,
        "kind": kind,
        "model": model,
        "dest": str(dest),
        "take": take_saved,
    }


@route("POST", "/api/apps/<app_id>/send-to-shot")
def _send_to_shot(r: Request) -> dict[str, Any]:
    app_id = r.p("app_id")
    _load_app_manifest(app_id)

    project = str(r.body.get("project") or "").strip()
    shot = r.body.get("shot")
    kind = str(r.body.get("kind") or "keyframe").strip().lower()
    model = str(r.body.get("model") or "flux3").strip()
    raw_source = str(r.body.get("source") or "").strip()
    as_take = bool(r.body.get("as_take", False))

    if not raw_source or ".." in Path(raw_source).parts:
        raise PlanError("Invalid source file path")

    src_path = Path(raw_source)
    if not src_path.is_absolute():
        src_path = (config.ROOT / src_path).resolve()
    else:
        src_path = src_path.resolve()

    allowed_roots = (config.ROOT.resolve(), _NEON_ROOT.resolve())
    if not any(root == src_path or root in src_path.parents for root in allowed_roots):
        raise HttpError(403, "source path must be inside the Studio workspace")
    if not src_path.is_file():
        raise HttpError(404, f"Source file not found: {raw_source}")

    return _save_to_shot_dest(
        project=project,
        shot=shot,
        kind=kind,
        model=model,
        payload=src_path.read_bytes(),
        as_take=as_take,
    )


@route("POST", "/api/canvas/export_take")
def _canvas_export_take(r: Request) -> dict[str, Any]:
    project = str(r.body.get("project") or "").strip()
    shot = r.body.get("shot", 1)
    if isinstance(shot, str) and shot.isdigit():
        shot = int(shot)
    kind = str(r.body.get("kind") or "keyframe").strip().lower()
    model = str(r.body.get("model") or "flux3").strip()
    b64 = str(r.body.get("image_base64") or "").strip()
    if "," in b64 and b64.startswith("data:"):
        b64 = b64.split(",", 1)[1]
    if not b64:
        raise PlanError("image_base64 is required")
    try:
        raw_bytes = base64.b64decode(b64, validate=True)
    except Exception as exc:
        raise PlanError(f"Invalid base64 image payload: {exc}") from exc
    if not raw_bytes.startswith(b"\x89PNG\r\n\x1a\n"):
        raise PlanError("image_base64 must decode to a valid PNG file")

    return _save_to_shot_dest(
        project=project,
        shot=shot,
        kind=kind,
        model=model,
        payload=raw_bytes,
        as_take=bool(r.body.get("as_take", True)),
    )


def _aggregate_pack_hardware() -> dict[str, dict[str, Any]]:
    apps_dir = _apps_root()
    info: dict[str, dict[str, Any]] = {}
    if not apps_dir.is_dir():
        return info
    for app_json in sorted(apps_dir.glob("*/app.json")):
        try:
            m = json.loads(app_json.read_text(encoding="utf-8"))
        except (OSError, ValueError, TypeError):
            continue
        pack_id = str(m.get("pack") or "core")
        vram = float(m.get("min_vram_gb") or 0.0)
        plats = list(m.get("platforms") or ["win_cuda", "linux_cuda"])
        cur = info.setdefault(pack_id, {"min_vram_gb": 0.0, "platforms": set()})
        cur["min_vram_gb"] = max(float(cur["min_vram_gb"]), vram)
        cur["platforms"].update(plats)
    return info


@route("GET", "/api/packs")
def _list_packs(_r: Request) -> dict[str, Any]:
    profile = gpus.gpu_profile()
    mdir = _models_root()
    mdir.mkdir(parents=True, exist_ok=True)
    free_gb = round(shutil.disk_usage(mdir).free / 1e9, 2)
    dl_state = model_packs.downloads_status(mdir)
    catalog = model_packs.load_pack_catalog(_packs_root())
    hw_by_pack = _aggregate_pack_hardware()

    tok, tok_src = model_packs.get_token()
    saved_user = _get_saved_user()

    packs_out: list[dict[str, Any]] = []
    for pid, pdata in sorted(catalog.items()):
        models = list(pdata.get("models") or [])
        missing_count = 0
        missing_gb = 0.0
        done_gb = 0.0
        gated_any = bool(pdata.get("needs_hf_token") or pdata.get("gated"))
        for m in models:
            if m.get("gated"):
                gated_any = True
            gb = float(m.get("gb") or 0.0)
            fname = str(m.get("name") or Path(str(m.get("file") or "")).name)
            dest = mdir / str(m.get("dir") or "") / fname
            if dest.is_file():
                done_gb += gb
            else:
                missing_count += 1
                missing_gb += gb
        hw = hw_by_pack.get(pid, {})
        plats = sorted(hw.get("platforms") or ["win_cuda", "linux_cuda", "mac_metal"])
        min_vram = float(pdata.get("min_vram_gb") or hw.get("min_vram_gb") or 0.0)
        total_gb = round(float(pdata.get("download_gb") or (done_gb + missing_gb)), 2)
        packs_out.append({
            "pack": pid,
            "id": pid,
            "title": str(pdata.get("title") or pid),
            "apps": list(pdata.get("apps") or []),
            "models": models,
            "download_gb": total_gb,
            "done_gb": round(done_gb, 2),
            "missing_gb": round(missing_gb, 2),
            "missing": missing_count,
            "installed": missing_count == 0,
            "needs_hf_token": gated_any,
            "gated": gated_any,
            "min_vram_gb": min_vram,
            "platforms": plats,
            "free_gb": free_gb,
        })

    return {
        "packs": sorted(packs_out, key=lambda x: (float(x.get("download_gb") or 0.0), str(x.get("pack") or ""))),
        "free_gb": free_gb,
        "gpu_profile": profile,
        "downloads": dl_state,
        "token": {
            "ok": bool(tok),
            "configured": bool(tok),
            "source": tok_src,
            "user": saved_user,
            "problem": model_packs.env_problem(),
        },
    }


@route("POST", "/api/packs/<pack_id>/download")
def _download_pack(r: Request) -> dict[str, Any]:
    pack_id = r.p("pack_id")
    if not isinstance(pack_id, str) or not _ID_RE.fullmatch(pack_id):
        raise HttpError(400, f"Invalid pack_id: {pack_id!r}")
    catalog = model_packs.load_pack_catalog(_packs_root())
    if pack_id not in catalog:
        raise HttpError(404, f"Model pack not found: {pack_id}")

    pack = catalog[pack_id]
    mdir = _models_root()
    mdir.mkdir(parents=True, exist_ok=True)

    # Check 2 GB free disk headroom before making any network requests
    needed_gb = 0.0
    for m in pack.get("models") or []:
        fname = str(m.get("name") or Path(str(m.get("file") or "")).name)
        dest = mdir / str(m.get("dir") or "") / fname
        if not dest.is_file():
            needed_gb += float(m.get("gb") or 0.0)
    if needed_gb == 0.0:
        needed_gb = float(pack.get("download_gb") or 0.0)
    free_gb = shutil.disk_usage(mdir).free / 1e9
    if (free_gb - needed_gb) < model_packs.MIN_HEADROOM_GB:
        raise PlanError(
            f"Insufficient disk space: {free_gb:.1f} GB free, {needed_gb:.1f} GB needed "
            f"(requires at least {model_packs.MIN_HEADROOM_GB:.1f} GB free disk headroom)"
        )

    tok, _ = model_packs.get_token()
    for m in pack.get("models") or []:
        if m.get("gated") or pack.get("needs_hf_token"):
            if not tok:
                raise HttpError(401, f"Gated model {m['repo']} requires a valid Hugging Face token (401)")
            probe = model_packs.probe_license(str(m["repo"]), str(m["file"]), token=tok)
            if probe == "token":
                raise HttpError(401, f"Hugging Face token rejected for gated model {m['repo']} (401)")
            if probe == "license":
                raise HttpError(403, f"Gated model license not accepted on Hugging Face for {m['repo']} (403 GatedRepo)")

    try:
        res = model_packs.download_packs([pack], models_dir=mdir, packs_dir=_packs_root())
    except RuntimeError as exc:
        raise PlanError(str(exc)) from exc

    if not res.get("ok"):
        failed = res.get("failed") or {}
        reasons = "; ".join(f"{k}: {v.get('reason')}" for k, v in failed.items())
        if "license" in reasons.lower() or "403" in reasons.lower():
            raise HttpError(403, f"Gated model license not accepted (403): {reasons}")
        if "token" in reasons.lower() or "401" in reasons.lower():
            raise HttpError(401, f"Valid Hugging Face token required (401): {reasons}")
        raise PlanError(f"Pack download failed: {reasons}")

    return {"ok": True, "started": True, "pack": pack_id, "downloaded": res.get("downloaded", [])}


@route("POST", "/api/hf/token")
def _save_hf_token(r: Request) -> dict[str, Any]:
    raw_tok = r.body.get("token")
    if not isinstance(raw_tok, str) or not model_packs.looks_like_token(raw_tok):
        raise PlanError("Invalid Hugging Face token format (must start with 'hf_' and be 30+ alphanumeric characters with no spaces)")
    clean_tok = raw_tok.strip()
    try:
        info = model_packs.verify_token(clean_tok)
    except PermissionError as exc:
        raise HttpError(401, str(exc)) from exc
    except ConnectionError as exc:
        raise HttpError(503, str(exc)) from exc
    except ValueError as exc:
        raise PlanError(str(exc)) from exc
    except RuntimeError as exc:
        raise HttpError(502, str(exc)) from exc

    model_packs.save_token(clean_tok, verify=False)
    user = str(info.get("user") or "hf_user")
    _save_token_user(user)
    return {"ok": True, "user": user, "username": user, "configured": True}
