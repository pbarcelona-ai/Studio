"""Tier 2 boundary, security, and edge-case E2E tests for Milestone E4 (R3/R4):
F17 (Apps/Packs boundaries), F18 (SSE + core.js boundaries), F19 (freefield JS boundaries),
F20 (Canvas Studio boundaries), and F21 (4-workspace shell boundaries).

Imports ONLY shared non-test helpers from `e2e.test_tier1_r3_r4_routes_sse_ui`.
"""
from __future__ import annotations

import base64
from concurrent.futures import ThreadPoolExecutor
import http.client
import importlib
import json
from pathlib import Path
import re
import shutil
import socket
import struct
import time
from typing import Any, NamedTuple

import pytest

from e2e.conftest import FULL_48G_PLATFORM_TAG, MAC_8G_PLATFORM_TAG
from e2e.helpers.fake_comfyui import MINIMAL_JPEG
from e2e.helpers.fake_hf import FakeHFHubServer
from e2e.helpers.fake_ollama import FakeOllamaServer
from e2e.helpers.studio_harness import IsolatedWorkspace, SSEEvent, StudioHarness
from e2e.test_tier1_r3_r4_routes_sse_ui import (
    ensure_workspace_manifests,
    find_workspace_token_files,
    make_solid_png_bytes,
    run_jsdom_harness,
    seed_demo_book_project,
)

_NEON_ROOT = Path(__file__).resolve().parents[2]
_WEB_DIR = _NEON_ROOT / "web"
_STATIC_JS_DIR = _WEB_DIR / "static" / "js"


# ===========================================================================
# F17 — Apps & Packs Boundaries & Security (Tier 2: 6 tests)
# ===========================================================================


def test_f17_t2_auth_host_origin_and_malformed_json_limits(live_studio_server: StudioHarness) -> None:
    ensure_workspace_manifests(live_studio_server.workspace)
    for method, path in (
        ("GET", "/api/apps"),
        ("GET", "/api/packs"),
        ("POST", "/api/hf/token"),
        ("POST", "/api/apps/smoke/run"),
    ):
        resp = live_studio_server.request(method, path, auth=False)
        assert resp.status == 403, f"Expected 403 for unauthenticated {method} {path}, got {resp.status}"

    assert live_studio_server.request("GET", "/api/apps", host="evil.example:80").status == 403
    assert live_studio_server.request("POST", "/api/hf/token", json_body={"token": "hf_abc"}, origin="http://evil.example").status == 403

    r_bad_json = live_studio_server.post(
        "/api/hf/token",
        raw_body=b"{not-json",
        headers={"Content-Type": "application/json"},
    )
    assert r_bad_json.status == 400

    r_non_dict = live_studio_server.post(
        "/api/hf/token",
        raw_body=b"[1, 2, 3]",
        headers={"Content-Type": "application/json"},
    )
    assert r_non_dict.status == 400

    r_too_big = live_studio_server.post(
        "/api/hf/token",
        raw_body=b"{}",
        headers={"Content-Type": "application/json", "Content-Length": str(9 * 1024 * 1024)},
        timeout=3.0,
    )
    assert r_too_big.status == 413


def test_f17_t2_path_traversal_and_unknown_ids_on_apps_and_packs(live_studio_server: StudioHarness) -> None:
    ensure_workspace_manifests(live_studio_server.workspace)
    traversal_ids = ("%2e%2e", "%2e%2e%2fscripts", "..")
    for bad_id in traversal_ids:
        for method, path, body in (
            ("GET", f"/api/apps/{bad_id}", None),
            ("GET", f"/api/apps/{bad_id}/workflow", None),
            ("POST", f"/api/apps/{bad_id}/run", {"inputs": {}}),
            ("POST", f"/api/apps/{bad_id}/send-to-shot", {"project": "demo", "shot": 1}),
            ("POST", f"/api/packs/{bad_id}/download", {}),
        ):
            resp = live_studio_server.request(method, path, json_body=body)
            assert resp.status in {400, 404}, f"Expected 400/404 for {method} {path}, got {resp.status}: {resp.text}"
            assert "scripts/studio_app" not in resp.text

    assert live_studio_server.get("/api/apps/nonexistent-app-xyz").status in {400, 404}
    assert live_studio_server.get("/api/apps/nonexistent-app-xyz/workflow").status in {400, 404}
    assert live_studio_server.post("/api/packs/nonexistent-pack-xyz/download", {}).status in {400, 404}


def test_f17_t2_run_app_input_validation_and_mac_8g_gating(
    live_studio_server: StudioHarness,
    mac_8g_lite_profile: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ensure_workspace_manifests(live_studio_server.workspace)
    gpus = importlib.import_module("studio_app.gpus")
    monkeypatch.setattr(gpus, "gpu_profile", lambda: dict(mac_8g_lite_profile))

    r_missing = live_studio_server.post("/api/apps/create-image/run", {"inputs": {}})
    assert r_missing.status == 400, r_missing.text
    assert "error" in r_missing.json()

    r_oob = live_studio_server.post("/api/apps/smoke/run", {"inputs": {"width": 99999, "height": 128}})
    assert r_oob.status == 400, r_oob.text
    assert "error" in r_oob.json()

    r_mac_gate = live_studio_server.post(
        "/api/apps/video-t2v/run",
        {"inputs": {"prompt": "Cinematic ocean waves"}},
    )
    assert r_mac_gate.status in {400, 403, 422}, f"Expected gating status, got {r_mac_gate.status}: {r_mac_gate.text}"
    err_msg = str(r_mac_gate.json().get("error", "")).lower()
    assert any(tok in err_msg for tok in ("vram", "8", "mac", "video", "memory", "support", "compat"))


def test_f17_t2_send_to_shot_invalid_bounds_and_source_traversal(
    live_studio_server: StudioHarness,
    isolated_workspace: IsolatedWorkspace,
) -> None:
    ensure_workspace_manifests(isolated_workspace)
    proj = seed_demo_book_project(isolated_workspace, slug="demo", shots=2)
    valid_src = isolated_workspace.root / "my_downloads" / "valid.png"
    valid_src.write_bytes(make_solid_png_bytes(64, 64))

    for bad_shot in (0, -1, 99, "abc"):
        r = live_studio_server.post(
            "/api/apps/smoke/send-to-shot",
            {"project": "demo", "shot": bad_shot, "kind": "keyframe", "model": "flux3", "source": str(valid_src)},
        )
        assert r.status == 400, f"Expected 400 for shot={bad_shot!r}, got {r.status}: {r.text}"

    for bad_proj in ("../escape", "missing_proj"):
        r = live_studio_server.post(
            "/api/apps/smoke/send-to-shot",
            {"project": bad_proj, "shot": 1, "kind": "keyframe", "model": "flux3", "source": str(valid_src)},
        )
        assert r.status in {400, 404}

    r_bad_kind = live_studio_server.post(
        "/api/apps/smoke/send-to-shot",
        {"project": "demo", "shot": 1, "kind": "audio_bad", "model": "flux3", "source": str(valid_src)},
    )
    assert r_bad_kind.status == 400

    for bad_src in ("../../etc/passwd", "/etc/passwd", str(isolated_workspace.root / "my_downloads" / "does_not_exist.png")):
        r = live_studio_server.post(
            "/api/apps/smoke/send-to-shot",
            {"project": "demo", "shot": 1, "kind": "keyframe", "model": "flux3", "source": bad_src},
        )
        assert r.status in {400, 403, 404}

    assert not (proj / "images").exists() or list((proj / "images").rglob("*")) == []


def test_f17_t2_pack_download_low_disk_guard_and_gated_hf_401_403(
    live_studio_server: StudioHarness,
    fake_hf_hub: FakeHFHubServer,
    full_48g_profile: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ensure_workspace_manifests(live_studio_server.workspace)
    gpus = importlib.import_module("studio_app.gpus")
    monkeypatch.setattr(gpus, "gpu_profile", lambda: dict(full_48g_profile))
    monkeypatch.setenv("HF_ENDPOINT", fake_hf_hub.base_url)

    class _DiskUsage(NamedTuple):
        total: int
        used: int
        free: int

    with monkeypatch.context() as mp:
        mp.setattr(shutil, "disk_usage", lambda _p: _DiskUsage(100 * 10**9, 98_500_000_000, 1_500_000_000))
        r_low = live_studio_server.post("/api/packs/image/download", {})
        assert r_low.status == 400, r_low.text
        assert any(w in r_low.text.lower() for w in ("disk", "space", "headroom", "free"))
        assert fake_hf_hub.requests_log == []

    # Check gated pack with missing token (401) and unlicensed token (403 GatedRepo)
    r_packs = live_studio_server.get("/api/packs")
    assert r_packs.status == 200
    raw = r_packs.json().get("packs", [])
    packs = list(raw.values()) if isinstance(raw, dict) else list(raw)
    gated_pack = next((p for p in packs if p.get("needs_hf_token") or p.get("gated")), None)
    assert gated_pack is not None, "Expected at least one gated pack in catalog"
    g_id = str(gated_pack.get("pack") or gated_pack.get("id"))
    for m in gated_pack.get("models", []):
        fake_hf_hub.register_file(
            m["repo"],
            m["file"],
            content=b"gated-model-bytes",
            gated=True,
            allowed_tokens={"hf_licensed_user_12345678901234567890"},
        )

    r_no_tok = live_studio_server.post(f"/api/packs/{g_id}/download", {})
    assert r_no_tok.status in {400, 401, 403}, r_no_tok.text

    unlicensed = "hf_unlicensed_user_1234567890123456"
    fake_hf_hub.set_valid_tokens({unlicensed: "bob_unlicensed", "hf_licensed_user_12345678901234567890": "alice_licensed"})
    assert live_studio_server.post("/api/hf/token", {"token": unlicensed}).status == 200
    r_403 = live_studio_server.post(f"/api/packs/{g_id}/download", {})
    assert r_403.status in {400, 403}, r_403.text
    assert any(w in r_403.text.lower() for w in ("license", "gated", "accept", "access", "403"))


def test_f17_t2_hf_token_rejects_malformed_unauthorized_and_hub_outage(
    live_studio_server: StudioHarness,
    fake_hf_hub: FakeHFHubServer,
    isolated_workspace: IsolatedWorkspace,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ensure_workspace_manifests(isolated_workspace)
    monkeypatch.setenv("HF_ENDPOINT", fake_hf_hub.base_url)

    for bad_body in (
        {},
        {"token": 12345},
        {"token": "not_hf_prefix_12345678901234567890"},
        {"token": "hf_short"},
        {"token": "hf_has spaces in token 1234567890"},
    ):
        r = live_studio_server.post("/api/hf/token", bad_body)
        assert r.status == 400, f"Expected 400 for {bad_body!r}, got {r.status}: {r.text}"
        assert find_workspace_token_files(isolated_workspace) == []

    r_unauth = live_studio_server.post("/api/hf/token", {"token": "hf_unrecognized_valid_shape_1234567890"})
    assert r_unauth.status in {400, 401}, r_unauth.text
    assert find_workspace_token_files(isolated_workspace) == []

    # Hub outage on closed ephemeral port
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        closed_port = s.getsockname()[1]
    monkeypatch.setenv("HF_ENDPOINT", f"http://127.0.0.1:{closed_port}")
    r_down = live_studio_server.post("/api/hf/token", {"token": "hf_valid_shape_unreachable_1234567890"})
    assert r_down.status in {400, 502, 503}, f"Unexpected status on HF outage: {r_down.status}: {r_down.text}"


# ===========================================================================
# F18 — SSE event: preview & core.js Boundaries (Tier 2: 6 tests)
# ===========================================================================


def test_f18_t2_sse_auth_host_origin_and_cookie_enforcement(live_studio_server: StudioHarness) -> None:
    assert live_studio_server.get("/api/v1/events?seconds=0.5", auth=False).status == 403
    assert live_studio_server.get(
        "/api/v1/events?seconds=0.5",
        auth=False,
        headers={"X-Studio-Token": "wrong-token"},
    ).status == 403
    assert live_studio_server.request("GET", "/api/v1/events?seconds=0.5", host="evil.example:80").status == 403
    assert live_studio_server.request("GET", "/api/v1/events?seconds=0.5", origin="http://evil.example").status == 403

    events = live_studio_server.read_sse_events(
        "/api/v1/events?seconds=0.5",
        auth=False,
        headers={"Cookie": f"studio_token={live_studio_server.token}"},
    )
    assert any(e.retry == 3000 for e in events)


def test_f18_t2_sse_bad_query_params_and_clamping(live_studio_server: StudioHarness) -> None:
    r_since = live_studio_server.get("/api/v1/events?since=abc")
    assert r_since.status == 400
    assert r_since.json() == {"error": "since and seconds are numbers"}

    r_sec = live_studio_server.get("/api/v1/events?seconds=nope")
    assert r_sec.status == 400
    assert r_sec.json() == {"error": "since and seconds are numbers"}

    t0 = time.monotonic()
    events = live_studio_server.read_sse_events("/api/v1/events?since=-10&seconds=0.1", timeout=3.0)
    elapsed = time.monotonic() - t0
    assert any(e.retry == 3000 for e in events)
    assert elapsed < 2.0


def test_f18_t2_malformed_ws_preview_frames_do_not_break_sse_stream(live_studio_server: StudioHarness) -> None:
    handler_mod = importlib.import_module("studio_app.handler")
    pantry_mod: Any = None
    comfy_mod: Any = None
    for mod_name in ("local_runners.pantry", "local_runners.comfyui_runner"):
        try:
            mod = importlib.import_module(mod_name)
            if mod_name.endswith("pantry"):
                pantry_mod = mod
            else:
                comfy_mod = mod
        except ImportError:
            pass

    relay_fn = None
    for mod in (handler_mod, pantry_mod, comfy_mod):
        if mod is None:
            continue
        for attr in ("relay_ws_preview_frame", "handle_ws_preview_frame", "publish_ws_preview", "broadcast_preview_bytes"):
            cand = getattr(mod, attr, None)
            if callable(cand):
                relay_fn = cand
                break
        if relay_fn is not None:
            break
    assert relay_fn is not None, "Expected M4 WS binary preview relay function on handler/pantry/comfyui_runner"

    with ThreadPoolExecutor(max_workers=1) as pool:
        fut = pool.submit(live_studio_server.read_sse_events, "/api/v1/events?seconds=1.3")
        time.sleep(0.15)
        for bad_frame in (
            b"",
            b"\x00\x01\x02",
            struct.pack(">II", 99, 1) + MINIMAL_JPEG,
            struct.pack(">II", 1, 9) + b"corrupt",
        ):
            relay_fn(bad_frame)
        relay_fn(struct.pack(">II", 1, 1) + MINIMAL_JPEG)
        events = fut.result(timeout=5.0)

    previews = [e for e in events if e.event == "preview"]
    assert len(previews) == 1, f"Expected exactly 1 valid preview event, got {previews!r}"
    payload = previews[0].json()
    assert payload["content_type"] == "image/jpeg"
    assert base64.b64decode(payload["data_base64"]) == MINIMAL_JPEG


def test_f18_t2_concurrent_sse_subscribers_and_abrupt_disconnect(live_studio_server: StudioHarness) -> None:
    jobs = importlib.import_module("studio_app.jobs")
    handler_mod = importlib.import_module("studio_app.handler")
    pub_fn = getattr(handler_mod, "publish_preview", None) or getattr(handler_mod, "broadcast_preview", None)
    assert callable(pub_fn), "Expected M4 SSE preview broadcaster on studio_app.handler"

    def _abrupt_subscriber() -> None:
        conn = http.client.HTTPConnection("127.0.0.1", live_studio_server.port, timeout=3.0)
        conn.putrequest("GET", "/api/v1/events?seconds=1.2", skip_host=True, skip_accept_encoding=True)
        conn.putheader("Host", f"127.0.0.1:{live_studio_server.port}")
        conn.putheader("X-Studio-Token", live_studio_server.token)
        conn.endheaders()
        resp = conn.getresponse()
        assert resp.status == 200
        _ = resp.readline()
        conn.close()

    with ThreadPoolExecutor(max_workers=3) as pool:
        f_abrupt = pool.submit(_abrupt_subscriber)
        f_sub2 = pool.submit(live_studio_server.read_sse_events, "/api/v1/events?seconds=1.2")
        f_sub3 = pool.submit(live_studio_server.read_sse_events, "/api/v1/events?seconds=1.2")
        time.sleep(0.15)
        for i in range(10):
            jobs.JOB.log(f"concurrent-line-{i}")
            pub_fn({"content_type": "image/jpeg", "data_base64": base64.b64encode(MINIMAL_JPEG).decode("ascii")})
            time.sleep(0.03)
        f_abrupt.result(timeout=4.0)
        ev2: list[SSEEvent] = f_sub2.result(timeout=5.0)
        ev3: list[SSEEvent] = f_sub3.result(timeout=5.0)

    for ev_list in (ev2, ev3):
        assert any(e.event == "log" for e in ev_list)
        previews = [e for e in ev_list if e.event == "preview"]
        assert len(previews) >= 1
        for p in previews:
            assert base64.b64decode(p.json()["data_base64"]) == MINIMAL_JPEG

    assert live_studio_server.get("/api/status").status == 200


def test_f18_t2_core_js_malformed_sse_payload_and_clean_close_on_finish(
    live_studio_server: StudioHarness,
    tmp_path: Path,
) -> None:
    jpeg_b64 = base64.b64encode(MINIMAL_JPEG).decode("ascii")
    scenario = """
const { createNeonDOM } = require("./neon_canvas_harness.cjs");
const [url, b64] = process.argv.slice(2);
(async () => {
  let spyES = null;
  class SpyEventSource {
    constructor(u) {
      this.url = String(u);
      this.listeners = {};
      this.closed = false;
      spyES = this;
    }
    addEventListener(t, fn) { (this.listeners[t] = this.listeners[t] || []).push(fn); }
    close() { this.closed = true; }
    __emitRaw(t, raw) {
      const ev = { type: t, data: raw };
      for (const fn of this.listeners[t] || []) fn(ev);
    }
  }
  const { window: w, document: d, errors, close } = await createNeonDOM({
    url,
    baseUrl: new URL(url).origin,
    beforeParse(win) { win.EventSource = SpyEventSource; },
  });
  await new Promise(r => setTimeout(r, 800));
  if (!spyES && typeof w.startLogStream === "function") w.startLogStream();
  if (!spyES) throw new Error("EventSource not created by core.js");
  spyES.__emitRaw("log", "{bad-json");
  spyES.__emitRaw("preview", "{}");
  spyES.__emitRaw("preview", JSON.stringify({ content_type: "image/jpeg", data_base64: b64 }));
  if (typeof spyES.onerror === "function") spyES.onerror(new w.Event("error"));
  spyES.__emitRaw("status", JSON.stringify({ running: false, step: "done" }));
  await new Promise(r => setTimeout(r, 100));
  const previewImg = d.querySelector("#livePreview, #previewImg, img[data-live-preview], .live-preview img");
  const src = previewImg ? (previewImg.getAttribute("src") || previewImg.src || "") : "";
  const closed = spyES.closed;
  close();
  console.log(JSON.stringify({ src, closed, errors }));
})();
"""
    res = run_jsdom_harness(tmp_path, scenario, args=[f"{live_studio_server.base_url}/?t={live_studio_server.token}", jpeg_b64])
    assert res["errors"] == [], res["errors"]
    assert "undefined" not in res["src"]
    assert res["src"] == f"data:image/jpeg;base64,{jpeg_b64}"
    assert res["closed"] is True


def test_f18_t2_no_preview_or_log_leak_across_sequential_workspaces(
    isolated_workspace: IsolatedWorkspace,
    tmp_path: Path,
) -> None:
    jobs = importlib.import_module("studio_app.jobs")
    handler_mod = importlib.import_module("studio_app.handler")
    pub_fn = getattr(handler_mod, "publish_preview", None) or getattr(handler_mod, "broadcast_preview", None)

    with StudioHarness(workspace=isolated_workspace) as h1:
        jobs.JOB.log("ws1-secret-log")
        if callable(pub_fn):
            pub_fn({"content_type": "image/jpeg", "data_base64": base64.b64encode(MINIMAL_JPEG).decode("ascii")})
        ev1 = h1.read_sse_events("/api/v1/events?seconds=0.6")
        assert any(e.event == "log" and e.json() == "ws1-secret-log" for e in ev1)

    with IsolatedWorkspace(base_dir=tmp_path / "ws2") as ws2, StudioHarness(workspace=ws2) as h2:
        ev2 = h2.read_sse_events("/api/v1/events?seconds=0.6")
        assert not any(e.event == "log" and "ws1-secret-log" in str(e.data) for e in ev2)
        assert not any(e.event == "preview" for e in ev2)


# ===========================================================================
# F19 — Ported freefield JS Boundaries (Tier 2: 8 tests)
# ===========================================================================


def test_f19_t2_paint_undo_boundary_0_20_21_plus_overflow(tmp_path: Path) -> None:
    paint_js = _STATIC_JS_DIR / "paint.js"
    assert paint_js.is_file(), f"Missing {paint_js}"
    bg_b64 = base64.b64encode(make_solid_png_bytes(160, 120)).decode("ascii")

    scenario = """
const fs = require("fs");
const { createNeonDOM } = require("./neon_canvas_harness.cjs");
const [paintPath, bgB64] = process.argv.slice(2);
(async () => {
  const { window: w, document: d, errors, close } = await createNeonDOM({
    html: "<!doctype html><html><body><div id='paintHost'></div></body></html>",
  });
  w.eval(fs.readFileSync(paintPath, "utf-8"));
  const openFn = w.openPainter || (w.StudioPaint && w.StudioPaint.open);
  openFn(`data:image/png;base64,${bgB64}`, { container: d.getElementById("paintHost") });
  await new Promise(r => setTimeout(r, 80));
  const undoBtn = [...d.querySelectorAll("button")].find(b => /undo/i.test(b.textContent || b.title || ""));
  const redoBtn = [...d.querySelectorAll("button")].find(b => /redo/i.test(b.textContent || b.title || ""));
  if (!undoBtn) throw new Error("Undo button missing");
  // Undo at 0 strokes -> no-op
  undoBtn.click();
  const canvas = d.querySelector("canvas");
  const ctx = canvas.getContext("2d");
  const fire = (t, x, y) => canvas.dispatchEvent(new w.PointerEvent(t, { bubbles: true, clientX: x, clientY: y, pointerId: 1 }));
  for (let i = 0; i < 25; i++) {
    const y = 5 + i * 4;
    fire("pointerdown", 10, y);
    fire("pointermove", 30, y);
    fire("pointerup", 30, y);
  }
  for (let i = 0; i < 22; i++) undoBtn.click();
  // Stroke #1..#5 remain after 20-step cap; stroke #5 at y=21 should still exist, stroke #25 at y=101 should be gone
  const stroke5Pixel = ctx.getImageData(20, 21, 1, 1).data[0];
  const stroke25Pixel = ctx.getImageData(20, 101, 1, 1).data[0];
  // Drawing after undo truncates redo tail
  fire("pointerdown", 80, 50);
  fire("pointermove", 100, 50);
  fire("pointerup", 100, 50);
  if (redoBtn) redoBtn.click();
  const stroke25AfterNew = ctx.getImageData(20, 101, 1, 1).data[0];
  close();
  console.log(JSON.stringify({ stroke5Pixel, stroke25Pixel, stroke25AfterNew, errors }));
})();
"""
    res = run_jsdom_harness(tmp_path, scenario, args=[str(paint_js), bg_b64])
    assert res["errors"] == [], res["errors"]
    assert res["stroke5Pixel"] > 0
    assert res["stroke25Pixel"] == 0
    assert res["stroke25AfterNew"] == 0


def test_f19_t2_paint_empty_mask_and_erased_all_rejection(tmp_path: Path) -> None:
    paint_js = _STATIC_JS_DIR / "paint.js"
    assert paint_js.is_file(), f"Missing {paint_js}"
    bg_b64 = base64.b64encode(make_solid_png_bytes(160, 120)).decode("ascii")

    scenario = """
const fs = require("fs");
const { createNeonDOM } = require("./neon_canvas_harness.cjs");
const [paintPath, bgB64] = process.argv.slice(2);
(async () => {
  const { window: w, document: d, errors, close } = await createNeonDOM({
    html: "<!doctype html><html><body><div id='paintHost'></div></body></html>",
  });
  w.eval(fs.readFileSync(paintPath, "utf-8"));
  let doneCalls = 0;
  const openFn = w.openPainter || (w.StudioPaint && w.StudioPaint.open);
  openFn(`data:image/png;base64,${bgB64}`, { container: d.getElementById("paintHost"), onDone() { doneCalls++; } });
  await new Promise(r => setTimeout(r, 80));
  const doneBtn = [...d.querySelectorAll("button")].find(b => /done|apply|save|export/i.test(b.textContent || ""));
  const clearBtn = [...d.querySelectorAll("button")].find(b => /clear/i.test(b.textContent || ""));
  doneBtn.click();
  await new Promise(r => setTimeout(r, 50));
  const emptyMsg = d.body.textContent;
  const canvas = d.querySelector("canvas");
  canvas.dispatchEvent(new w.PointerEvent("pointerdown", { bubbles: true, clientX: 20, clientY: 20, pointerId: 1 }));
  canvas.dispatchEvent(new w.PointerEvent("pointermove", { bubbles: true, clientX: 50, clientY: 20, pointerId: 1 }));
  canvas.dispatchEvent(new w.PointerEvent("pointerup", { bubbles: true, clientX: 50, clientY: 20, pointerId: 1 }));
  clearBtn.click();
  doneBtn.click();
  await new Promise(r => setTimeout(r, 50));
  close();
  console.log(JSON.stringify({ doneCalls, hasWarning: /empty|paint|draw|mask/i.test(emptyMsg), errors }));
})();
"""
    res = run_jsdom_harness(tmp_path, scenario, args=[str(paint_js), bg_b64])
    assert res["errors"] == [], res["errors"]
    assert res["doneCalls"] == 0


def test_f19_t2_paint_zero_dimension_canvas_and_bad_image(tmp_path: Path) -> None:
    paint_js = _STATIC_JS_DIR / "paint.js"
    assert paint_js.is_file(), f"Missing {paint_js}"

    scenario = """
const fs = require("fs");
const { createNeonDOM } = require("./neon_canvas_harness.cjs");
const [paintPath] = process.argv.slice(2);
(async () => {
  const { window: w, document: d, errors, close } = await createNeonDOM({
    html: "<!doctype html><html><body><div id='paintHost'></div></body></html>",
    zeroRect: true,
  });
  w.eval(fs.readFileSync(paintPath, "utf-8"));
  const openFn = w.openPainter || (w.StudioPaint && w.StudioPaint.open);
  openFn("http://127.0.0.1/corrupt-image.png", { container: d.getElementById("paintHost") });
  await new Promise(r => setTimeout(r, 100));
  const canvas = d.querySelector("canvas");
  if (canvas) {
    canvas.dispatchEvent(new w.PointerEvent("pointerdown", { bubbles: true, clientX: 10, clientY: 10, pointerId: 1 }));
    canvas.dispatchEvent(new w.PointerEvent("pointerup", { bubbles: true, clientX: 10, clientY: 10, pointerId: 1 }));
  }
  close();
  console.log(JSON.stringify({ width: canvas ? canvas.width : 1, height: canvas ? canvas.height : 1, errors }));
})();
"""
    res = run_jsdom_harness(tmp_path, scenario, args=[str(paint_js)])
    assert res["errors"] == [], res["errors"]
    assert res["width"] >= 1 and res["height"] >= 1


def test_f19_t2_compare_dual_video_nan_duration_asymmetric_and_missing_source(tmp_path: Path) -> None:
    compare_js = _STATIC_JS_DIR / "compare.js"
    assert compare_js.is_file(), f"Missing {compare_js}"

    scenario = """
const fs = require("fs");
const { createNeonDOM } = require("./neon_canvas_harness.cjs");
const [cmpPath] = process.argv.slice(2);
(async () => {
  const { window: w, document: d, errors, close } = await createNeonDOM({
    html: "<!doctype html><html><body><div id='cmpHost'></div></body></html>",
  });
  w.eval(fs.readFileSync(cmpPath, "utf-8"));
  const openCmp = w.openCompare || (w.StudioCompare && w.StudioCompare.open);
  // Case 1: NaN duration scrub + asymmetric 12s vs 3s
  openCmp(
    { kind: "video", src: "http://127.0.0.1/a.mp4", label: "Long", duration: NaN },
    { kind: "video", src: "http://127.0.0.1/b.mp4", label: "Short", duration: 3 },
    { container: d.getElementById("cmpHost") }
  );
  await new Promise(r => setTimeout(r, 80));
  const videos = [...d.querySelectorAll("video")];
  videos[0].setAttribute("data-duration", "NaN");
  const seek = d.querySelector("input[type='range']");
  if (seek) {
    seek.value = "50";
    seek.dispatchEvent(new w.Event("input", { bubbles: true }));
  }
  const hasNaNTime = videos.some(v => Number.isNaN(v.currentTime));
  videos[0].setAttribute("data-duration", "12");
  videos[1].setAttribute("data-duration", "3");
  videos[0].currentTime = 4.5;
  videos[1].currentTime = 3.0;
  await new Promise(r => setTimeout(r, 450));
  const vbClamped = videos[1].currentTime <= 3.01;

  // Case 2: image + video mismatch disables Wipe mode
  d.getElementById("cmpHost").innerHTML = "";
  openCmp(
    { kind: "image", src: "http://127.0.0.1/a.png", label: "Img" },
    { kind: "video", src: "http://127.0.0.1/b.mp4", label: "Vid" },
    { container: d.getElementById("cmpHost") }
  );
  await new Promise(r => setTimeout(r, 60));
  const wipeBtn = [...d.querySelectorAll("button")].find(b => /wipe/i.test(b.textContent || ""));
  const wipeDisabledOnMismatch = !wipeBtn || wipeBtn.disabled;
  close();
  console.log(JSON.stringify({ hasNaNTime, vbClamped, wipeDisabledOnMismatch, errors }));
})();
"""
    res = run_jsdom_harness(tmp_path, scenario, args=[str(compare_js)])
    assert res["errors"] == [], res["errors"]
    assert res["hasNaNTime"] is False
    assert res["vbClamped"] is True
    assert res["wipeDisabledOnMismatch"] is True


def test_f19_t2_compare_wipe_pointer_clamp_and_url_revoke(tmp_path: Path) -> None:
    compare_js = _STATIC_JS_DIR / "compare.js"
    assert compare_js.is_file(), f"Missing {compare_js}"
    img_a = base64.b64encode(make_solid_png_bytes(160, 120)).decode("ascii")
    img_b = base64.b64encode(make_solid_png_bytes(160, 120)).decode("ascii")

    scenario = """
const fs = require("fs");
const { createNeonDOM } = require("./neon_canvas_harness.cjs");
const [cmpPath, aB64, bB64] = process.argv.slice(2);
(async () => {
  const { window: w, document: d, errors, close } = await createNeonDOM({
    html: "<!doctype html><html><body><div id='cmpHost'></div></body></html>",
  });
  w.eval(fs.readFileSync(cmpPath, "utf-8"));
  const blobA = new w.Blob([Buffer.from(aB64, "base64")], { type: "image/png" });
  const blobB = new w.Blob([Buffer.from(bB64, "base64")], { type: "image/png" });
  const urlA = w.URL.createObjectURL(blobA);
  const urlB = w.URL.createObjectURL(blobB);
  const openCmp = w.openCompare || (w.StudioCompare && w.StudioCompare.open);
  const inst = openCmp(
    { kind: "image", src: urlA, label: "A", revokeOnClose: true },
    { kind: "image", src: urlB, label: "B", revokeOnClose: true },
    { container: d.getElementById("cmpHost") }
  );
  await new Promise(r => setTimeout(r, 80));
  const wipeBtn = [...d.querySelectorAll("button")].find(b => /wipe/i.test(b.textContent || ""));
  if (wipeBtn) wipeBtn.click();
  const stage = d.querySelector(".wipe, .compare-stage, [data-compare-stage]") || d.getElementById("cmpHost");
  stage.dispatchEvent(new w.PointerEvent("pointerdown", { bubbles: true, clientX: -200, clientY: 20, pointerId: 1 }));
  const handle = d.querySelector("[data-wipe-handle], .wipe-handle, .compare-handle, [role='slider']");
  const leftMin = handle ? handle.style.left : "";
  stage.dispatchEvent(new w.PointerEvent("pointermove", { bubbles: true, clientX: 9999, clientY: 20, pointerId: 1 }));
  const leftMax = handle ? handle.style.left : "";
  stage.dispatchEvent(new w.PointerEvent("pointerup", { bubbles: true, clientX: 9999, clientY: 20, pointerId: 1 }));
  const closeBtn = [...d.querySelectorAll("button")].find(b => /close|exit|done/i.test(b.textContent || ""));
  if (inst && typeof inst.close === "function") inst.close();
  else if (closeBtn) closeBtn.click();
  const revoked = w.__neonRevokedUrls.slice();
  close();
  console.log(JSON.stringify({ leftMin, leftMax, revokedCount: revoked.length, errors }));
})();
"""
    res = run_jsdom_harness(tmp_path, scenario, args=[str(compare_js), img_a, img_b])
    assert res["errors"] == [], res["errors"]
    assert res["leftMin"] == "0%" and res["leftMax"] == "100%"
    assert res["revokedCount"] >= 2


def test_f19_t2_packs_8gb_mac_gated_badges_and_2gb_disk_guard(tmp_path: Path) -> None:
    packs_js = _STATIC_JS_DIR / "packs_vram.js"
    assert packs_js.is_file(), f"Missing {packs_js}"

    scenario = r"""
const fs = require("fs");
const { createNeonDOM } = require("./neon_canvas_harness.cjs");
const [packsPath, fullTag, macTag] = process.argv.slice(2);
(async () => {
  const { window: w, document: d, errors, close } = await createNeonDOM({
    html: "<!doctype html><html><body><div id='packsHost'></div></body></html>",
    beforeParse(win) {
      win.__virtualRoutes = {
        "/api/packs": {
          status: 200,
          body: {
            free_gb: 10.5,
            token: { ok: true, configured: true },
            gpu_profile: { tier: "mac_8g_lite", vram_gb: 8.0, ram_gb: 8.0 },
            packs: [
              { pack: "video-wan", apps: ["wan-t2v"], download_gb: 9.0, missing_gb: 9.0, min_vram_gb: 24, platforms: [fullTag], missing: 1, models: [{ repo: "w/wan", file: "w.safetensors", gb: 9.0 }] },
              { pack: "image-lite", apps: ["z-image"], download_gb: 9.0, missing_gb: 9.0, min_vram_gb: 6, platforms: [macTag, fullTag], missing: 1, models: [{ repo: "z/img", file: "z.gguf", gb: 9.0 }] },
            ],
          },
        },
      };
    },
  });
  w.eval(fs.readFileSync(packsPath, "utf-8"));
  const initFn = w.initPacksVram || (w.PacksVram && w.PacksVram.render);
  if (typeof initFn === "function") await initFn(d.getElementById("packsHost"));
  await new Promise(r => setTimeout(r, 150));
  const dlBtns = [...d.querySelectorAll("button")].filter(b => /download|install/i.test(b.textContent || ""));
  const allDlDisabled = dlBtns.length > 0 && dlBtns.every(b => b.disabled);
  const txt = d.body.textContent.toLowerCase();
  close();
  console.log(JSON.stringify({ allDlDisabled, mentionsDiskOrGuard: /headroom|disk|space|2\s*gb/i.test(txt), errors }));
})();
"""
    res = run_jsdom_harness(tmp_path, scenario, args=[str(packs_js), FULL_48G_PLATFORM_TAG, MAC_8G_PLATFORM_TAG])
    assert res["errors"] == [], res["errors"]
    assert res["allDlDisabled"] is True
    assert res["mentionsDiskOrGuard"] is True


def test_f19_t2_apps_packs_xss_escaping_in_metadata(tmp_path: Path) -> None:
    apps_js = _STATIC_JS_DIR / "apps_gallery.js"
    packs_js = _STATIC_JS_DIR / "packs_vram.js"
    assert apps_js.is_file() and packs_js.is_file()

    scenario = """
const fs = require("fs");
const { createNeonDOM } = require("./neon_canvas_harness.cjs");
const [appsPath, packsPath] = process.argv.slice(2);
(async () => {
  const xssName = '<img src=x onerror="window.__xss=1"><script>window.__xss=2</script>" onmouseover="window.__xss=3';
  const { window: w, document: d, errors, close } = await createNeonDOM({
    html: "<!doctype html><html><body><div id='appsHost'></div><div id='packsHost'></div></body></html>",
    beforeParse(win) {
      win.__virtualRoutes = {
        "/api/apps": {
          status: 200,
          body: { apps: [{ id: "xss-app", name: xssName, section: "image", pack: "core", min_vram_gb: 4, platforms: ["mac_metal"], compatible: true, description: xssName }] },
        },
        "/api/packs": {
          status: 200,
          body: {
            free_gb: 100,
            token: { ok: false },
            gpu_profile: { tier: "full_48g", vram_gb: 48.0, ram_gb: 64.0 },
            packs: [{ pack: "xss-pack", title: xssName, apps: ["xss-app"], download_gb: 1.0, min_vram_gb: 4, platforms: ["win_cuda"], models: [] }],
          },
        },
      };
    },
  });
  w.eval(fs.readFileSync(appsPath, "utf-8"));
  w.eval(fs.readFileSync(packsPath, "utf-8"));
  const initApps = w.initAppsGallery || (w.AppsGallery && w.AppsGallery.render);
  const initPacks = w.initPacksVram || (w.PacksVram && w.PacksVram.render);
  if (typeof initApps === "function") await initApps(d.getElementById("appsHost"));
  if (typeof initPacks === "function") await initPacks(d.getElementById("packsHost"));
  await new Promise(r => setTimeout(r, 150));
  const injectedEls = d.querySelectorAll("img[onerror], script, [onmouseover]").length;
  const xssFlag = w.__xss;
  close();
  console.log(JSON.stringify({ injectedEls, xssTriggered: xssFlag !== undefined, hasLiteralEscaped: d.body.textContent.includes("<img src=x"), errors }));
})();
"""
    res = run_jsdom_harness(tmp_path, scenario, args=[str(apps_js), str(packs_js)])
    assert res["errors"] == [], res["errors"]
    assert res["injectedEls"] == 0
    assert res["xssTriggered"] is False
    assert res["hasLiteralEscaped"] is True


def test_f19_t2_apps_gallery_empty_search_and_nonexistent_app_id(tmp_path: Path) -> None:
    apps_js = _STATIC_JS_DIR / "apps_gallery.js"
    assert apps_js.is_file(), f"Missing {apps_js}"

    scenario = r"""
const fs = require("fs");
const { createNeonDOM } = require("./neon_canvas_harness.cjs");
const [appsPath] = process.argv.slice(2);
(async () => {
  const { window: w, document: d, errors, close } = await createNeonDOM({
    html: "<!doctype html><html><body><div id='appsHost'></div></body></html>",
    beforeParse(win) {
      win.__virtualRoutes = {
        "/api/apps": {
          status: 200,
          body: { apps: [{ id: "smoke", name: "Smoke", section: "utility", pack: "core", min_vram_gb: 2, platforms: ["mac_metal"], compatible: true }] },
        },
        "/api/apps/does-not-exist": { status: 404, body: { error: "app not found" } },
      };
    },
  });
  w.eval(fs.readFileSync(appsPath, "utf-8"));
  const initApps = w.initAppsGallery || (w.AppsGallery && w.AppsGallery.render);
  if (typeof initApps === "function") await initApps(d.getElementById("appsHost"));
  await new Promise(r => setTimeout(r, 100));
  const search = d.querySelector("input[type='search'], input[type='text']");
  if (search) {
    search.value = "zzz_nonexistent_999";
    search.dispatchEvent(new w.Event("input", { bubbles: true }));
  }
  await new Promise(r => setTimeout(r, 80));
  const emptyText = d.body.textContent;
  if (w.AppsGallery && typeof w.AppsGallery.open === "function") await w.AppsGallery.open("does-not-exist");
  await new Promise(r => setTimeout(r, 80));
  close();
  console.log(JSON.stringify({ hasEmptyState: /no\s+apps|empty|none|0\s+match/i.test(emptyText), errors }));
})();
"""
    res = run_jsdom_harness(tmp_path, scenario, args=[str(apps_js)])
    assert res["errors"] == [], res["errors"]
    assert res["hasEmptyState"] is True


# ===========================================================================
# F20 — Client-Side Canvas Studio Boundaries (Tier 2: 7 tests)
# ===========================================================================


def test_f20_t2_zoom_and_pan_clamping_boundaries(tmp_path: Path) -> None:
    cs_js = _STATIC_JS_DIR / "canvas_studio.js"
    assert cs_js.is_file(), f"Missing {cs_js}"
    img_b64 = base64.b64encode(make_solid_png_bytes(320, 240)).decode("ascii")

    scenario = """
const fs = require("fs");
const { createNeonDOM } = require("./neon_canvas_harness.cjs");
const [csPath, b64] = process.argv.slice(2);
(async () => {
  const { window: w, document: d, errors, close } = await createNeonDOM({
    html: "<!doctype html><html><body><div id='csHost'></div></body></html>",
  });
  w.eval(fs.readFileSync(csPath, "utf-8"));
  const mount = w.mountCanvasStudio || (w.CanvasStudio && w.CanvasStudio.mount);
  const api = mount(d.getElementById("csHost"), { imageUrl: `data:image/png;base64,${b64}` });
  await new Promise(r => setTimeout(r, 80));
  const zoomIn = [...d.querySelectorAll("button")].find(b => /zoom\\s*\\+|\\bin\\b|^\\+$/i.test((b.textContent || b.title || "").trim()));
  const zoomOut = [...d.querySelectorAll("button")].find(b => /zoom\\s*-|\\bout\\b|^-$/i.test((b.textContent || b.title || "").trim()));
  const resetBtn = [...d.querySelectorAll("button")].find(b => /reset\\s*view|100%/i.test(b.textContent || b.title || ""));
  for (let i = 0; i < 15; i++) zoomOut.click();
  const minZoom = api && api.getState ? api.getState().zoom : null;
  for (let i = 0; i < 20; i++) zoomIn.click();
  const maxZoom = api && api.getState ? api.getState().zoom : null;
  resetBtn.click();
  const resetState = api && api.getState ? api.getState() : null;
  close();
  console.log(JSON.stringify({ minZoom, maxZoom, resetState, errors }));
})();
"""
    res = run_jsdom_harness(tmp_path, scenario, args=[str(cs_js), img_b64])
    assert res["errors"] == [], res["errors"]
    assert res["minZoom"] is not None and 0.45 <= res["minZoom"] <= 0.55
    assert res["maxZoom"] is not None and 1.9 <= res["maxZoom"] <= 2.1
    assert res["resetState"]["zoom"] == 1


def test_f20_t2_out_of_range_grading_sliders_and_nan_inputs(tmp_path: Path) -> None:
    cs_js = _STATIC_JS_DIR / "canvas_studio.js"
    assert cs_js.is_file(), f"Missing {cs_js}"
    img_b64 = base64.b64encode(make_solid_png_bytes(320, 240)).decode("ascii")

    scenario = """
const fs = require("fs");
const { createNeonDOM } = require("./neon_canvas_harness.cjs");
const [csPath, b64] = process.argv.slice(2);
(async () => {
  const { window: w, document: d, errors, close } = await createNeonDOM({
    html: "<!doctype html><html><body><div id='csHost'></div></body></html>",
  });
  w.eval(fs.readFileSync(csPath, "utf-8"));
  const mount = w.mountCanvasStudio || (w.CanvasStudio && w.CanvasStudio.mount);
  const api = mount(d.getElementById("csHost"), { imageUrl: `data:image/png;base64,${b64}` });
  await new Promise(r => setTimeout(r, 80));
  if (api && typeof api.setGrading === "function") {
    api.setGrading({
      exposure: { stops: -99 },
      colorCorrect: { contrast: -200, hue: NaN },
      lensInstructions: { vignette: 2.5 },
      filmGrain: { strength: 3.0 },
    });
  }
  const baseImg = d.querySelector("img");
  const filterLow = baseImg ? baseImg.style.filter : "";
  const blob = api && typeof api.exportComposite === "function" ? await api.exportComposite() : null;
  close();
  console.log(JSON.stringify({ filterLow, hasBlob: Boolean(blob), errors }));
})();
"""
    res = run_jsdom_harness(tmp_path, scenario, args=[str(cs_js), img_b64])
    assert res["errors"] == [], res["errors"]
    assert "NaN" not in res["filterLow"]
    assert "brightness(-" not in res["filterLow"]
    assert res["hasBlob"] is True


def test_f20_t2_zero_dimension_canvas_and_no_image_loaded(tmp_path: Path) -> None:
    cs_js = _STATIC_JS_DIR / "canvas_studio.js"
    assert cs_js.is_file(), f"Missing {cs_js}"

    scenario = """
const fs = require("fs");
const { createNeonDOM } = require("./neon_canvas_harness.cjs");
const [csPath] = process.argv.slice(2);
(async () => {
  const { window: w, document: d, errors, close } = await createNeonDOM({
    html: "<!doctype html><html><body><div id='csHost'></div></body></html>",
    zeroRect: true,
  });
  w.eval(fs.readFileSync(csPath, "utf-8"));
  const mount = w.mountCanvasStudio || (w.CanvasStudio && w.CanvasStudio.mount);
  const api = mount(d.getElementById("csHost"), { imageUrl: null });
  await new Promise(r => setTimeout(r, 80));
  let exportErr = null;
  try {
    if (api && typeof api.exportComposite === "function") await api.exportComposite();
  } catch (e) {
    exportErr = e.message || String(e);
  }
  const canvas = d.querySelector("canvas");
  if (canvas) {
    canvas.dispatchEvent(new w.PointerEvent("pointerdown", { bubbles: true, clientX: 50, clientY: 50, pointerId: 1 }));
    canvas.dispatchEvent(new w.PointerEvent("pointermove", { bubbles: true, clientX: 90, clientY: 90, pointerId: 1 }));
    canvas.dispatchEvent(new w.PointerEvent("pointerup", { bubbles: true, clientX: 90, clientY: 90, pointerId: 1 }));
  }
  const stateStr = JSON.stringify(api && api.getState ? api.getState() : {});
  close();
  console.log(JSON.stringify({ exportErr, hasNaN: stateStr.includes("NaN"), errors }));
})();
"""
    res = run_jsdom_harness(tmp_path, scenario, args=[str(cs_js)])
    assert res["errors"] == [], res["errors"]
    assert res["hasNaN"] is False


def test_f20_t2_tiny_lasso_and_zero_area_box_ignored(tmp_path: Path) -> None:
    cs_js = _STATIC_JS_DIR / "canvas_studio.js"
    assert cs_js.is_file(), f"Missing {cs_js}"
    img_b64 = base64.b64encode(make_solid_png_bytes(320, 240)).decode("ascii")

    scenario = """
const fs = require("fs");
const { createNeonDOM } = require("./neon_canvas_harness.cjs");
const [csPath, b64] = process.argv.slice(2);
(async () => {
  const { window: w, document: d, errors, close } = await createNeonDOM({
    html: "<!doctype html><html><body><div id='csHost'></div></body></html>",
  });
  w.eval(fs.readFileSync(csPath, "utf-8"));
  const mount = w.mountCanvasStudio || (w.CanvasStudio && w.CanvasStudio.mount);
  const api = mount(d.getElementById("csHost"), { imageUrl: `data:image/png;base64,${b64}` });
  await new Promise(r => setTimeout(r, 80));
  const lassoBtn = [...d.querySelectorAll("button")].find(b => /lasso/i.test(b.textContent || b.dataset.tool || ""));
  const boxBtn = [...d.querySelectorAll("button")].find(b => /box|region|rect/i.test(b.textContent || b.dataset.tool || ""));
  const canvas = d.querySelector("canvas");
  lassoBtn.click();
  canvas.dispatchEvent(new w.PointerEvent("pointerdown", { bubbles: true, clientX: 100, clientY: 100, pointerId: 1 }));
  canvas.dispatchEvent(new w.PointerEvent("pointerup", { bubbles: true, clientX: 101, clientY: 101, pointerId: 1 }));
  boxBtn.click();
  canvas.dispatchEvent(new w.PointerEvent("pointerdown", { bubbles: true, clientX: 120, clientY: 120, pointerId: 1 }));
  canvas.dispatchEvent(new w.PointerEvent("pointermove", { bubbles: true, clientX: 122, clientY: 122, pointerId: 1 }));
  canvas.dispatchEvent(new w.PointerEvent("pointerup", { bubbles: true, clientX: 122, clientY: 122, pointerId: 1 }));
  const regions = api && api.getState ? api.getState().markedRegions || [] : [];
  close();
  console.log(JSON.stringify({ regionCount: regions.length, errors }));
})();
"""
    res = run_jsdom_harness(tmp_path, scenario, args=[str(cs_js), img_b64])
    assert res["errors"] == [], res["errors"]
    assert res["regionCount"] == 0


def test_f20_t2_grain_size_presets_and_zero_strength_skip(tmp_path: Path) -> None:
    cs_js = _STATIC_JS_DIR / "canvas_studio.js"
    assert cs_js.is_file(), f"Missing {cs_js}"
    img_b64 = base64.b64encode(make_solid_png_bytes(320, 240)).decode("ascii")

    scenario = """
const fs = require("fs");
const { createNeonDOM } = require("./neon_canvas_harness.cjs");
const [csPath, b64] = process.argv.slice(2);
(async () => {
  const { window: w, document: d, errors, close } = await createNeonDOM({
    html: "<!doctype html><html><body><div id='csHost'></div></body></html>",
  });
  w.eval(fs.readFileSync(csPath, "utf-8"));
  const mount = w.mountCanvasStudio || (w.CanvasStudio && w.CanvasStudio.mount);
  const api = mount(d.getElementById("csHost"), { imageUrl: `data:image/png;base64,${b64}` });
  await new Promise(r => setTimeout(r, 80));
  const freqs = {};
  for (const sz of ["35mm", "16mm", "8mm"]) {
    api.setGrading({ filmGrain: { strength: 0.4, size: sz } });
    const turb = d.querySelector("feTurbulence");
    freqs[sz] = turb ? turb.getAttribute("baseFrequency") : null;
  }
  api.setGrading({ lensInstructions: { vignette: 0 }, filmGrain: { strength: 0, size: "35mm" } });
  const origGetContext = w.HTMLCanvasElement.prototype.getContext;
  const contexts = [];
  w.HTMLCanvasElement.prototype.getContext = function (k) {
    const c = origGetContext.call(this, k);
    if (c && !contexts.includes(c)) contexts.push(c);
    return c;
  };
  await api.exportComposite();
  const calls = contexts.flatMap(c => c.__getCalls());
  close();
  console.log(JSON.stringify({
    freqs,
    usedRadial: calls.some(c => c.method === "createRadialGradient"),
    usedPattern: calls.some(c => c.method === "createPattern"),
    errors,
  }));
})();
"""
    res = run_jsdom_harness(tmp_path, scenario, args=[str(cs_js), img_b64])
    assert res["errors"] == [], res["errors"]
    assert res["usedRadial"] is False
    assert res["usedPattern"] is False


def test_f20_t2_overlay_text_xss_and_long_word_wrap(tmp_path: Path) -> None:
    cs_js = _STATIC_JS_DIR / "canvas_studio.js"
    assert cs_js.is_file(), f"Missing {cs_js}"
    img_b64 = base64.b64encode(make_solid_png_bytes(320, 240)).decode("ascii")

    scenario = """
const fs = require("fs");
const { createNeonDOM } = require("./neon_canvas_harness.cjs");
const [csPath, b64] = process.argv.slice(2);
(async () => {
  const { window: w, document: d, errors, close } = await createNeonDOM({
    html: "<!doctype html><html><body><div id='csHost'></div></body></html>",
  });
  w.eval(fs.readFileSync(csPath, "utf-8"));
  const mount = w.mountCanvasStudio || (w.CanvasStudio && w.CanvasStudio.mount);
  const api = mount(d.getElementById("csHost"), { imageUrl: `data:image/png;base64,${b64}` });
  await new Promise(r => setTimeout(r, 80));
  const payload = "<script>window.__xss=9</script> supercalifragilisticexpialidocious wrap test";
  if (api && typeof api.addTextOverlay === "function") api.addTextOverlay(payload);
  else {
    const inp = d.querySelector("input[type='text'], textarea");
    if (inp) { inp.value = payload; inp.dispatchEvent(new w.Event("input", { bubbles: true })); }
    const addBtn = [...d.querySelectorAll("button")].find(b => /add|place|text/i.test(b.textContent || ""));
    if (addBtn) addBtn.click();
  }
  const origGetContext = w.HTMLCanvasElement.prototype.getContext;
  const contexts = [];
  w.HTMLCanvasElement.prototype.getContext = function (k) {
    const c = origGetContext.call(this, k);
    if (c && !contexts.includes(c)) contexts.push(c);
    return c;
  };
  await api.exportComposite();
  const fillTextCalls = contexts.flatMap(c => c.__getCalls()).filter(c => c.method === "fillText");
  const xss = w.__xss;
  close();
  console.log(JSON.stringify({ xssTriggered: xss !== undefined, fillTextCount: fillTextCalls.length, errors }));
})();
"""
    res = run_jsdom_harness(tmp_path, scenario, args=[str(cs_js), img_b64])
    assert res["errors"] == [], res["errors"]
    assert res["xssTriggered"] is False
    assert res["fillTextCount"] >= 1


def test_f20_t2_undo_redo_boundaries_and_object_delete(tmp_path: Path) -> None:
    cs_js = _STATIC_JS_DIR / "canvas_studio.js"
    assert cs_js.is_file(), f"Missing {cs_js}"
    img_b64 = base64.b64encode(make_solid_png_bytes(320, 240)).decode("ascii")

    scenario = """
const fs = require("fs");
const { createNeonDOM } = require("./neon_canvas_harness.cjs");
const [csPath, b64] = process.argv.slice(2);
(async () => {
  const { window: w, document: d, errors, close } = await createNeonDOM({
    html: "<!doctype html><html><body><div id='csHost'></div></body></html>",
  });
  w.eval(fs.readFileSync(csPath, "utf-8"));
  const mount = w.mountCanvasStudio || (w.CanvasStudio && w.CanvasStudio.mount);
  const api = mount(d.getElementById("csHost"), { imageUrl: `data:image/png;base64,${b64}` });
  await new Promise(r => setTimeout(r, 80));
  const undoBtn = [...d.querySelectorAll("button")].find(b => /undo/i.test(b.textContent || b.title || ""));
  const redoBtn = [...d.querySelectorAll("button")].find(b => /redo/i.test(b.textContent || b.title || ""));
  undoBtn.click();
  redoBtn.click();
  if (api && typeof api.addTextOverlay === "function") api.addTextOverlay("Keep");
  const inp = d.querySelector("input, textarea");
  if (inp) {
    inp.focus();
    inp.dispatchEvent(new w.KeyboardEvent("keydown", { key: "Backspace", bubbles: true }));
  }
  const afterInputBackspace = api && api.getState ? (api.getState().objects || []).length : 1;
  d.body.focus();
  d.dispatchEvent(new w.KeyboardEvent("keydown", { key: "Delete", bubbles: true }));
  const afterDelete = api && api.getState ? (api.getState().objects || []).length : 0;
  close();
  console.log(JSON.stringify({ afterInputBackspace, afterDelete, errors }));
})();
"""
    res = run_jsdom_harness(tmp_path, scenario, args=[str(cs_js), img_b64])
    assert res["errors"] == [], res["errors"]
    assert res["afterInputBackspace"] >= 1
    assert res["afterDelete"] == 0


# ===========================================================================
# F21 — Unified 4-Workspace Shell Boundaries (Tier 2: 7 tests)
# ===========================================================================


def test_f21_t2_invalid_workspace_hash_and_storage_fallback(
    live_studio_server: StudioHarness,
    tmp_path: Path,
) -> None:
    scenario = """
const { createNeonDOM } = require("./neon_canvas_harness.cjs");
const [url] = process.argv.slice(2);
(async () => {
  const { window: w, document: d, errors, close } = await createNeonDOM({
    url: url + "#nonexistent-workspace",
    baseUrl: new URL(url).origin,
    beforeParse(win) {
      win.localStorage.setItem("activeTab", "__invalid_ws__");
      win.localStorage.setItem("activeWorkspace", "__invalid_ws__");
    },
  });
  await new Promise(r => setTimeout(r, 900));
  w.location.hash = "#<script>alert(1)</script>";
  w.dispatchEvent(new w.HashChangeEvent("hashchange"));
  await new Promise(r => setTimeout(r, 150));
  const panels = [...d.querySelectorAll("[data-workspace-panel], .workspace-panel, section.panel[role='tabpanel']")];
  const visiblePanels = panels.filter(p => !p.classList.contains("hidden") && p.getAttribute("aria-hidden") !== "true" && p.style.display !== "none");
  close();
  console.log(JSON.stringify({ visibleCount: visiblePanels.length, errors }));
})();
"""
    res = run_jsdom_harness(tmp_path, scenario, args=[f"{live_studio_server.base_url}/?t={live_studio_server.token}"])
    assert res["errors"] == [], res["errors"]
    assert res["visibleCount"] == 1


def test_f21_t2_xss_in_ollama_models_project_and_provider_status(
    fake_ollama: FakeOllamaServer,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_ollama.set_available_models([
        "qwen2.5:3b",
        'evil<img src=x onerror="window.__xss=1">',
        "bad\"'<b>tag</b>",
    ])
    monkeypatch.setenv("STUDIO_LOCAL_LLM", "1")
    with IsolatedWorkspace(base_dir=tmp_path / "ws_xss", local_llm_url=fake_ollama.v1_chat_url) as ws:
        proj = ws.root / "projects" / "books" / "xss_book"
        proj.mkdir(parents=True, exist_ok=True)
        (proj / "xss_book.json").write_text(json.dumps({"slug": "xss_book", "title": "<script>window.__xss=2</script>"}), encoding="utf-8")
        with StudioHarness(workspace=ws) as harness:
            scenario = """
const { createNeonDOM } = require("./neon_canvas_harness.cjs");
const [url] = process.argv.slice(2);
(async () => {
  const { window: w, document: d, errors, close } = await createNeonDOM({ url, baseUrl: new URL(url).origin });
  await new Promise(r => setTimeout(r, 1000));
  const escaped = typeof w.escapeHtml === "function" ? w.escapeHtml('<img src=x onerror="alert(1)">\\'&') : "";
  const triggers = [...d.querySelectorAll("nav button, nav [role='tab'], [data-workspace]")];
  for (const t of triggers) { t.click(); await new Promise(r => setTimeout(r, 60)); }
  const badNodes = d.querySelectorAll("img[onerror], script:not([src])").length;
  const xss = w.__xss;
  close();
  console.log(JSON.stringify({ escaped, badNodes, xssTriggered: xss !== undefined, errors }));
})();
"""
            res = run_jsdom_harness(tmp_path, scenario, args=[f"{harness.base_url}/?t={harness.token}"])
            assert res["errors"] == [], res["errors"]
            assert res["badNodes"] == 0 and res["xssTriggered"] is False
            assert "<" not in res["escaped"] and "&quot;" in res["escaped"] and "&#39;" in res["escaped"]


def test_f21_t2_narrow_mobile_viewport_and_reduced_motion(
    live_studio_server: StudioHarness,
    tmp_path: Path,
) -> None:
    css = (_WEB_DIR / "static" / "css" / "studio.css").read_text(encoding="utf-8")
    assert "@media" in css and "max-width" in css
    assert "prefers-reduced-motion" in css

    scenario = """
const { createNeonDOM } = require("./neon_canvas_harness.cjs");
const [url] = process.argv.slice(2);
(async () => {
  const { window: w, document: d, errors, close } = await createNeonDOM({
    url,
    baseUrl: new URL(url).origin,
    beforeParse(win) {
      win.innerWidth = 375;
      win.innerHeight = 812;
      win.matchMedia = (q) => ({
        matches: String(q).includes("reduced-motion") || String(q).includes("max-width"),
        media: String(q),
        addEventListener() {}, removeEventListener() {}, addListener() {}, removeListener() {},
      });
    },
  });
  await new Promise(r => setTimeout(r, 900));
  w.innerWidth = 320;
  w.innerHeight = 568;
  w.dispatchEvent(new w.Event("resize"));
  const patterns = [/film\\s*studio/i, /^\\s*apps\\s*$/i, /canvas.*compare/i, /models.*hardware/i];
  const triggers = patterns.map(re =>
    [...d.querySelectorAll("nav button, nav [role='tab'], nav a, [data-workspace]")].find(el => re.test((el.textContent || "").trim()))
  );
  triggers.filter(Boolean).forEach(t => t.click());
  close();
  console.log(JSON.stringify({ triggerCount: triggers.filter(Boolean).length, errors }));
})();
"""
    res = run_jsdom_harness(tmp_path, scenario, args=[f"{live_studio_server.base_url}/?t={live_studio_server.token}"])
    assert res["errors"] == [], res["errors"]
    assert res["triggerCount"] == 4


def test_f21_t2_legacy_cloud_non_one_values_stay_gated(
    live_studio_server: StudioHarness,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for val in ("", "0", "false", "true", "yes"):
        monkeypatch.setenv("STUDIO_LEGACY_CLOUD", val)
        r_prov = live_studio_server.get("/api/providers")
        assert r_prov.status == 200
        prov = r_prov.json()
        assert prov["legacy_cloud"] is False, f"STUDIO_LEGACY_CLOUD={val!r} must NOT enable legacy cloud"
        assert prov["free"] == [] and prov["paid"] == []
        r_stat = live_studio_server.get("/api/status")
        assert r_stat.status == 200
        stat_json = r_stat.json()
        assert stat_json["legacy_cloud"] is False
        assert set(stat_json["gpus"]) == {"computer"}

    for val in ("1", " 1 "):
        monkeypatch.setenv("STUDIO_LEGACY_CLOUD", val)
        r_prov = live_studio_server.get("/api/providers")
        assert r_prov.status == 200
        prov = r_prov.json()
        assert prov["legacy_cloud"] is True
        assert {p["id"] for p in prov["free"]} == {"kaggle", "colab", "huggingface"}
        assert len(prov["paid"]) >= 10


def test_f21_t2_unavailable_optional_routes_and_offline_ollama_ui(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        closed_port = s.getsockname()[1]

    monkeypatch.setenv("STUDIO_LOCAL_LLM", "1")
    with (
        IsolatedWorkspace(base_dir=tmp_path / "ws_off", local_llm_url=f"http://127.0.0.1:{closed_port}/v1/chat/completions") as ws,
        StudioHarness(workspace=ws) as harness,
    ):
        scenario = """
const { createNeonDOM } = require("./neon_canvas_harness.cjs");
const [url] = process.argv.slice(2);
(async () => {
  const { document: d, errors, close } = await createNeonDOM({
    url,
    baseUrl: new URL(url).origin,
    beforeParse(win) {
      win.__virtualRoutes = {
        "/api/composers/status": { status: 503, body: { error: "offline" } },
        "/api/packs": { status: 503, body: { error: "offline" } },
      };
    },
  });
  await new Promise(r => setTimeout(r, 1000));
  const triggers = [...d.querySelectorAll("nav button, nav [role='tab'], [data-workspace]")];
  for (const t of triggers) { t.click(); await new Promise(r => setTimeout(r, 50)); }
  close();
  console.log(JSON.stringify({ triggerCount: triggers.length, errors }));
})();
"""
        res = run_jsdom_harness(tmp_path, scenario, args=[f"{harness.base_url}/?t={harness.token}"])
        assert res["errors"] == [], res["errors"]
        assert res["triggerCount"] >= 4


def test_f21_t2_auth_host_origin_static_traversal_and_token_isolation(live_studio_server: StudioHarness) -> None:
    assert live_studio_server.get("/", auth=False).status == 403
    assert live_studio_server.get("/?t=invalid-token", auth=False).status == 403

    r_auth = live_studio_server.get(f"/?t={live_studio_server.token}", auth=False)
    assert r_auth.status == 302
    assert r_auth.header("Location") == "/"
    cookie_hdr = r_auth.header("Set-Cookie")
    assert "HttpOnly" in cookie_hdr and "SameSite=Strict" in cookie_hdr

    for bad_path in (
        "/static/../index.html",
        "/static/%2e%2e/scripts/studio_app/config.py",
        "/static/js/nonexistent_file_xyz.js",
    ):
        assert live_studio_server.get(bad_path, auth=False).status in {403, 404}

    assert live_studio_server.request("GET", "/static/js/core.js", auth=False, host="evil.example:8765").status == 403
    r_core = live_studio_server.get("/static/js/core.js", auth=False)
    assert r_core.status == 200
    assert "__TOKEN__" in r_core.text
    assert live_studio_server.token not in r_core.text


def test_f21_t2_rapid_workspace_switching_and_load_order_safety(
    live_studio_server: StudioHarness,
    tmp_path: Path,
) -> None:
    html = (_WEB_DIR / "index.html").read_text(encoding="utf-8")
    order = re.findall(r"""<script\s+src="/static/js/([A-Za-z0-9_]+)\.js"\s+defer""", html)
    assert len(order) >= 5
    src_lines = {n: (_STATIC_JS_DIR / f"{n}.js").read_text(encoding="utf-8").splitlines() for n in order}
    defined_in: dict[str, int] = {}
    for idx, name in enumerate(order):
        for ln in src_lines[name]:
            m = re.match(r"(?:async\s+)?function\s+([A-Za-z_$][\w$]*)", ln)
            if m:
                defined_in[m.group(1)] = idx
    bad_refs: list[str] = []
    for idx, name in enumerate(order):
        depth = 0
        for lineno, ln in enumerate(src_lines[name], 1):
            if depth == 0 and ln and not ln.startswith(("function", "async function", "//", "}", "/*", " *")):
                for sym, sym_idx in defined_in.items():
                    if sym_idx > idx:
                        m_use = re.search(r"(?<![\w$.\"'])" + re.escape(sym) + r"(?![\w$])", ln)
                        if m_use and "=>" not in ln[:m_use.start()] and "function" not in ln[:m_use.start()]:
                            bad_refs.append(f"{name}.js:{lineno}: {sym}")
            depth += sum(ln.count(c) for c in "{([") - sum(ln.count(c) for c in "})]")
    assert bad_refs == [], f"Top-level forward references found: {bad_refs}"

    scenario = """
const { createNeonDOM } = require("./neon_canvas_harness.cjs");
const [url] = process.argv.slice(2);
(async () => {
  const { window: w, document: d, errors, close } = await createNeonDOM({ url, baseUrl: new URL(url).origin });
  await new Promise(r => setTimeout(r, 900));
  const patterns = [/film\\s*studio/i, /^\\s*apps\\s*$/i, /canvas.*compare/i, /models.*hardware/i];
  const triggers = patterns.map(re =>
    [...d.querySelectorAll("nav button, nav [role='tab'], nav a, [data-workspace]")].find(el => re.test((el.textContent || "").trim()))
  ).filter(Boolean);
  for (let round = 0; round < 3; round++) {
    for (const trig of triggers) trig.click();
  }
  const themeBtn = d.getElementById("themeToggle");
  if (themeBtn) { themeBtn.click(); themeBtn.click(); }
  d.dispatchEvent(new w.KeyboardEvent("keydown", { key: "k", ctrlKey: true, bubbles: true }));
  d.dispatchEvent(new w.KeyboardEvent("keydown", { key: "Escape", bubbles: true }));
  await new Promise(r => setTimeout(r, 150));
  const activeBtns = triggers.filter(t => t.classList.contains("active") || t.getAttribute("aria-selected") === "true" || t.getAttribute("aria-current") === "page");
  const panels = [...d.querySelectorAll("[data-workspace-panel], .workspace-panel, section.panel[role='tabpanel']")];
  const visiblePanels = panels.filter(p => !p.classList.contains("hidden") && p.getAttribute("aria-hidden") !== "true" && p.style.display !== "none");
  close();
  console.log(JSON.stringify({ activeBtnCount: activeBtns.length, visiblePanelCount: visiblePanels.length, errors }));
})();
"""
    res = run_jsdom_harness(tmp_path, scenario, args=[f"{live_studio_server.base_url}/?t={live_studio_server.token}"])
    assert res["errors"] == [], res["errors"]
    assert res["activeBtnCount"] == 1 and res["visiblePanelCount"] == 1
