"""Tier 2 boundary & adversarial E2E tests for Requirement R1 / Features F1-F4 (24 tests, 6 per feature).

All Neon module imports are deferred inside test functions/runtime helpers so
``STUDIO_RUN_E2E=1 pytest --collect-only`` always succeeds with zero import errors.
"""
from __future__ import annotations

import ast
from collections.abc import Callable, Iterator, Sequence
from contextlib import contextmanager
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import threading
import time
from typing import TYPE_CHECKING, Any

import pytest

if TYPE_CHECKING:
    from e2e.helpers.fake_comfyui import FakeComfyUIServer
    from e2e.helpers.fake_ollama import FakeOllamaServer
    from e2e.helpers.studio_harness import IsolatedWorkspace, StudioHarness

_NEON_ROOT = Path(__file__).resolve().parents[2]
_JS_DIR = _NEON_ROOT / "tests" / "js"


@contextmanager
def _temp_routes(specs: Sequence[tuple[str, str, Callable[[Any], Any]]]) -> Iterator[None]:
    """Register temporary @api.route handlers and restore ROUTES/PATTERN_ROUTES cleanly."""
    from studio_app import api

    saved_routes = {m: dict(r) for m, r in api.ROUTES.items()}
    saved_patterns = {m: list(p) for m, p in api.PATTERN_ROUTES.items()}
    try:
        for method, path, fn in specs:
            api.route(method, path)(fn)
        yield
    finally:
        for m, orig_r in saved_routes.items():
            api.ROUTES[m].clear()
            api.ROUTES[m].update(orig_r)
        for m, orig_p in saved_patterns.items():
            api.PATTERN_ROUTES[m][:] = orig_p


def _run_jsdom_probe(url: str, body_js: str, timeout_s: float = 20.0) -> dict[str, Any]:
    """Execute an inline jsdom script against a live StudioHarness URL and return parsed JSON."""
    node = shutil.which("node")
    if not node:
        pytest.skip("node not installed in PATH")
    script = (
        'const { JSDOM, ResourceLoader, VirtualConsole, CookieJar } = require("jsdom");\n'
        "const url = process.argv[1];\n"
        "const errors = [];\n"
        "const vc = new VirtualConsole();\n"
        'vc.on("jsdomError", e => errors.push("jsdomError: " + (e.detail && e.detail.stack || e.message)));\n'
        'vc.on("error", (...a) => errors.push("console.error: " + a.join(" ").slice(0, 300)));\n'
        "class Loader extends ResourceLoader {\n"
        '  fetch(u, o) { return u.includes("fonts.g") ? Promise.resolve(Buffer.from("")) : super.fetch(u, o); }\n'
        "}\n"
        "const wait = ms => new Promise(r => setTimeout(r, ms));\n"
        "let pendingFetches = 0;\n"
        "JSDOM.fromURL(url, {\n"
        "  beforeParse(w) {\n"
        "    const N = class { observe() {} unobserve() {} disconnect() {} };\n"
        "    w.ResizeObserver = N;\n"
        "    w.IntersectionObserver = N;\n"
        "    w.scrollTo = () => {};\n"
        "    w.Element.prototype.scrollIntoView = () => {};\n"
        "    w.matchMedia = w.matchMedia || (() => ({ matches: false, addEventListener() {}, removeEventListener() {}, addListener() {}, removeListener() {} }));\n"
        "    w.fetch = (u, o) => {\n"
        "      pendingFetches += 1;\n"
        "      return fetch(new URL(u, url).href, o).then(\n"
        "        r => { if (!r.ok) errors.push('HTTP ' + r.status + ' ' + u); return r; },\n"
        "        err => { errors.push('FETCH_ERR ' + u + ': ' + err.message); throw err; }\n"
        "      ).finally(() => { pendingFetches -= 1; });\n"
        "    };\n"
        "  },\n"
        '  runScripts: "dangerously",\n'
        "  resources: new Loader(),\n"
        "  pretendToBeVisual: true,\n"
        "  virtualConsole: vc,\n"
        "  cookieJar: new CookieJar(),\n"
        "}).then(async dom => {\n"
        "  const w = dom.window;\n"
        "  const d = w.document;\n"
        "  w.HTMLMediaElement.prototype.play = () => Promise.resolve();\n"
        "  w.HTMLMediaElement.prototype.load = () => {};\n"
        "  const deadline = Date.now() + 8000;\n"
        "  while (Date.now() < deadline) {\n"
        "    let stReady = false;\n"
        '    try { stReady = w.eval("typeof ST !== \'undefined\' && ST !== null") && pendingFetches === 0; } catch (_) {}\n'
        "    if (stReady) break;\n"
        "    await wait(50);\n"
        "  }\n"
        "  await wait(150);\n"
        f"{body_js}\n"
        "}).catch(err => {\n"
        '  console.log(JSON.stringify({ errors: ["load failed: " + (err && err.stack || err)] }));\n'
        "  process.exit(1);\n"
        "});\n"
    )
    proc = subprocess.run(
        [node, "-e", script, url],
        cwd=str(_JS_DIR),
        capture_output=True,
        text=True,
        timeout=timeout_s,
        check=False,
    )
    assert proc.returncode == 0, f"jsdom probe failed (rc={proc.returncode}): stdout={proc.stdout!r} stderr={proc.stderr!r}"
    lines = [line.strip() for line in proc.stdout.splitlines() if line.strip()]
    assert lines, f"jsdom probe produced no JSON output: stderr={proc.stderr!r}"
    parsed: dict[str, Any] = json.loads(lines[-1])
    return parsed


# ---------------------------------------------------------------------------
# Feature F1 Boundaries — GPU Lease Arbitrator (6 tests)
# ---------------------------------------------------------------------------


def test_t2_f1_48g_exact_threshold_42gb_and_42_001_ieee754_pairs(
    fake_ollama: FakeOllamaServer,
    full_48g_profile: dict[str, Any],
    isolated_workspace: IsolatedWorkspace,
) -> None:
    from local_runners.gpu_lease import LeaseManager

    fake_ollama.load_model("qwen2.5:32b", size_vram=20 * 2**30)
    mgr = LeaseManager(ollama_url=fake_ollama.base_url)

    for active_gb, media_gb in ((20.0, 22.0), (18.1, 23.9), (0.0, 42.0), (42.0, 0.0)):
        res = mgr.acquire_media_lease(media_gb, active_llm_gb=active_gb, profile=full_48g_profile)
        assert res.evicted_ollama is False, f"Unexpected eviction at {active_gb} + {media_gb}"
        assert fake_ollama.get_evictions() == []

    res_over = mgr.acquire_media_lease(22.001, active_llm_gb=20.0, profile=full_48g_profile)
    assert res_over.evicted_ollama is True
    assert res_over.evicted_models == ["qwen2.5:32b"]
    assert fake_ollama.get_loaded_models() == []


def test_t2_f1_negative_nan_inf_vram_and_cpu_offloaded_ps_records(
    fake_ollama: FakeOllamaServer,
    full_48g_profile: dict[str, Any],
    isolated_workspace: IsolatedWorkspace,
) -> None:
    from local_runners.gpu_lease import LeaseManager

    fake_ollama.set_loaded_models([{"name": "cpu_only:3b", "size": 2 * 2**30, "size_vram": 0}])
    mgr = LeaseManager(ollama_url=fake_ollama.base_url)

    r_neg = mgr.acquire_media_lease(-5.0, active_llm_gb=-1.0, profile=full_48g_profile)
    assert r_neg.active_llm_gb == 0.0
    assert r_neg.media_vram_gb == 0.0
    assert r_neg.evicted_ollama is False

    r_nan = mgr.acquire_media_lease(float("nan"), active_llm_gb=float("nan"), profile=full_48g_profile)
    assert r_nan.active_llm_gb == 0.0
    assert r_nan.media_vram_gb == 0.0
    assert r_nan.evicted_ollama is False

    r_ps = mgr.acquire_media_lease(4.0, active_llm_gb=None, profile=full_48g_profile)
    assert r_ps.active_llm_gb == 0.0
    assert r_ps.evicted_ollama is False

    r_inf = mgr.acquire_media_lease(float("inf"), active_llm_gb=0.0, profile=full_48g_profile)
    assert r_inf.evicted_ollama is True
    assert r_inf.evicted_models == ["cpu_only:3b"]


def test_t2_f1_mac_8g_lite_zero_media_vram_and_ollama_model_fallback(
    fake_ollama: FakeOllamaServer,
    mac_8g_lite_profile: dict[str, Any],
    isolated_workspace: IsolatedWorkspace,
) -> None:
    from local_runners.gpu_lease import LeaseManager

    mgr = LeaseManager(ollama_url=fake_ollama.base_url)

    r_empty = mgr.acquire_media_lease(0.0, ollama_model=None, profile=mac_8g_lite_profile)
    assert r_empty.evicted_ollama is False

    r_hint = mgr.acquire_media_lease(0.0, ollama_model="llama3.2:3b", profile=mac_8g_lite_profile)
    assert r_hint.evicted_ollama is True
    assert r_hint.evicted_models == ["llama3.2:3b"]

    fake_ollama.load_model("qwen2.5:3b", size_vram=2 * 2**30)
    r_loaded = mgr.acquire_media_lease(0.0, profile=mac_8g_lite_profile)
    assert r_loaded.evicted_ollama is True
    assert r_loaded.evicted_models == ["qwen2.5:3b"]


def test_t2_f1_hostile_ollama_and_comfyui_errors_and_timeouts_never_raise(
    fake_ollama: FakeOllamaServer,
    fake_comfyui: FakeComfyUIServer,
    mac_8g_lite_profile: dict[str, Any],
    isolated_workspace: IsolatedWorkspace,
) -> None:
    from local_runners.gpu_lease import LeaseManager

    fake_ollama.set_error("/api/ps", 500)
    fake_ollama.set_error("/api/generate", 503)
    fake_comfyui.set_error("/free", 500)

    mgr = LeaseManager(comfyui_url=fake_comfyui.base_url, ollama_url=fake_ollama.base_url)
    r1 = mgr.acquire_media_lease(4.0, free_comfyui=True, ollama_model="qwen2.5:3b", profile=mac_8g_lite_profile)
    assert r1.evicted_ollama is False
    assert r1.comfyui_freed is False
    assert len(r1.warnings) >= 2

    fake_ollama.reset()
    fake_ollama.set_error("/api/ps", 200, body=b"{broken")
    r2 = mgr.acquire_media_lease(4.0, profile=mac_8g_lite_profile)
    assert r2.evicted_ollama is False
    assert any("ps" in w.lower() or "json" in w.lower() or "expecting" in w.lower() for w in r2.warnings)

    dead_mgr = LeaseManager(comfyui_url="http://127.0.0.1:9", ollama_url="http://127.0.0.1:9", timeout=0.2)
    r3 = dead_mgr.acquire_media_lease(4.0, free_comfyui=True, ollama_model="qwen2.5:3b", profile=mac_8g_lite_profile)
    assert r3.evicted_ollama is False
    assert r3.comfyui_freed is False
    assert len(r3.warnings) >= 2


def test_t2_f1_url_origin_rejects_non_http_and_schemeless_schemes(
    isolated_workspace: IsolatedWorkspace,
) -> None:
    from local_runners.gpu_lease import LeaseManager, resolve_comfyui_url, resolve_ollama_url

    for bad in ("file:///etc/passwd", "file:/etc/passwd", "javascript:alert(1)", "ftp://127.0.0.1:11434"):
        with pytest.raises(ValueError):
            resolve_ollama_url(bad)
        with pytest.raises(ValueError):
            resolve_comfyui_url(bad)

    with pytest.raises(ValueError):
        LeaseManager()._http_json("GET", "file:///etc/passwd")

    assert resolve_ollama_url("127.0.0.1:11434") == "http://127.0.0.1:11434"
    assert resolve_ollama_url("[::1]:11434") == "http://[::1]:11434"


def test_t2_f1_concurrent_with_leases_serialize_model_key_and_no_mid_lease_free(
    fake_ollama: FakeOllamaServer,
    fake_comfyui: FakeComfyUIServer,
    full_48g_profile: dict[str, Any],
    isolated_workspace: IsolatedWorkspace,
) -> None:
    from local_runners.gpu_lease import LeaseManager

    mgr = LeaseManager(comfyui_url=fake_comfyui.base_url, ollama_url=fake_ollama.base_url)
    num_threads = 8
    barrier = threading.Barrier(num_threads)
    lock = threading.Lock()
    active_in_with = 0
    max_concurrent = 0
    mid_lease_changes: list[tuple[int, int]] = []
    errors: list[str] = []

    def _worker(idx: int) -> None:
        nonlocal active_in_with, max_concurrent
        key = "flux" if idx % 2 == 0 else "wan22"
        try:
            barrier.wait(timeout=5.0)
            with mgr.acquire_media_lease(12.0, active_llm_gb=10.0, model_key=key, profile=full_48g_profile):
                with lock:
                    active_in_with += 1
                    max_concurrent = max(max_concurrent, active_in_with)
                before_free = len(fake_comfyui.free_calls)
                time.sleep(0.02)
                after_free = len(fake_comfyui.free_calls)
                if before_free != after_free:
                    with lock:
                        mid_lease_changes.append((before_free, after_free))
                with lock:
                    active_in_with -= 1
        except Exception as exc:
            with lock:
                errors.append(repr(exc))

    threads = [threading.Thread(target=_worker, args=(i,)) for i in range(num_threads)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=15.0)
        assert not t.is_alive()

    assert errors == []
    assert max_concurrent == 1
    assert mid_lease_changes == []


# ---------------------------------------------------------------------------
# Feature F2 Boundaries — Legacy Cloud Backend Gating (6 tests)
# ---------------------------------------------------------------------------


def test_t2_f2_studio_legacy_cloud_strict_value_parsing(
    live_studio_server: StudioHarness,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for val, expected in (("", False), ("0", False), ("true", False), ("yes", False), ("1", True), (" 1 ", True)):
        monkeypatch.setenv("STUDIO_LEGACY_CLOUD", val)
        prov = live_studio_server.get("/api/providers").json()
        stat = live_studio_server.get("/api/status").json()
        assert prov["legacy_cloud"] is expected, f"Failed for STUDIO_LEGACY_CLOUD={val!r}"
        assert stat["legacy_cloud"] is expected, f"Failed for STUDIO_LEGACY_CLOUD={val!r}"
        if not expected:
            assert prov["free"] == []
            assert prov["paid"] == []
            assert set(stat["gpus"]) == {"computer"}


def test_t2_f2_providers_json_integrity_and_paid_non_selectable(
    live_studio_server: StudioHarness,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("STUDIO_LEGACY_CLOUD", "1")
    d = live_studio_server.get("/api/providers").json()

    comp_ids = {p["id"] for p in d["computer"]}
    free_ids = {p["id"] for p in d["free"]}
    paid_ids = [p["id"] for p in d["paid"]]

    assert len(paid_ids) == len(set(paid_ids))
    assert set(paid_ids).isdisjoint(comp_ids | free_ids)
    for row in d["paid"]:
        assert row["proven"] is False
        assert row["selectable"] is False
        assert str(row["url"]).startswith("https://")
    for row in d["computer"] + d["free"]:
        assert row["proven"] is True
        assert row["selectable"] is True


def test_t2_f2_status_blockers_filter_leaves_only_computer_when_gated(
    live_studio_server: StudioHarness,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("STUDIO_LEGACY_CLOUD", raising=False)
    st = live_studio_server.get("/api/status").json()

    for model_svcs in st["blockers"].values():
        assert set(model_svcs.keys()) <= {"computer"}
    assert set(st["gpu_blockers"].keys()) <= {"computer"}


def test_t2_f2_core_js_fillgpus_handles_empty_gpus_and_null_st(
    live_studio_server: StudioHarness,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("STUDIO_LEGACY_CLOUD", raising=False)
    url = f"{live_studio_server.base_url}/?t={live_studio_server.token}"
    res = _run_jsdom_probe(
        url,
        "w.eval('ST = { gpus: { computer: [] }, gpu_blockers: {}, tools: {}, projects: [], library: [] }; fillGpus();');\n"
        'const gpuAfterEmpty = d.getElementById("gpu").value;\n'
        "w.eval('ST = null;');\n"
        'const kr = d.querySelector(\'input[name="svc"][value="kaggle"]\');\n'
        'if (kr) { kr.checked = true; kr.dispatchEvent(new w.Event("change", { bubbles: true })); }\n'
        "console.log(JSON.stringify({ errors, gpuAfterEmpty }));\n"
        "process.exit(0);\n",
    )
    assert res["errors"] == []
    assert res["gpuAfterEmpty"] == ""


def test_t2_f2_core_js_bounces_kaggle_radio_back_to_computer_when_gated(
    live_studio_server: StudioHarness,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("STUDIO_LEGACY_CLOUD", raising=False)
    url = f"{live_studio_server.base_url}/?t={live_studio_server.token}"
    res = _run_jsdom_probe(
        url,
        'const kr = d.querySelector(\'input[name="svc"][value="kaggle"]\');\n'
        "let hasKaggleRadio = !!kr;\n"
        "if (kr) {\n"
        "  kr.checked = true;\n"
        '  kr.dispatchEvent(new w.Event("change", { bubbles: true }));\n'
        "}\n"
        'const checked = d.querySelector(\'input[name="svc"]:checked\');\n'
        'console.log(JSON.stringify({ errors, hasKaggleRadio, svcChecked: checked ? checked.value : "" }));\n'
        "process.exit(0);\n",
    )
    assert res["errors"] == []
    assert res["hasKaggleRadio"] is True
    assert res["svcChecked"] == "computer"


def test_t2_f2_legacy_endpoints_still_enforce_validation_when_gated(
    live_studio_server: StudioHarness,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("STUDIO_LEGACY_CLOUD", raising=False)

    r_bad_look = live_studio_server.get("/api/suggest?look=bad_look&service=kaggle&gpu=NvidiaTeslaT4")
    r_bad_gpu = live_studio_server.get("/api/suggest?look=live_action&service=kaggle&gpu=NoSuchGpu")
    r_bad_ref = live_studio_server.get("/api/kernel_status?ref=invalid")

    for resp in (r_bad_look, r_bad_gpu, r_bad_ref):
        assert resp.status == 400
        body = resp.json()
        assert isinstance(body.get("error"), str) and body["error"]


# ---------------------------------------------------------------------------
# Feature F3 Boundaries — Phase 1 Fixes & Routing (6 tests)
# ---------------------------------------------------------------------------


def test_t2_f3_api_rejects_encoded_and_literal_path_traversal_segments(
    live_studio_server: StudioHarness,
) -> None:
    calls = 0

    def _param(r: Any) -> dict[str, Any]:
        nonlocal calls
        calls += 1
        return {"id": r.p("item_id")}

    def _exact(r: Any) -> dict[str, Any]:
        return {"exact": True}

    specs = [
        ("GET", "/api/_e2e_f3_sec/<item_id>", _param),
        ("GET", "/api/_e2e_f3_sec/status", _exact),
    ]
    with _temp_routes(specs):
        bad_paths = (
            "/api/_e2e_f3_sec/foo%2Fbar",
            "/api/_e2e_f3_sec/..%2F..%2Fetc%2Fpasswd",
            "/api/_e2e_f3_sec/..%5C..%5Cwin",
            "/api/_e2e_f3_sec/..",
            "/api/_e2e_f3_sec/.",
            "/api/_e2e_f3_sec/bad%00id",
            "/api/_e2e_f3_sec/",
        )
        for p in bad_paths:
            resp = live_studio_server.get(p)
            assert resp.status == 404, f"Expected 404 on {p}, got {resp.status}"
            assert resp.json() == {"error": "not found"}

    assert calls == 0


def test_t2_f3_api_percent_encoded_exact_route_cannot_bypass_to_param_route(
    live_studio_server: StudioHarness,
) -> None:
    def _param(r: Any) -> dict[str, Any]:
        return {"exact": False, "id": r.p("item_id")}

    def _exact(r: Any) -> dict[str, Any]:
        return {"exact": True}

    # Register param route BEFORE exact route to verify exact takes precedence after decoding.
    specs = [
        ("GET", "/api/_e2e_f3_sec/<item_id>", _param),
        ("GET", "/api/_e2e_f3_sec/status", _exact),
    ]
    with _temp_routes(specs):
        r_bypass = live_studio_server.get("/api/_e2e_f3_sec/st%61tus")
        r_ok = live_studio_server.get("/api/_e2e_f3_sec/my%20app")

    assert r_bypass.status == 200
    assert r_bypass.json() == {"exact": True}
    assert r_ok.status == 200
    assert r_ok.json() == {"exact": False, "id": "my app"}


def test_t2_f3_api_duplicate_param_conflict_and_regex_metachar_guards() -> None:
    from studio_app import api

    saved_routes = {m: dict(r) for m, r in api.ROUTES.items()}
    saved_patterns = {m: list(p) for m, p in api.PATTERN_ROUTES.items()}
    try:
        with pytest.raises(RuntimeError):
            api.route("GET", "/api/_e2e_dup/<a>/x/<a>")(lambda r: {})

        api.route("GET", "/api/_e2e_conf/<id>")(lambda r: {})
        with pytest.raises(RuntimeError):
            api.route("GET", "/api/_e2e_conf/<app_id>")(lambda r: {})

        api.route("GET", "/api/_e2e_v1.0/items/<id>")(lambda r: {"ok": r.p("id")})
        fn_match, params = api.resolve("GET", "/api/_e2e_v1.0/items/abc")
        fn_miss, miss_params = api.resolve("GET", "/api/_e2e_v1X0/items/abc")

        assert fn_match is not None
        assert params == {"id": "abc"}
        assert fn_miss is None
        assert miss_params == {}
    finally:
        for m, orig_r in saved_routes.items():
            api.ROUTES[m].clear()
            api.ROUTES[m].update(orig_r)
        for m, orig_p in saved_patterns.items():
            api.PATTERN_ROUTES[m][:] = orig_p


def test_t2_f3_handler_404_before_413_and_invalid_body_bounds(
    live_studio_server: StudioHarness,
) -> None:
    # 1) Unknown POST route with huge Content-Length and 0 body bytes returns 404 immediately
    raw_req = (
        "POST /api/_no_such_route_e2e HTTP/1.1\r\n"
        f"Host: 127.0.0.1:{live_studio_server.port}\r\n"
        f"X-Studio-Token: {live_studio_server.token}\r\n"
        "Content-Length: 99999999\r\n"
        "Connection: close\r\n\r\n"
    ).encode("ascii")
    with socket.create_connection(("127.0.0.1", live_studio_server.port), timeout=3.0) as sock:
        sock.sendall(raw_req)
        chunks: list[bytes] = []
        while True:
            part = sock.recv(4096)
            if not part:
                break
            chunks.append(part)
    raw_resp = b"".join(chunks).decode("latin-1", errors="replace")
    assert "404" in raw_resp.splitlines()[0], f"Expected 404 before 413, got: {raw_resp!r}"

    # 2) Negative Content-Length -> 400
    r_neg = live_studio_server.post("/api/plan", raw_body=b"{}", headers={"Content-Length": "-5"})
    assert r_neg.status == 400

    # 3) Body > MAX_JSON_BODY (8 MiB) -> 413
    r_big = live_studio_server.post("/api/plan", raw_body=b"{}", headers={"Content-Length": "8388609"})
    assert r_big.status == 413

    # 4) Non-object JSON body -> 400
    r_list = live_studio_server.post("/api/plan", raw_body=b"[1,2,3]")
    assert r_list.status == 400

    # 5) Unauthenticated POST -> 403
    r_unauth = live_studio_server.post("/api/plan", {}, auth=False)
    assert r_unauth.status == 403


def test_t2_f3_load_optional_routes_propagates_broken_module_errors(tmp_path: Path) -> None:
    from studio_app import handler

    empty_pkg = tmp_path / "e2e_empty"
    empty_pkg.mkdir()
    (empty_pkg / "__init__.py").write_text("", encoding="utf-8")

    bad_imp_pkg = tmp_path / "e2e_bad_imp"
    bad_imp_pkg.mkdir()
    (bad_imp_pkg / "__init__.py").write_text("", encoding="utf-8")
    (bad_imp_pkg / "apps_routes.py").write_text("import nonexistent_pkg_xyz_999\n", encoding="utf-8")

    bad_syn_pkg = tmp_path / "e2e_bad_syn"
    bad_syn_pkg.mkdir()
    (bad_syn_pkg / "__init__.py").write_text("", encoding="utf-8")
    (bad_syn_pkg / "compose_routes.py").write_text("def broken(:\n    pass\n", encoding="utf-8")

    saved_path = list(sys.path)
    try:
        sys.path.insert(0, str(tmp_path))
        assert handler.load_optional_routes(package="e2e_empty") == []
        with pytest.raises(ModuleNotFoundError):
            handler.load_optional_routes(package="e2e_bad_imp")
        with pytest.raises(SyntaxError):
            handler.load_optional_routes(package="e2e_bad_syn")
    finally:
        sys.path[:] = saved_path
        for prefix in ("e2e_empty", "e2e_bad_imp", "e2e_bad_syn"):
            for mod_name in [k for k in sys.modules if k == prefix or k.startswith(prefix + ".")]:
                sys.modules.pop(mod_name, None)


def test_t2_f3_blackwell_offload_40gb_boundary_and_platform_guard(tmp_path: Path) -> None:
    import run_local_model as rl

    assert rl.gpu_optimizations("RTX 5090", "12.0", 39.9)["allow_cpu_offload"] is True
    assert rl.gpu_optimizations("RTX 5090", "12.0", 40.0)["allow_cpu_offload"] is False
    assert rl.is_blackwell_gpu("Apple M2", "MPS") is False

    prob = rl.gpu_problem(
        [{"name": "Apple M2", "vendor": "Apple", "gb": 8.0, "shared": True, "cap": "MPS", "nvidia_ready": False, "rocm_ready": False, "mps_ready": True}],
        platform="win32",
    )
    assert prob is not None and "win32" in prob

    nb_path = tmp_path / "indent_nb.ipynb"
    nb_path.write_text(
        json.dumps(
            {
                "cells": [
                    {
                        "cell_type": "code",
                        "source": [
                            "if True:\n",
                            "    # pipe.enable_model_cpu_offload()\n",
                            "    pipe.enable_sequential_cpu_offload( )\n",
                        ],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    script, _ = rl.to_script(
        nb_path,
        1,
        1,
        "all_shots.csv",
        tmp_path,
        tmp_path,
        rl.gpu_optimizations("RTX 5090", "12.0", 40.0),
    )
    compile(script, "indent_nb.py", "exec")
    assert "    # pipe.enable_model_cpu_offload()" in script
    assert "    pipe.to(_device)" in script


# ---------------------------------------------------------------------------
# Feature F4 Boundaries — Hardware Matrix & CI/JS Baseline Gates (6 tests)
# ---------------------------------------------------------------------------


def test_t2_f4_local_llm_status_empty_models_and_unreachable_url(
    fake_ollama: FakeOllamaServer,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from e2e.helpers.studio_harness import IsolatedWorkspace as _IsoWs

    monkeypatch.setenv("STUDIO_LOCAL_LLM", "1")
    fake_ollama.set_available_models([])
    with _IsoWs(base_dir=tmp_path / "ws_empty", local_llm_url=fake_ollama.v1_chat_url):
        from studio_app import llm

        st_empty = llm.local_llm_status(force=True)
        assert st_empty["ready"] is False
        assert "no models yet" in st_empty["reason"]

    with _IsoWs(base_dir=tmp_path / "ws_dead", local_llm_url="http://127.0.0.1:9/v1/chat/completions"):
        from studio_app import llm

        st_dead = llm.local_llm_status(force=True)
        assert st_dead["ready"] is False
        assert "no local model server answered" in st_dead["reason"]


def test_t2_f4_gpu_profile_mac_8g_vs_16g_vram_tier_boundary(tmp_path: Path) -> None:
    if sys.platform != "darwin":
        pytest.skip("darwin-specific CLI probe (system_profiler/sysctl)")

    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(parents=True, exist_ok=True)
    sp = bin_dir / "system_profiler"
    sp.write_text(
        f"#!{sys.executable}\n"
        "import json\n"
        'print(json.dumps({"SPDisplaysDataType": [{"sppci_model": "Apple M2", "spdisplays_vendor": "sppci_vendor_Apple", "spdisplays_vram_shared": "spdisplays_yes"}]}))\n',
        encoding="utf-8",
    )
    sp.chmod(0o755)
    sysctl = bin_dir / "sysctl"
    sysctl.chmod(0o755) if sysctl.exists() else None

    results: dict[int, dict[str, Any]] = {}
    for mem_gb in (8, 16):
        sysctl.write_text(f"#!{sys.executable}\nprint({mem_gb * 2**30})\n", encoding="utf-8")
        sysctl.chmod(0o755)
        env = dict(os.environ)
        env["PATH"] = f"{bin_dir}{os.pathsep}{env.get('PATH', '')}"
        env["PYTHONPATH"] = str(_NEON_ROOT / "scripts")
        proc = subprocess.run(
            [sys.executable, "-c", "import json; from studio_app import gpus; print(json.dumps(gpus.gpu_profile()))"],
            cwd=str(_NEON_ROOT),
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )
        assert proc.returncode == 0, f"subprocess failed for {mem_gb} GB: {proc.stderr}"
        results[mem_gb] = json.loads(proc.stdout.strip())

    assert results[8]["tier"] == "mac_8g_lite"
    assert results[8]["supports_local_video"] is False
    assert results[8]["default_image_backend"] == "sd_cli"

    assert results[16]["tier"] == "standard_gpu"
    assert results[16]["supports_local_video"] is False
    assert results[16]["default_video_backend"] == "none"


def test_t2_f4_mem_gb_and_gpu_text_malformed_and_boundary_inputs() -> None:
    import run_local_model as rl

    assert rl._mem_gb("0 MB") == 0.0
    assert rl._mem_gb("512 MB") == 0.5
    assert rl._mem_gb("1.5 TB") == 1536.0
    assert rl._mem_gb("") is None
    assert rl._mem_gb("abc") is None
    assert rl._mem_gb(None) is None

    assert rl.gpu_text({"name": "Plain GPU", "gb": None, "shared": False}) == "Plain GPU"
    assert rl.gpu_text({"name": "Apple M2", "gb": 8, "shared": True, "mps_ready": True}) == "Apple M2 (8 GB shared, Metal MPS)"
    assert rl.gpu_text({"name": "AMD RX 7900", "gb": 24, "shared": False, "rocm_ready": True}) == "AMD RX 7900 (24 GB, ROCm, experimental)"


def test_t2_f4_static_assets_csp_headers_and_traversal_defense(live_studio_server: StudioHarness) -> None:
    r_idx = live_studio_server.get("/", headers={"Cookie": f"studio_token={live_studio_server.token}"}, auth=False)
    assert r_idx.status == 200
    assert "default-src 'self'" in r_idx.header("Content-Security-Policy")
    assert r_idx.header("X-Content-Type-Options") == "nosniff"
    assert r_idx.header("Referrer-Policy") == "no-referrer"

    for asset in ("/static/js/core.js", "/static/js/providers.js"):
        r_js = live_studio_server.get(asset)
        assert r_js.status == 200
        assert "charset=utf-8" in r_js.header("Content-Type").lower()

    for bad_path in ("/static/../scripts/studio_app/api.py", "/static/%2e%2e/scripts/studio_app/api.py"):
        r_trav = live_studio_server.get(bad_path)
        assert r_trav.status == 404

    r_host = live_studio_server.request("GET", "/static/js/core.js", host="evil.example")
    assert r_host.status == 403


def test_t2_f4_e2e_test_files_have_zero_top_level_neon_imports() -> None:
    neon_roots = {"studio_app", "local_runners", "run_local_model", "local_audio", "bookkit", "layout", "model_advisor"}
    e2e_dir = _NEON_ROOT / "tests" / "e2e"
    target_files = [
        e2e_dir / "conftest.py",
        e2e_dir / "test_infra_selfcheck.py",
        e2e_dir / "test_tier1_r1_hardware_lease.py",
        e2e_dir / "test_tier2_r1_boundaries.py",
        e2e_dir / "test_tier1_r2_runners_packs_audio.py",
        e2e_dir / "test_tier2_r2_boundaries.py",
    ]
    for path in target_files:
        if not path.is_file():
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for stmt in tree.body:
            if isinstance(stmt, ast.If) and isinstance(stmt.test, ast.Name) and stmt.test.id == "TYPE_CHECKING":
                continue
            if isinstance(stmt, ast.Import):
                for alias in stmt.names:
                    top = alias.name.split(".", 1)[0]
                    assert top not in neon_roots, f"{path.name} has top-level import of {alias.name}"
            elif isinstance(stmt, ast.ImportFrom) and stmt.module:
                top = stmt.module.split(".", 1)[0]
                assert top not in neon_roots, f"{path.name} has top-level import from {stmt.module}"


def test_t2_f4_js_package_lock_and_jsdom_constructor_parity() -> None:
    pkg = json.loads((_JS_DIR / "package.json").read_text(encoding="utf-8"))
    jsdom_pkg = json.loads((_JS_DIR / "node_modules" / "jsdom" / "package.json").read_text(encoding="utf-8"))
    expected_ver = str((pkg.get("dependencies") or pkg.get("devDependencies") or {})["jsdom"]).lstrip("^~")
    assert jsdom_pkg["version"] == expected_ver

    node = shutil.which("node")
    assert node is not None
    proc = subprocess.run(
        [node, "-e", "const {JSDOM}=require('jsdom'); const d=new JSDOM('<p>ok</p>'); if(d.window.document.querySelector('p').textContent!=='ok') process.exit(1);"],
        cwd=str(_JS_DIR),
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, f"jsdom constructor check failed: {proc.stderr}"
