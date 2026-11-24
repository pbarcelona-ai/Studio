"""Declarative ComfyUI app manifest validation, input binding, monotonic Meter, and Pantry VRAM lifecycle manager."""
from __future__ import annotations

from collections.abc import Callable
import copy
import json
import math
from pathlib import Path
import random
import re
import urllib.error
import urllib.request
from typing import Any

_ID_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
_INPUT_ID_RE = re.compile(r"^[a-z][a-z0-9_]*$")
_REPO_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
_COMMIT_RE = re.compile(r"^[0-9a-f]{7,40}$")
_PLACEHOLDER_RE = re.compile(r"\{([a-z][a-z0-9_]*)\}")

ALLOWED_PLATFORMS = {"win_cuda", "linux_cuda", "mac_metal"}
ALLOWED_SECTIONS = {"image", "video", "audio", "utility"}
ALLOWED_STATUSES = {"draft", "ready"}
ALLOWED_INPUT_TYPES = {"text", "textarea", "number", "slider", "select", "toggle", "seed", "image", "video", "audio"}
ALLOWED_OUTPUT_TYPES = {"image", "video", "audio"}
ALLOWED_MODEL_DIRS = {
    "diffusion_models", "text_encoders", "vae", "loras", "checkpoints", "clip_vision",
    "latent_upscale_models", "upscale_models", "model_patches", "geometry_estimation",
    "background_removal", "frame_interpolation", "audio_encoders", "embeddings", "detection",
}
ALLOWED_MODEL_PHASES = {"encode", "denoise", "denoise2", "decode", "aux", "all"}


def model_key(manifest: dict[str, Any]) -> str:
    """Sorted non-optional, non-LoRA base model key for Pantry VRAM caching."""
    keys: set[str] = set()
    for m in manifest.get("models") or []:
        if not isinstance(m, dict):
            continue
        if m.get("optional") or m.get("dir") == "loras":
            continue
        d = str(m.get("dir") or "").strip()
        f = Path(str(m.get("file") or "")).name
        if d and f:
            keys.add(f"{d}/{f}")
    return ",".join(sorted(keys))


class Pantry:
    """Tracks resident ComfyUI base models and calls POST /free only when the base model set changes."""

    def __init__(self, comfyui_url: str = "http://127.0.0.1:8188", timeout: float = 10.0) -> None:
        self.comfyui_url = comfyui_url.rstrip("/")
        self.timeout = timeout
        self.models: str = ""
        self.last_app: str = ""

    def free(self) -> bool:
        req = urllib.request.Request(
            f"{self.comfyui_url}/free",
            data=json.dumps({"unload_models": True, "free_memory": True}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                _ = resp.read()
                return 200 <= resp.status < 300
        except (urllib.error.HTTPError, urllib.error.URLError, OSError) as exc:
            self.models = ""
            raise RuntimeError(f"ComfyUI POST /free failed: {exc}") from exc

    def prepare(self, app_id: str, next_models: str) -> dict[str, Any]:
        freed = False
        if (self.models or self.last_app) and self.models != next_models:
            self.free()
            freed = True
        self.models = next_models
        self.last_app = app_id
        return {"app": app_id, "models": next_models, "freed": freed}


class Meter:
    """Monotonic ComfyUI progress meter (capped at 0.99) resilient to 1/1 spikes and NaN inputs."""

    def __init__(self, expected_nodes: int = 1, class_of: Callable[[str], str | None] | None = None) -> None:
        self.expected_nodes = max(1, int(expected_nodes or 1))
        self.class_of = class_of
        self.value: float = 0.0
        self.node: str = ""
        self._nodes_done: int = 0

    def update(self, ev: dict[str, Any]) -> float:
        cur_node = ev.get("current_node") or ev.get("node")
        if cur_node is not None:
            nid = str(cur_node)
            cls_name = self.class_of(nid) if callable(self.class_of) else None
            self.node = cls_name or nid

        raw_done = ev.get("nodes_done")
        raw_total = ev.get("nodes_total")
        if isinstance(raw_done, (int, float)) and not math.isnan(raw_done):
            done_i = max(0, int(raw_done))
            total_i = int(raw_total) if isinstance(raw_total, (int, float)) and not math.isnan(raw_total) and int(raw_total) > 0 else self.expected_nodes
            if total_i == 1 and self.expected_nodes > 1:
                total_i = self.expected_nodes
            self._nodes_done = max(self._nodes_done, min(done_i, total_i))
        else:
            total_i = self.expected_nodes

        denom = max(self.expected_nodes, total_i, 1)
        step_frac = 0.0
        raw_step = ev.get("step")
        raw_steps = ev.get("steps")
        if (
            isinstance(raw_step, (int, float))
            and isinstance(raw_steps, (int, float))
            and not math.isnan(raw_step)
            and not math.isnan(raw_steps)
            and raw_steps > 0
        ):
            step_frac = max(0.0, min(1.0, float(raw_step) / float(raw_steps)))

        candidate = (self._nodes_done + step_frac) / float(denom)
        if not math.isnan(candidate):
            self.value = min(0.99, max(self.value, candidate))
        return self.value


def pick_outputs(outputs: list[dict[str, Any]], declared_nodes: list[str]) -> list[dict[str, Any]]:
    """Filter ComfyUI output items to those produced by manifest-declared output nodes, with full fallback."""
    want = {str(n) for n in (declared_nodes or [])}
    picked = [o for o in outputs if str(o.get("nodeId") if "nodeId" in o else o.get("node", "")) in want]
    return picked if picked else list(outputs)


def render_template(template: str, values: dict[str, Any]) -> str:
    """Substitute {var} placeholders and tidy empty punctuation/commas."""
    def _repl(match: re.Match[str]) -> str:
        key = match.group(1)
        val = values.get(key, "")
        return "" if val is None else str(val).strip()

    out = _PLACEHOLDER_RE.sub(_repl, template)
    out = re.sub(r"\s*,\s*,+", ", ", out)
    out = re.sub(r"(^\s*,\s*|\s*,\s*$)", "", out)
    out = re.sub(r"\s*\|\s*$", "", out)
    out = re.sub(r"\s{2,}", " ", out)
    return out.strip()


def validate_app(app_dir: Path | str) -> list[str]:
    """Validate an app folder's app.json and workflow.api.json contract and node bindings."""
    folder = Path(app_dir)
    problems: list[str] = []
    app_file = folder / "app.json"
    if not app_file.is_file():
        return [f"Missing {app_file}"]
    try:
        manifest = json.loads(app_file.read_text(encoding="utf-8"))
    except Exception as exc:
        return [f"Invalid JSON in {app_file}: {exc}"]

    required = {"id", "name", "section", "pack", "status", "inputs", "outputs", "models"}
    missing = required - set(manifest.keys())
    if missing:
        problems.append(f"Missing required keys: {sorted(missing)}")

    allowed_top = required | {
        "$schema", "summary", "higgsfield_feature", "workflow", "source", "modes", "mode_label",
        "presets", "custom_nodes", "vram", "test", "credits", "notes", "min_vram_gb", "platforms",
    }
    extra = set(manifest.keys()) - allowed_top
    if extra:
        problems.append(f"Unexpected top-level keys: {sorted(extra)}")

    app_id = str(manifest.get("id") or "")
    if not _ID_RE.match(app_id):
        problems.append(f"Invalid id {app_id!r}")
    if folder.name and app_id and app_id != folder.name:
        problems.append(f"id {app_id!r} does not match folder {folder.name!r}")
    if manifest.get("section") not in ALLOWED_SECTIONS:
        problems.append(f"Invalid section {manifest.get('section')!r}")
    if manifest.get("status") not in ALLOWED_STATUSES:
        problems.append(f"Invalid status {manifest.get('status')!r}")

    if "min_vram_gb" in manifest:
        mv = manifest.get("min_vram_gb")
        if not isinstance(mv, (int, float)) or isinstance(mv, bool) or mv < 0:
            problems.append(f"Invalid min_vram_gb {mv!r}")
    if "platforms" in manifest:
        pl = manifest.get("platforms")
        if not isinstance(pl, list) or not pl or not set(pl).issubset(ALLOWED_PLATFORMS):
            problems.append(f"Invalid platforms {pl!r}")

    wf: dict[str, Any] = {}
    if manifest.get("status") == "ready":
        wf_name = manifest.get("workflow")
        if not wf_name:
            problems.append("Ready app missing workflow filename")
        else:
            wf_path = folder / str(wf_name)
            if not wf_path.is_file():
                problems.append(f"Missing workflow file {wf_path}")
            else:
                try:
                    wf = json.loads(wf_path.read_text(encoding="utf-8"))
                except Exception as exc:
                    problems.append(f"Invalid workflow JSON: {exc}")

    inputs = manifest.get("inputs") or []
    non_file_ids = {str(i.get("id")) for i in inputs if isinstance(i, dict) and i.get("type") not in {"image", "video", "audio"}}
    for inp in inputs:
        if not isinstance(inp, dict):
            continue
        iid = str(inp.get("id") or "")
        if not _INPUT_ID_RE.match(iid):
            problems.append(f"Invalid input id {iid!r}")
        if inp.get("type") not in ALLOWED_INPUT_TYPES:
            problems.append(f"Invalid input type {inp.get('type')!r}")
        for b in inp.get("bind") or []:
            nid = str(b.get("node") or "")
            if wf and nid not in wf:
                problems.append(f"Input {iid!r} binds to missing workflow node {nid!r}")
            tmpl = b.get("template")
            if tmpl:
                for var in _PLACEHOLDER_RE.findall(str(tmpl)):
                    if var not in non_file_ids:
                        problems.append(f"Template variable {var!r} not in non-file inputs")
        for opt in inp.get("options") or []:
            for s in opt.get("sets") or []:
                nid = str(s.get("node") or "")
                if wf and nid not in wf:
                    problems.append(f"Option set references missing node {nid!r}")

    for preset in manifest.get("presets") or []:
        for s in preset.get("sets") or []:
            nid = str(s.get("node") or "")
            if wf and nid not in wf:
                problems.append(f"Preset references missing node {nid!r}")

    for out in manifest.get("outputs") or []:
        nid = str(out.get("node") or "")
        if wf and nid not in wf:
            problems.append(f"Output references missing node {nid!r}")

    return problems


def resolve_values(manifest: dict[str, Any], raw_values: dict[str, Any] | None = None) -> dict[str, Any]:
    """Validate and coerce input values against an app manifest."""
    given = dict(raw_values or {})
    resolved: dict[str, Any] = {}
    for inp in manifest.get("inputs") or []:
        iid = str(inp["id"])
        itype = str(inp["type"])
        val = given.get(iid, inp.get("default"))

        if itype == "seed":
            seed_num = int(val) if val is not None and str(val).strip() != "" else int(inp.get("default", -1))
            if seed_num < 0:
                seed_num = random.randint(0, (1 << 48) - 1)
            resolved[iid] = seed_num
            continue

        if itype in ("number", "slider"):
            if val is None or (isinstance(val, str) and not val.strip()):
                if inp.get("required", False):
                    raise ValueError(f"Missing required numeric input {iid!r}")
                val = inp.get("default", 0)
            num_val = float(val)
            if math.isnan(num_val) or math.isinf(num_val):
                raise ValueError(f"Invalid number for {iid!r}")
            min_v = inp.get("min")
            max_v = inp.get("max")
            if min_v is not None and num_val < float(min_v):
                raise ValueError(f"Input {iid!r} value {num_val} is below minimum {min_v}")
            if max_v is not None and num_val > float(max_v):
                raise ValueError(f"Input {iid!r} value {num_val} exceeds maximum {max_v}")
            step_v = inp.get("step")
            if isinstance(step_v, int) or (isinstance(inp.get("default"), int) and num_val.is_integer()):
                resolved[iid] = int(num_val)
            else:
                resolved[iid] = num_val
            continue

        if itype == "toggle":
            resolved[iid] = bool(val) if val is not None else bool(inp.get("default", False))
            continue

        if itype == "select":
            options = [opt["value"] for opt in (inp.get("options") or []) if isinstance(opt, dict) and "value" in opt]
            mult = inp.get("multiple")
            if mult:
                items = val if isinstance(val, list) else ([val] if val else (inp.get("default") or []))
                for item in items:
                    if options and item not in options:
                        raise ValueError(f"Invalid option {item!r} for {iid!r}")
                resolved[iid] = list(items)
            else:
                if val is None:
                    val = inp.get("default", options[0] if options else "")
                if options and val not in options:
                    raise ValueError(f"Invalid option {val!r} for {iid!r}")
                resolved[iid] = val
            continue

        if itype in ("text", "textarea"):
            s_val = "" if val is None else str(val)
            if inp.get("required") and not s_val.strip() and iid not in given:
                raise ValueError(f"Missing required text input {iid!r}")
            if inp.get("required") and not s_val.strip():
                raise ValueError(f"Input {iid!r} cannot be empty")
            resolved[iid] = s_val
            continue

        if itype in ("image", "video", "audio"):
            if (val is None or str(val).strip() == "") and inp.get("required"):
                raise ValueError(f"Missing required file input {iid!r}")
            resolved[iid] = val
            continue

        resolved[iid] = val
    return resolved


def apply_inputs(
    manifest: dict[str, Any],
    workflow: dict[str, Any],
    resolved_values: dict[str, Any],
    *,
    preset: str | None = None,
    uploaded_names: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Return a copy of workflow with resolved input bindings, templates, option sets, and presets applied."""
    wf = copy.deepcopy(workflow)
    uploads = dict(uploaded_names or {})

    # Format template values (handling multi-select prefix/join)
    template_vars: dict[str, Any] = {}
    for inp in manifest.get("inputs") or []:
        iid = str(inp["id"])
        val = resolved_values.get(iid)
        mult = inp.get("multiple")
        if mult and isinstance(val, list):
            if val:
                joiner = str(mult.get("join", ", "))
                prefix = str(mult.get("prefix", ""))
                template_vars[iid] = prefix + joiner.join(str(x) for x in val)
            else:
                template_vars[iid] = ""
        else:
            template_vars[iid] = "" if val is None else val

    # 1. Apply preset sets first if requested
    if preset:
        for p in manifest.get("presets") or []:
            if p.get("id") == preset:
                for s in p.get("sets") or []:
                    nid = str(s["node"])
                    if nid in wf:
                        wf[nid].setdefault("inputs", {})[s["field"]] = s["value"]

    # 2. Apply input bindings and selected option sets
    for inp in manifest.get("inputs") or []:
        iid = str(inp["id"])
        itype = str(inp["type"])
        val = resolved_values.get(iid)

        for b in inp.get("bind") or []:
            nid = str(b["node"])
            field = str(b["field"])
            if nid not in wf:
                continue
            wf[nid].setdefault("inputs", {})
            if b.get("template"):
                wf[nid]["inputs"][field] = render_template(str(b["template"]), template_vars)
            elif itype in ("image", "video", "audio"):
                if iid in uploads:
                    wf[nid]["inputs"][field] = uploads[iid]
                elif val is not None and str(val).strip():
                    wf[nid]["inputs"][field] = str(val)
            else:
                wf[nid]["inputs"][field] = template_vars[iid] if inp.get("multiple") else val

        if itype == "select" and not inp.get("multiple"):
            for opt in inp.get("options") or []:
                if opt.get("value") == val:
                    for s in opt.get("sets") or []:
                        nid = str(s["node"])
                        if nid in wf:
                            wf[nid].setdefault("inputs", {})[s["field"]] = s["value"]

    return wf
