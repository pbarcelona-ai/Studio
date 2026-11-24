"""Tier 1 E2E tests for Requirement R1 / Features F1-F4 (24 tests, 6 per feature).

All Neon module imports are deferred inside test functions/runtime helpers so
``STUDIO_RUN_E2E=1 pytest --collect-only`` always succeeds with zero import errors.
"""
from __future__ import annotations

from collections.abc import Callable, Iterator, Sequence
from contextlib import contextmanager
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
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


def _seed_minimal_book(ws_root: Path, slug: str) -> Path:
    book_dir = ws_root / "projects" / "books" / slug
    book_dir.mkdir(parents=True, exist_ok=True)
    (book_dir / "chapters.json").write_text(json.dumps({"chapters": [{"number": 1, "title": "Ch 1", "text": "Once upon a time."}]}), encoding="utf-8")
    (book_dir / "movies.json").write_text(json.dumps({"shots": [{"id": 1, "rows": [1, 1], "first_chapter": 1, "last_chapter": 1, "clips": 1, "est_seconds": 5}]}), encoding="utf-8")
    (book_dir / "all_shots.csv").write_text(
        "shot,chapter,scene,prompt,narration,lines_json,duration_s\n"
        '1,1,1,"A neon alley at dusk","Hello world","[]",4\n',
        encoding="utf-8",
    )
    (book_dir / "audio_shots.csv").write_text(
        'shot,chapter,narration,lines_json\n1,1,"Hello world","[]"\n',
        encoding="utf-8",
    )
    return book_dir


def _tool_bin(name: str) -> str:
    candidate = Path(sys.executable).with_name(name)
    if candidate.is_file():
        return str(candidate)
    found = shutil.which(name)
    if found:
        return found
    pytest.fail(f"Required dev tool {name!r} not found next to {sys.executable} or in PATH")


# ---------------------------------------------------------------------------
# Feature F1 — GPU Lease Arbitrator (6 tests)
# ---------------------------------------------------------------------------


def test_t1_f1_mac_8g_lite_strict_evicts_all_loaded_ollama_models(
    fake_ollama: FakeOllamaServer,
    mac_8g_lite_profile: dict[str, Any],
    isolated_workspace: IsolatedWorkspace,
) -> None:
    from local_runners.gpu_lease import LeaseManager, LeaseResult

    fake_ollama.load_model("qwen2.5:3b", size_vram=2 * 2**30)
    fake_ollama.load_model("gemma3:4b", size_vram=3 * 2**30)

    mgr = LeaseManager(ollama_url=fake_ollama.base_url)
    res = mgr.acquire_media_lease(media_vram_gb=2.5, profile=mac_8g_lite_profile)

    assert isinstance(res, LeaseResult)
    assert res.owner == "media"
    assert res.tier == "mac_8g_lite"
    assert res.threshold_gb == 0.0
    assert res.evicted_ollama is True
    assert set(res.evicted_models) == {"qwen2.5:3b", "gemma3:4b"}
    assert res.warnings == []
    assert fake_ollama.get_loaded_models() == []
    evictions = fake_ollama.get_evictions()
    assert len(evictions) == 2
    assert all(ev["keep_alive"] == 0 for ev in evictions)


def test_t1_f1_full_48g_keeps_ollama_resident_under_42gb_threshold(
    fake_ollama: FakeOllamaServer,
    full_48g_profile: dict[str, Any],
    isolated_workspace: IsolatedWorkspace,
) -> None:
    from local_runners.gpu_lease import LeaseManager

    fake_ollama.load_model("qwen2.5:14b", size_vram=10 * 2**30)

    mgr = LeaseManager(ollama_url=fake_ollama.base_url)
    res = mgr.acquire_media_lease(media_vram_gb=24.0, active_llm_gb=None, profile=full_48g_profile)

    assert res.tier == "full_48g"
    assert res.threshold_gb == 42.0
    assert res.active_llm_gb == pytest.approx(10.0, rel=1e-2)
    assert res.evicted_ollama is False
    assert res.evicted_models == []
    assert fake_ollama.get_evictions() == []
    assert len(fake_ollama.get_loaded_models()) == 1


def test_t1_f1_full_48g_evicts_ollama_above_42gb_threshold(
    fake_ollama: FakeOllamaServer,
    full_48g_profile: dict[str, Any],
    isolated_workspace: IsolatedWorkspace,
) -> None:
    from local_runners.gpu_lease import LeaseManager

    fake_ollama.load_model("qwen2.5:32b", size_vram=20 * 2**30)

    mgr = LeaseManager(ollama_url=fake_ollama.base_url)
    res = mgr.acquire_media_lease(media_vram_gb=24.0, active_llm_gb=None, profile=full_48g_profile)

    assert res.evicted_ollama is True
    assert res.evicted_models == ["qwen2.5:32b"]
    assert fake_ollama.get_loaded_models() == []
    evictions = fake_ollama.get_evictions()
    assert len(evictions) == 1
    assert evictions[0]["keep_alive"] == 0


def test_t1_f1_comfyui_free_on_model_key_change_and_explicit_flag(
    fake_ollama: FakeOllamaServer,
    fake_comfyui: FakeComfyUIServer,
    full_48g_profile: dict[str, Any],
    isolated_workspace: IsolatedWorkspace,
) -> None:
    from local_runners.gpu_lease import LeaseManager

    mgr = LeaseManager(comfyui_url=fake_comfyui.base_url, ollama_url=fake_ollama.base_url)

    r1 = mgr.acquire_media_lease(12.0, model_key="flux", profile=full_48g_profile)
    r2 = mgr.acquire_media_lease(12.0, model_key="flux", profile=full_48g_profile)
    r3 = mgr.acquire_media_lease(18.0, model_key="wan22", profile=full_48g_profile)
    r4 = mgr.acquire_media_lease(18.0, model_key="wan22", free_comfyui=True, profile=full_48g_profile)

    assert r1.comfyui_freed is False
    assert r2.comfyui_freed is False
    assert r3.comfyui_freed is True
    assert r4.comfyui_freed is True
    assert fake_comfyui.free_calls == [{"unload_models": True, "free_memory": True}] * 2
    assert fake_comfyui.loaded_models == set()


def test_t1_f1_mac_8g_lite_context_manager_then_llm_lease_frees_comfyui(
    fake_ollama: FakeOllamaServer,
    fake_comfyui: FakeComfyUIServer,
    mac_8g_lite_profile: dict[str, Any],
    isolated_workspace: IsolatedWorkspace,
) -> None:
    from local_runners.gpu_lease import LeaseManager

    fake_ollama.load_model("qwen2.5:3b", size_vram=2 * 2**30)
    mgr = LeaseManager(comfyui_url=fake_comfyui.base_url, ollama_url=fake_ollama.base_url)

    with mgr.acquire_media_lease(media_vram_gb=3.0, model_key="sd15", profile=mac_8g_lite_profile) as media_res:
        assert media_res.evicted_ollama is True
        assert fake_comfyui.free_calls == []

    llm_res = mgr.acquire_llm_lease(profile=mac_8g_lite_profile)
    assert llm_res.owner == "llm"
    assert llm_res.comfyui_freed is True
    assert len(fake_comfyui.free_calls) == 1
    assert fake_comfyui.loaded_models == set()


def test_t1_f1_module_level_env_resolution_and_to_dict(
    fake_ollama: FakeOllamaServer,
    fake_comfyui: FakeComfyUIServer,
    mac_8g_lite_profile: dict[str, Any],
    isolated_workspace: IsolatedWorkspace,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from local_runners.gpu_lease import acquire_llm_lease, acquire_media_lease

    monkeypatch.setenv("OLLAMA_URL", fake_ollama.base_url)
    monkeypatch.setenv("COMFYUI_URL", fake_comfyui.base_url)
    fake_ollama.load_model("gemma3:4b")

    with acquire_media_lease(2.5, profile=mac_8g_lite_profile) as lr:
        summary = lr.to_dict()
    llm_lr = acquire_llm_lease(free_comfyui=True, profile=mac_8g_lite_profile)

    assert summary["owner"] == "media"
    assert summary["evicted_ollama"] is True
    assert summary["evicted_models"] == ["gemma3:4b"]
    assert summary["tier"] == "mac_8g_lite"
    assert llm_lr.comfyui_freed is True
    assert len(fake_comfyui.free_calls) == 1
    assert len(fake_ollama.get_evictions()) == 1


# ---------------------------------------------------------------------------
# Feature F2 — Legacy Cloud Backend Gating (6 tests)
# ---------------------------------------------------------------------------


def test_t1_f2_providers_and_status_hide_legacy_cloud_by_default(
    live_studio_server: StudioHarness,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("STUDIO_LEGACY_CLOUD", raising=False)

    r_prov = live_studio_server.get("/api/providers")
    r_stat = live_studio_server.get("/api/status")
    r_prof = live_studio_server.get("/api/gpu_profile")

    assert r_prov.status == 200
    assert r_stat.status == 200
    assert r_prof.status == 200

    prov = r_prov.json()
    stat = r_stat.json()
    prof = r_prof.json()

    assert prov["legacy_cloud"] is False
    assert prov["free"] == []
    assert prov["paid"] == []
    assert [p["id"] for p in prov["computer"]] == ["computer"]
    assert isinstance(prov["gpu_profile"], dict)

    assert stat["legacy_cloud"] is False
    assert set(stat["gpus"]) == {"computer"}
    for legacy_key in ("kaggle", "colab", "huggingface", "cloud_api"):
        assert legacy_key not in stat["gpus"]
        assert legacy_key not in stat["gpu_blockers"]
    for legacy_tool in ("kaggle", "colab", "hf", "huggingface"):
        assert legacy_tool not in stat["tools"]

    assert prof["legacy_cloud"] is False


def test_t1_f2_providers_and_status_expose_legacy_cloud_when_enabled(
    live_studio_server: StudioHarness,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("STUDIO_LEGACY_CLOUD", "1")

    r_prov = live_studio_server.get("/api/providers")
    r_stat = live_studio_server.get("/api/status")
    r_prof = live_studio_server.get("/api/gpu_profile")

    assert r_prov.status == 200
    assert r_stat.status == 200
    assert r_prof.status == 200

    prov = r_prov.json()
    stat = r_stat.json()
    prof = r_prof.json()

    assert prov["legacy_cloud"] is True
    assert {p["id"] for p in prov["free"]} == {"kaggle", "colab", "huggingface"}
    assert len(prov["paid"]) >= 10

    assert stat["legacy_cloud"] is True
    assert {"computer", "kaggle", "colab", "huggingface", "cloud_api"} <= set(stat["gpus"])
    assert {"kaggle", "colab", "hf", "huggingface"} <= set(stat["tools"])
    assert prof["legacy_cloud"] is True


def test_t1_f2_dynamic_runtime_toggle_on_live_server(
    live_studio_server: StudioHarness,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("STUDIO_LEGACY_CLOUD", raising=False)
    p0 = live_studio_server.get("/api/providers").json()
    s0 = live_studio_server.get("/api/status").json()
    assert p0["free"] == []
    assert set(s0["gpus"]) == {"computer"}

    monkeypatch.setenv("STUDIO_LEGACY_CLOUD", "1")
    p1 = live_studio_server.get("/api/providers").json()
    s1 = live_studio_server.get("/api/status").json()
    assert len(p1["free"]) == 3
    assert "kaggle" in s1["gpus"]

    monkeypatch.delenv("STUDIO_LEGACY_CLOUD", raising=False)
    p2 = live_studio_server.get("/api/providers").json()
    s2 = live_studio_server.get("/api/status").json()
    assert p2["free"] == []
    assert set(s2["gpus"]) == {"computer"}


def test_t1_f2_legacy_routes_and_planner_remain_functional_when_gated(
    live_studio_server: StudioHarness,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("STUDIO_LEGACY_CLOUD", raising=False)
    _seed_minimal_book(live_studio_server.workspace.root, "e2e_f2_book")

    r_suggest = live_studio_server.get("/api/suggest?look=live_action&service=kaggle&gpu=NvidiaTeslaT4")
    r_runs = live_studio_server.get("/api/kaggle_runs")
    r_plan = live_studio_server.post("/api/plan", {"project": "e2e_f2_book", "steps": {"write": True}})

    assert r_suggest.status == 200
    suggest = r_suggest.json()
    assert suggest["service"] == "kaggle"
    assert "steps" in suggest

    # /api/kaggle_runs remains routed and active even when legacy cloud is gated (200 if kaggle CLI installed, 400 missing-CLI error otherwise; never 404).
    assert r_runs.status in {200, 400}
    runs_body = r_runs.json()
    assert ("runs" in runs_body) or ("kaggle" in str(runs_body.get("error", "")).lower())

    assert r_plan.status == 200
    assert len(r_plan.json()["steps"]) >= 1


def test_t1_f2_js_ui_hides_paid_providers_and_selects_computer_when_gated(
    live_studio_server: StudioHarness,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("STUDIO_LEGACY_CLOUD", raising=False)
    url = f"{live_studio_server.base_url}/?t={live_studio_server.token}"
    res = _run_jsdom_probe(
        url,
        'const svcEl = d.querySelector(\'input[name="svc"]:checked\');\n'
        "const out = {\n"
        "  errors,\n"
        '  stLegacyCloud: w.eval("ST && ST.legacy_cloud"),\n'
        '  paidCount: d.querySelectorAll("#paidProviders li").length,\n'
        '  svcChecked: svcEl ? svcEl.value : "",\n'
        '  toolsText: (d.getElementById("tools") || {}).textContent || "",\n'
        "};\n"
        "console.log(JSON.stringify(out));\n"
        "process.exit(0);\n",
    )
    assert res["errors"] == []
    assert res["stLegacyCloud"] is False
    assert res["paidCount"] == 0
    if res["svcChecked"]:
        assert res["svcChecked"] == "computer"
    assert "Kaggle CLI missing" not in res["toolsText"]
    assert "Colab CLI missing" not in res["toolsText"]


def test_t1_f2_js_ui_populates_paid_providers_when_legacy_cloud_enabled(
    live_studio_server: StudioHarness,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("STUDIO_LEGACY_CLOUD", "1")
    url = f"{live_studio_server.base_url}/?t={live_studio_server.token}"
    res = _run_jsdom_probe(
        url,
        "const out = {\n"
        "  errors,\n"
        '  stLegacyCloud: w.eval("ST && ST.legacy_cloud"),\n'
        '  paidCount: d.querySelectorAll("#paidProviders li").length,\n'
        '  paidText: (d.getElementById("paidProviders") || {}).textContent || "",\n'
        "};\n"
        "console.log(JSON.stringify(out));\n"
        "process.exit(0);\n",
    )
    assert res["errors"] == []
    assert res["stLegacyCloud"] is True
    assert res["paidCount"] >= 10
    assert "unproven" in res["paidText"]
    assert "RunPod" in res["paidText"]


# ---------------------------------------------------------------------------
# Feature F3 — Phase 1 Fixes & Routing (6 tests)
# ---------------------------------------------------------------------------


def test_t1_f3_gpu_profile_endpoint_and_schema_parity(
    live_studio_server: StudioHarness,
    full_48g_profile: dict[str, Any],
) -> None:
    from studio_app import gpus

    resp = live_studio_server.get("/api/gpu_profile")
    assert resp.status == 200
    data = resp.json()
    direct = gpus.gpu_profile()

    assert data == direct
    assert set(data.keys()) == set(full_48g_profile.keys())
    assert isinstance(data["ram_gb"], float)
    assert data["ram_gb"] > 0.0
    assert isinstance(data["vram_gb"], float)
    assert data["tier"] in {"full_48g", "standard_gpu", "low_vram", "mac_8g_lite", "cpu"}


def test_t1_f3_blackwell_detection_cu128_and_offload_disabled_for_48gb(
    isolated_workspace: IsolatedWorkspace,
) -> None:
    import run_local_model as rl

    assert rl.BLACKWELL_TORCH_INDEX == "https://download.pytorch.org/whl/cu128"
    assert rl.is_blackwell_gpu("NVIDIA GeForce RTX 5090", "12.0") is True

    opts_48 = rl.gpu_optimizations("NVIDIA GeForce RTX 5090", "12.0", 48.0)
    opts_12 = rl.gpu_optimizations("NVIDIA GeForce RTX 5070", "12.0", 12.0)

    assert opts_48["use_bf16"] is True
    assert opts_48["use_flash_attn"] is True
    assert opts_48["allow_cpu_offload"] is False
    assert opts_48["memory_fraction"] == 0.98

    assert opts_12["allow_cpu_offload"] is True
    assert opts_12["memory_fraction"] == 0.80


def test_t1_f3_to_script_wires_allow_cpu_offload_and_cuda_mem_guard(tmp_path: Path) -> None:
    import run_local_model as rl

    nb_path = tmp_path / "test_nb.ipynb"
    nb_data = {
        "cells": [
            {
                "cell_type": "code",
                "source": [
                    "START, END = 1, 1\n",
                    "CSV_NAME = 'shots.csv'\n",
                    "# pipe.enable_model_cpu_offload()\n",
                    "pipe.enable_model_cpu_offload()\n",
                    "pipe2.enable_sequential_cpu_offload()\n",
                ],
            }
        ]
    }
    nb_path.write_text(json.dumps(nb_data), encoding="utf-8")

    s_no, _ = rl.to_script(
        nb_path,
        1,
        1,
        "all_shots.csv",
        tmp_path,
        tmp_path,
        rl.gpu_optimizations("NVIDIA GeForce RTX 5090", "12.0", 48.0),
    )
    s_yes, _ = rl.to_script(
        nb_path,
        1,
        1,
        "all_shots.csv",
        tmp_path,
        tmp_path,
        rl.gpu_optimizations("NVIDIA GeForce RTX 5070", "12.0", 12.0),
    )

    compile(s_no, "no_offload.py", "exec")
    compile(s_yes, "with_offload.py", "exec")

    assert "_ALLOW_CPU_OFFLOAD = False" in s_no
    assert "\npipe.to(_device)\n" in s_no
    assert "\npipe2.to(_device)\n" in s_no
    assert "# pipe.enable_model_cpu_offload()" in s_no
    assert 'if _device == "cuda":' in s_no
    assert "set_per_process_memory_fraction" in s_no

    assert "_ALLOW_CPU_OFFLOAD = True" in s_yes
    assert "pipe.enable_model_cpu_offload()" in s_yes


def test_t1_f3_local_llm_status_8gb_lite_tier_via_fake_ollama(
    fake_ollama: FakeOllamaServer,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from e2e.helpers.studio_harness import IsolatedWorkspace as _IsoWs

    fake_ollama.set_available_models(["qwen2.5:3b", "gemma3:4b"])
    monkeypatch.setenv("STUDIO_LOCAL_LLM", "1")

    with _IsoWs(base_dir=tmp_path / "ws_llm", local_llm_url=fake_ollama.v1_chat_url):
        from studio_app import llm

        st = llm.local_llm_status(force=True)

    assert st["ready"] is True
    assert st["models"] == ["qwen2.5:3b", "gemma3:4b"]
    assert st["tier"] == "lite"
    assert "qwen2.5:3b" in st["recommended_models"]
    assert any(r["path"] == "/v1/models" for r in fake_ollama.get_requests())


def test_t1_f3_parameterized_routing_live_http_get_and_post(live_studio_server: StudioHarness) -> None:
    def _exact_status(r: Any) -> dict[str, Any]:
        return {"exact": True}

    def _get_item(r: Any) -> dict[str, Any]:
        return {"id": r.p("item_id")}

    def _post_run(r: Any) -> dict[str, Any]:
        return {"id": r.p("item_id"), "mode": r.q("mode"), "seed": r.body.get("seed")}

    specs = [
        ("GET", "/api/_e2e_f3_items/status", _exact_status),
        ("GET", "/api/_e2e_f3_items/<item_id>", _get_item),
        ("POST", "/api/_e2e_f3_items/<item_id>/run", _post_run),
    ]
    with _temp_routes(specs):
        r1 = live_studio_server.get("/api/_e2e_f3_items/alpha-1")
        r2 = live_studio_server.get("/api/_e2e_f3_items/status")
        r3 = live_studio_server.post("/api/_e2e_f3_items/beta%202/run?mode=fast", {"seed": 7})

    assert r1.status == 200
    assert r1.json() == {"id": "alpha-1"}
    assert r2.status == 200
    assert r2.json() == {"exact": True}
    assert r3.status == 200
    assert r3.json() == {"id": "beta 2", "mode": "fast", "seed": 7}


def test_t1_f3_load_optional_routes_discovers_and_registers_when_present(tmp_path: Path) -> None:
    from studio_app import api, handler

    pkg_dir = tmp_path / "e2e_opt_pkg"
    pkg_dir.mkdir(parents=True, exist_ok=True)
    (pkg_dir / "__init__.py").write_text("", encoding="utf-8")
    (pkg_dir / "apps_routes.py").write_text(
        "from studio_app import api\n"
        "@api.route('GET', '/api/_e2e_opt_apps')\n"
        "def _apps(r):\n"
        "    return {'ok': 'apps'}\n",
        encoding="utf-8",
    )
    (pkg_dir / "compose_routes.py").write_text(
        "from studio_app import api\n"
        "@api.route('GET', '/api/_e2e_opt_compose')\n"
        "def _compose(r):\n"
        "    return {'ok': 'compose'}\n",
        encoding="utf-8",
    )

    saved_routes = {m: dict(r) for m, r in api.ROUTES.items()}
    saved_patterns = {m: list(p) for m, p in api.PATTERN_ROUTES.items()}
    saved_path = list(sys.path)
    try:
        sys.path.insert(0, str(tmp_path))
        loaded = handler.load_optional_routes(package="e2e_opt_pkg")
        assert handler.OPTIONAL_ROUTE_MODULES == ("apps_routes", "compose_routes")
        assert loaded == ["e2e_opt_pkg.apps_routes", "e2e_opt_pkg.compose_routes"]
        assert api.dispatch("GET", "/api/_e2e_opt_apps", api.Request()) == (200, {"ok": "apps"})
        assert api.dispatch("GET", "/api/_e2e_opt_compose", api.Request()) == (200, {"ok": "compose"})
    finally:
        sys.path[:] = saved_path
        for mod_name in [k for k in sys.modules if k == "e2e_opt_pkg" or k.startswith("e2e_opt_pkg.")]:
            sys.modules.pop(mod_name, None)
        for m, orig_r in saved_routes.items():
            api.ROUTES[m].clear()
            api.ROUTES[m].update(orig_r)
        for m, orig_p in saved_patterns.items():
            api.PATTERN_ROUTES[m][:] = orig_p


# ---------------------------------------------------------------------------
# Feature F4 — Hardware Matrix & CI/JS Baseline Gates (6 tests)
# ---------------------------------------------------------------------------


def test_t1_f4_hardware_matrix_profiles_distinct_and_consistent(
    full_48g_profile: dict[str, Any],
    mac_8g_lite_profile: dict[str, Any],
) -> None:
    assert set(full_48g_profile.keys()) == set(mac_8g_lite_profile.keys())
    assert len(full_48g_profile) == 13

    assert full_48g_profile["tier"] == "full_48g"
    assert full_48g_profile["vram_gb"] == 48.0
    assert full_48g_profile["ram_gb"] == 64.0
    assert full_48g_profile["is_blackwell"] is True
    assert full_48g_profile["supports_local_video"] is True
    assert full_48g_profile["default_image_backend"] == "comfyui"
    assert full_48g_profile["default_video_backend"] == "comfyui"

    assert mac_8g_lite_profile["tier"] == "mac_8g_lite"
    assert mac_8g_lite_profile["vram_gb"] == 8.0
    assert mac_8g_lite_profile["ram_gb"] == 8.0
    assert mac_8g_lite_profile["is_blackwell"] is False
    assert mac_8g_lite_profile["supports_local_video"] is False
    assert mac_8g_lite_profile["supports_local_images"] is True
    assert mac_8g_lite_profile["default_image_backend"] == "sd_cli"
    assert mac_8g_lite_profile["default_video_backend"] == "none"


def test_t1_f4_js_test_dependencies_and_node_syntax_gate() -> None:
    node = shutil.which("node")
    assert node is not None, "node executable must be on PATH"

    jsdom_check = subprocess.run(
        [node, "-e", 'require("jsdom")'],
        cwd=str(_JS_DIR),
        capture_output=True,
        text=True,
        check=False,
    )
    assert jsdom_check.returncode == 0, f"jsdom missing in {_JS_DIR}: {jsdom_check.stderr}"

    js_files = sorted((_NEON_ROOT / "web" / "static" / "js").glob("*.js"))
    assert js_files, "Expected JS files in web/static/js"
    for js_file in js_files:
        chk = subprocess.run([node, "--check", str(js_file)], capture_output=True, text=True, check=False)
        assert chk.returncode == 0, f"node --check failed on {js_file.name}: {chk.stderr}"


def test_t1_f4_ruff_baseline_clean_on_r1_modules() -> None:
    ruff = _tool_bin("ruff")
    targets = [
        "scripts/local_runners",
        "scripts/studio_app/gpus.py",
        "scripts/studio_app/providers.py",
        "scripts/studio_app/overview.py",
        "scripts/studio_app/api.py",
        "scripts/studio_app/handler.py",
        "scripts/studio_app/llm.py",
        "scripts/run_local_model.py",
        "tests/e2e/conftest.py",
        "tests/e2e/test_infra_selfcheck.py",
    ]
    proc = subprocess.run([ruff, "check", *targets], cwd=str(_NEON_ROOT), capture_output=True, text=True, check=False)
    assert proc.returncode == 0, f"ruff check failed:\n{proc.stdout}\n{proc.stderr}"


def test_t1_f4_mypy_baseline_clean_on_r1_modules() -> None:
    mypy = _tool_bin("mypy")
    targets = [
        "scripts/local_runners",
        "scripts/studio_app/gpus.py",
        "scripts/studio_app/providers.py",
        "scripts/studio_app/overview.py",
        "scripts/studio_app/api.py",
        "scripts/studio_app/handler.py",
        "scripts/studio_app/llm.py",
        "scripts/run_local_model.py",
    ]
    proc = subprocess.run([mypy, *targets], cwd=str(_NEON_ROOT), capture_output=True, text=True, check=False)
    assert proc.returncode == 0, f"mypy failed:\n{proc.stdout}\n{proc.stderr}"


def test_t1_f4_e2e_collection_gating_on_vs_off() -> None:
    base_env = {k: v for k, v in os.environ.items() if k not in {"STUDIO_RUN_E2E", "PYTEST_ADDOPTS"}}

    off_proc = subprocess.run(
        [sys.executable, "-m", "pytest", "--collect-only", "-q", "tests/e2e/test_infra_selfcheck.py"],
        cwd=str(_NEON_ROOT),
        env=base_env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert off_proc.returncode in (0, 5)
    assert "13 tests" not in off_proc.stdout

    on_env = dict(base_env)
    on_env["STUDIO_RUN_E2E"] = "1"
    on_proc = subprocess.run(
        [sys.executable, "-m", "pytest", "--collect-only", "-q", "tests/e2e/test_infra_selfcheck.py"],
        cwd=str(_NEON_ROOT),
        env=on_env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert on_proc.returncode == 0
    assert "test_infra_selfcheck.py: 13" in on_proc.stdout or "13 tests collected" in on_proc.stdout


def test_t1_f4_macos_apple_silicon_detection_via_fake_system_profiler_cli(tmp_path: Path) -> None:
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
    sysctl.write_text(
        f"#!{sys.executable}\n"
        f"print({8 * 2**30})\n",
        encoding="utf-8",
    )
    sysctl.chmod(0o755)

    env = dict(os.environ)
    env["PATH"] = f"{bin_dir}{os.pathsep}{env.get('PATH', '')}"
    env["PYTHONPATH"] = str(_NEON_ROOT / "scripts")
    env.pop("STUDIO_LEGACY_CLOUD", None)

    proc = subprocess.run(
        [sys.executable, "-c", "import json; from studio_app import gpus; print(json.dumps(gpus.gpu_profile()))"],
        cwd=str(_NEON_ROOT),
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, f"subprocess failed: {proc.stderr}"
    prof = json.loads(proc.stdout.strip())
    assert prof["backend"] == "mps"
    assert prof["tier"] == "mac_8g_lite"
    assert prof["vram_gb"] == 8.0
    assert prof["ram_gb"] == 8.0
    assert prof["supports_local_video"] is False
    assert prof["default_image_backend"] == "sd_cli"
    assert prof["default_video_backend"] == "none"
