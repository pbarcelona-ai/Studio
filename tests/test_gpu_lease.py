"""Tests for scripts/local_runners/gpu_lease.py against mocked HTTP servers."""
from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

import pytest

from local_runners import (
    DEFAULT_48G_THRESHOLD_GB,
    LeaseManager,
    LeaseResult,
    acquire_llm_lease,
    acquire_media_lease,
)
from local_runners.gpu_lease import resolve_comfyui_url, resolve_ollama_url


def _start_mock_server(
    ps_models: list[dict[str, Any]] | None = None,
    *,
    fail_ps_status: int | None = None,
    fail_generate_status: int | None = None,
    fail_free_status: int | None = None,
    bad_ps_json: bool = False,
):
    state: dict[str, Any] = {
        "ps_models": list(ps_models or []),
        "ps_calls": 0,
        "generate_calls": [],
        "free_calls": [],
    }
    lock = threading.Lock()

    class _Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt: str, *args: Any) -> None:
            return

        def _read_json(self) -> dict[str, Any]:
            n = int(self.headers.get("Content-Length", "0") or 0)
            raw = self.rfile.read(n) if n > 0 else b"{}"
            return json.loads(raw.decode("utf-8"))

        def _send_json(self, code: int, obj: Any) -> None:
            body = json.dumps(obj).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self) -> None:
            if self.path == "/api/ps":
                with lock:
                    state["ps_calls"] += 1
                    models = list(state["ps_models"])
                if fail_ps_status is not None:
                    self._send_json(fail_ps_status, {"error": "ps failed"})
                    return
                if bad_ps_json:
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Content-Length", "7")
                    self.end_headers()
                    self.wfile.write(b"{broken")
                    return
                self._send_json(200, {"models": models})
                return
            self._send_json(404, {"error": "not found"})

        def do_POST(self) -> None:
            body = self._read_json()
            if self.path == "/api/generate":
                with lock:
                    state["generate_calls"].append(body)
                if fail_generate_status is not None:
                    self._send_json(fail_generate_status, {"error": "generate failed"})
                    return
                if body.get("keep_alive") == 0:
                    with lock:
                        state["ps_models"] = [
                            m for m in state["ps_models"]
                            if (m.get("model") or m.get("name")) != body.get("model")
                        ]
                self._send_json(200, {"done": True})
                return
            if self.path == "/free":
                with lock:
                    state["free_calls"].append(body)
                if fail_free_status is not None:
                    self._send_json(fail_free_status, {"error": "free failed"})
                    return
                self._send_json(200, {"freed": True})
                return
            self._send_json(404, {"error": "not found"})

    srv = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    url = f"http://127.0.0.1:{srv.server_port}"
    return srv, url, state


MAC_8G_PROFILE = {"tier": "mac_8g_lite", "vram_gb": 8.0, "ram_gb": 8.0}
FULL_48G_PROFILE = {"tier": "full_48g", "vram_gb": 48.0, "ram_gb": 64.0}


def test_mac_8g_lite_strict_eviction():
    srv, url, state = _start_mock_server(
        ps_models=[
            {"model": "qwen2.5:3b", "size_vram": 2 * 2**30},
            {"name": "gemma3:4b", "size": 3 * 2**30},
        ]
    )
    try:
        mgr = LeaseManager(ollama_url=url)
        res = mgr.acquire_media_lease(media_vram_gb=2.5, profile=MAC_8G_PROFILE)
        assert isinstance(res, LeaseResult)
        assert res.owner == "media"
        assert res.tier == "mac_8g_lite"
        assert res.evicted_ollama is True
        assert res.evicted_models == ["qwen2.5:3b", "gemma3:4b"]
        assert res.warnings == []
        assert state["generate_calls"] == [
            {"model": "qwen2.5:3b", "keep_alive": 0},
            {"model": "gemma3:4b", "keep_alive": 0},
        ]

        # Second call when /api/ps is empty is a no-op
        res2 = mgr.acquire_media_lease(media_vram_gb=2.5, profile=MAC_8G_PROFILE)
        assert res2.evicted_ollama is False
        assert res2.evicted_models == []

        # Fallback ollama_model when /api/ps is empty
        res3 = mgr.acquire_media_lease(
            media_vram_gb=2.5,
            profile=MAC_8G_PROFILE,
            ollama_model="llama3.2:3b",
        )
        assert res3.evicted_ollama is True
        assert res3.evicted_models == ["llama3.2:3b"]
    finally:
        srv.shutdown()
        srv.server_close()


def test_full_48g_threshold_and_boundary():
    assert DEFAULT_48G_THRESHOLD_GB == 42.0
    srv, url, state = _start_mock_server(
        ps_models=[{"model": "qwen2.5:32b", "size_vram": int(18.5 * 2**30)}]
    )
    try:
        mgr = LeaseManager(ollama_url=url)

        # 10 + 20 = 30 <= 42 -> stays resident
        r1 = mgr.acquire_media_lease(media_vram_gb=20.0, active_llm_gb=10.0, profile=FULL_48G_PROFILE)
        assert r1.evicted_ollama is False
        assert r1.threshold_gb == 42.0
        assert state["generate_calls"] == []

        # Exact boundary 18 + 24 = 42.0 -> stays resident (strict >)
        r2 = mgr.acquire_media_lease(media_vram_gb=24.0, active_llm_gb=18.0, profile=FULL_48G_PROFILE)
        assert r2.evicted_ollama is False
        assert state["generate_calls"] == []

        # active_llm_gb=None reads 18.5 GB from /api/ps; 18.5 + 24.0 = 42.5 > 42.0 -> evicts
        r3 = mgr.acquire_media_lease(media_vram_gb=24.0, active_llm_gb=None, profile=FULL_48G_PROFILE)
        assert r3.active_llm_gb == pytest.approx(18.5, rel=1e-2)
        assert r3.evicted_ollama is True
        assert r3.evicted_models == ["qwen2.5:32b"]
        assert state["generate_calls"] == [{"model": "qwen2.5:32b", "keep_alive": 0}]
    finally:
        srv.shutdown()
        srv.server_close()


def test_comfyui_free_on_flag_and_model_key_change():
    srv, url, state = _start_mock_server(ps_models=[])
    try:
        mgr = LeaseManager(comfyui_url=url, ollama_url=url)

        # First key does not call /free
        r1 = mgr.acquire_media_lease(media_vram_gb=12.0, model_key="flux", profile=FULL_48G_PROFILE)
        assert r1.comfyui_freed is False
        assert state["free_calls"] == []

        # Same key does not call /free
        r2 = mgr.acquire_media_lease(media_vram_gb=12.0, model_key="flux", profile=FULL_48G_PROFILE)
        assert r2.comfyui_freed is False
        assert state["free_calls"] == []

        # Changed key calls POST /free
        r3 = mgr.acquire_media_lease(media_vram_gb=16.0, model_key="wan21", profile=FULL_48G_PROFILE)
        assert r3.comfyui_freed is True
        assert state["free_calls"] == [{"unload_models": True, "free_memory": True}]

        # Explicit free_comfyui=True forces /free
        r4 = mgr.acquire_media_lease(media_vram_gb=16.0, model_key="wan21", free_comfyui=True, profile=FULL_48G_PROFILE)
        assert r4.comfyui_freed is True
        assert len(state["free_calls"]) == 2

        # acquire_llm_lease frees ComfyUI on mac_8g_lite when media was active
        r5 = mgr.acquire_media_lease(media_vram_gb=4.0, profile=MAC_8G_PROFILE)
        assert r5.owner == "media"
        llm_res = mgr.acquire_llm_lease(profile=MAC_8G_PROFILE)
        assert llm_res.owner == "llm"
        assert llm_res.comfyui_freed is True
        assert len(state["free_calls"]) == 3
    finally:
        srv.shutdown()
        srv.server_close()


def test_context_manager_and_concurrent_threads(monkeypatch):
    srv, url, state = _start_mock_server(ps_models=[{"model": "qwen2.5:3b", "size_vram": 2 * 2**30}])
    monkeypatch.setenv("OLLAMA_URL", url)
    monkeypatch.setenv("COMFYUI_URL", url)
    try:
        with acquire_media_lease(media_vram_gb=4.0, profile=MAC_8G_PROFILE) as lease:
            assert lease.evicted_ollama is True
            d = lease.to_dict()
            assert d["owner"] == "media" and d["evicted_models"] == ["qwen2.5:3b"]
        lease.release(free_comfyui=True)  # idempotent after __exit__
        assert state["free_calls"] == []

        with acquire_llm_lease(free_comfyui=True, profile=MAC_8G_PROFILE) as lres:
            assert lres.comfyui_freed is True

        # Concurrent acquisition from multiple threads without deadlocks or errors
        mgr = LeaseManager(comfyui_url=url, ollama_url=url)
        errors: list[Exception] = []
        results: list[LeaseResult] = []
        res_lock = threading.Lock()

        def worker(i: int) -> None:
            try:
                with (
                    mgr.acquire_media_lease(
                        media_vram_gb=10.0,
                        active_llm_gb=10.0,
                        model_key=f"m{i % 3}",
                        profile=FULL_48G_PROFILE,
                    ) as lr,
                    res_lock,
                ):
                    results.append(lr)
            except Exception as exc:
                with res_lock:
                    errors.append(exc)

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(12)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)
        assert errors == []
        assert len(results) == 12
    finally:
        srv.shutdown()
        srv.server_close()


def test_unreachable_and_error_servers_resilient():
    # Unreachable port never raises
    mgr_dead = LeaseManager(comfyui_url="http://127.0.0.1:9", ollama_url="http://127.0.0.1:9", timeout=0.3)
    r_dead = mgr_dead.acquire_media_lease(
        media_vram_gb=4.0,
        free_comfyui=True,
        profile=MAC_8G_PROFILE,
        ollama_model="qwen2.5:3b",
    )
    assert r_dead.evicted_ollama is False
    assert r_dead.comfyui_freed is False
    assert len(r_dead.warnings) >= 2

    # HTTP 500 on /api/ps, /api/generate, and /free
    srv, url, _ = _start_mock_server(
        ps_models=[{"model": "m1", "size_vram": 1}],
        fail_ps_status=500,
        fail_generate_status=500,
        fail_free_status=500,
    )
    try:
        mgr_err = LeaseManager(comfyui_url=url, ollama_url=url, timeout=1.0)
        r_err = mgr_err.acquire_media_lease(
            media_vram_gb=4.0,
            free_comfyui=True,
            profile=MAC_8G_PROFILE,
            ollama_model="m1",
        )
        assert r_err.evicted_ollama is False
        assert r_err.comfyui_freed is False
        assert len(r_err.warnings) == 3
    finally:
        srv.shutdown()
        srv.server_close()

    # Malformed JSON on /api/ps
    srv2, url2, _ = _start_mock_server(bad_ps_json=True)
    try:
        mgr_bad = LeaseManager(comfyui_url=url2, ollama_url=url2, timeout=1.0)
        r_bad = mgr_bad.acquire_media_lease(media_vram_gb=4.0, profile=MAC_8G_PROFILE)
        assert r_bad.warnings and "Ollama /api/ps failed" in r_bad.warnings[0]
    finally:
        srv2.shutdown()
        srv2.server_close()


def test_mac_8g_lite_with_context_manager_frees_comfyui_on_llm_lease():
    srv, url, state = _start_mock_server(ps_models=[{"model": "qwen2.5:3b", "size_vram": 2 * 2**30}])
    try:
        mgr = LeaseManager(comfyui_url=url, ollama_url=url)
        with mgr.acquire_media_lease(media_vram_gb=2.0, model_key="sd15", profile=MAC_8G_PROFILE) as lease:
            assert lease.evicted_ollama is True
        assert state["free_calls"] == []
        assert mgr._comfyui_dirty is True
        assert mgr._active_owner is None

        llm_res = mgr.acquire_llm_lease(profile=MAC_8G_PROFILE)
        assert llm_res.comfyui_freed is True
        assert state["free_calls"] == [{"unload_models": True, "free_memory": True}]
        assert mgr._comfyui_dirty is False
        assert mgr._active_model_key is None

        # Subsequent LLM lease does not redundantly free ComfyUI
        llm_res2 = mgr.acquire_llm_lease(profile=MAC_8G_PROFILE)
        assert llm_res2.comfyui_freed is False
        assert len(state["free_calls"]) == 1
    finally:
        srv.shutdown()
        srv.server_close()


def test_concurrent_with_media_leases_serialized():
    import time

    srv, url, state = _start_mock_server(ps_models=[])
    try:
        mgr = LeaseManager(comfyui_url=url, ollama_url=url)
        t1_entered = threading.Event()
        observations: list[tuple[str, str | None, str | None, int, int, bool]] = []
        obs_lock = threading.Lock()

        def t1() -> None:
            with mgr.acquire_media_lease(
                media_vram_gb=10.0,
                active_llm_gb=10.0,
                model_key="flux",
                profile=FULL_48G_PROFILE,
            ) as lr:
                enter_key = mgr._active_model_key
                enter_frees = len(state["free_calls"])
                t1_entered.set()
                time.sleep(0.08)
                exit_key = mgr._active_model_key
                exit_frees = len(state["free_calls"])
                with obs_lock:
                    observations.append(("flux", enter_key, exit_key, enter_frees, exit_frees, lr.comfyui_freed))

        def t2() -> None:
            t1_entered.wait(timeout=5.0)
            time.sleep(0.02)
            with mgr.acquire_media_lease(
                media_vram_gb=10.0,
                active_llm_gb=10.0,
                model_key="wan21",
                profile=FULL_48G_PROFILE,
            ) as lr:
                enter_key = mgr._active_model_key
                enter_frees = len(state["free_calls"])
                exit_key = mgr._active_model_key
                exit_frees = len(state["free_calls"])
                with obs_lock:
                    observations.append(("wan21", enter_key, exit_key, enter_frees, exit_frees, lr.comfyui_freed))

        th1 = threading.Thread(target=t1)
        th2 = threading.Thread(target=t2)
        th1.start()
        th2.start()
        th1.join(timeout=10)
        th2.join(timeout=10)

        assert len(observations) == 2
        by_name = {row[0]: row for row in observations}
        assert by_name["flux"] == ("flux", "flux", "flux", 0, 0, False)
        assert by_name["wan21"] == ("wan21", "wan21", "wan21", 1, 1, True)

        # Mixed direct and context-manager calls across threads never deadlock
        errors: list[Exception] = []

        def mixed_worker(idx: int) -> None:
            try:
                if idx % 3 == 0:
                    with mgr.acquire_media_lease(
                        media_vram_gb=8.0,
                        active_llm_gb=8.0,
                        model_key=f"k{idx % 2}",
                        profile=FULL_48G_PROFILE,
                    ):
                        time.sleep(0.005)
                elif idx % 3 == 1:
                    mgr.acquire_media_lease(
                        media_vram_gb=8.0,
                        active_llm_gb=8.0,
                        model_key=f"k{idx % 2}",
                        profile=FULL_48G_PROFILE,
                    )
                else:
                    mgr.acquire_llm_lease(profile=FULL_48G_PROFILE)
            except Exception as exc:
                errors.append(exc)

        mix_threads = [threading.Thread(target=mixed_worker, args=(i,)) for i in range(12)]
        for th in mix_threads:
            th.start()
        for th in mix_threads:
            th.join(timeout=10)
            assert not th.is_alive()
        assert errors == []
    finally:
        srv.shutdown()
        srv.server_close()


def test_origin_rejects_schemeless_schemes_and_accepts_valid_hosts():
    assert resolve_ollama_url("127.0.0.1:11434") == "http://127.0.0.1:11434"
    assert resolve_ollama_url("0.0.0.0:11434") == "http://0.0.0.0:11434"
    assert resolve_ollama_url("[::1]:11434") == "http://[::1]:11434"
    assert resolve_ollama_url("localhost:11434") == "http://localhost:11434"
    assert resolve_ollama_url("http://127.0.0.1:11434/v1/chat/completions") == "http://127.0.0.1:11434"
    assert resolve_comfyui_url("https://comfy.example.com/ws") == "https://comfy.example.com"

    for bad in (
        "file:/etc/passwd",
        "file:///etc/passwd",
        "javascript:alert(1)",
        "data:text/plain,hello",
        "ftp://127.0.0.1:11434",
        "mailto:user@example.com",
        "http:foo",
    ):
        with pytest.raises(ValueError):
            resolve_ollama_url(bad)
        with pytest.raises(ValueError):
            resolve_comfyui_url(bad)
