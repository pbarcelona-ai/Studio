"""Self-verification tests for Milestone E1 E2E test infrastructure."""
from __future__ import annotations

import hashlib
import importlib
import io
import json
import logging
import os
from pathlib import Path
import socket
import subprocess
import sys
import threading
import time
from typing import Any
import urllib.error
import urllib.request

from e2e.conftest import FULL_48G_PLATFORM_TAG, MAC_8G_PLATFORM_TAG
from e2e.helpers.fake_comfyui import MINIMAL_JPEG, MINIMAL_PNG, FakeComfyUIServer, connect_ws
from e2e.helpers.fake_hf import FakeHFHubServer
from e2e.helpers.fake_ollama import FakeOllamaServer
from e2e.helpers.studio_harness import IsolatedWorkspace, StudioHarness


class _NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(
        self,
        req: urllib.request.Request,
        fp: Any,
        code: int,
        msg: str,
        headers: Any,
        newurl: str,
    ) -> urllib.request.Request | None:
        return None


def _http_call(
    method: str,
    url: str,
    *,
    body: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
    follow_redirects: bool = True,
) -> tuple[int, dict[str, str], bytes]:
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req_headers = dict(headers or {})
    if data is not None:
        req_headers.setdefault("Content-Type", "application/json")
    req = urllib.request.Request(url, data=data, headers=req_headers, method=method)
    opener = (
        urllib.request.build_opener()
        if follow_redirects
        else urllib.request.build_opener(_NoRedirectHandler)
    )
    try:
        with opener.open(req, timeout=5.0) as resp:
            return resp.status, {k.lower(): v for k, v in resp.headers.items()}, resp.read()
    except urllib.error.HTTPError as err:
        return err.code, {k.lower(): v for k, v in err.headers.items()}, err.read()


# ---------------------------------------------------------------------------
# 1. FakeOllamaServer self-checks
# ---------------------------------------------------------------------------


def test_fake_ollama_tags_ps_generate_and_eviction(fake_ollama: FakeOllamaServer) -> None:
    fake_ollama.set_available_models(["qwen2.5:3b", "qwen2.5:32b"])
    fake_ollama.load_model("qwen2.5:3b", size_vram=2_500_000_000)

    status, _, raw_tags = _http_call("GET", f"{fake_ollama.base_url}/api/tags")
    assert status == 200
    tags = json.loads(raw_tags)
    assert {m["name"] for m in tags["models"]} == {"qwen2.5:3b", "qwen2.5:32b"}

    status, _, raw_ps = _http_call("GET", f"{fake_ollama.base_url}/api/ps")
    assert status == 200
    ps = json.loads(raw_ps)
    assert len(ps["models"]) == 1
    assert ps["models"][0]["name"] == "qwen2.5:3b"
    assert ps["models"][0]["size_vram"] == 2_500_000_000

    # Stream=False generate returns single JSON object with default reply
    status, hdrs_sync, raw_sync = _http_call(
        "POST",
        f"{fake_ollama.base_url}/api/generate",
        body={"model": "qwen2.5:3b", "prompt": "say hi", "stream": False},
    )
    assert status == 200
    assert "application/json" in hdrs_sync.get("content-type", "")
    sync_json = json.loads(raw_sync)
    assert sync_json["done"] is True
    assert sync_json["response"] == "fake-ollama-response"

    # Stream=True NDJSON generate loads qwen2.5:32b
    status, hdrs, raw_gen = _http_call(
        "POST",
        f"{fake_ollama.base_url}/api/generate",
        body={"model": "qwen2.5:32b", "prompt": "hello", "stream": True, "keep_alive": "5m"},
    )
    assert status == 200
    assert "application/x-ndjson" in hdrs.get("content-type", "")
    chunks = [json.loads(line) for line in raw_gen.decode("utf-8").splitlines() if line.strip()]
    assert len(chunks) == 2
    assert chunks[0]["done"] is False
    assert chunks[1]["done"] is True

    _, _, raw_ps_after_load = _http_call("GET", f"{fake_ollama.base_url}/api/ps")
    loaded_names = {m["name"] for m in json.loads(raw_ps_after_load)["models"]}
    assert loaded_names == {"qwen2.5:3b", "qwen2.5:32b"}

    # Evict with keep_alive: 0 and "0s"
    status, _, raw_evict = _http_call(
        "POST",
        f"{fake_ollama.base_url}/api/generate",
        body={"model": "qwen2.5:3b", "prompt": "", "keep_alive": 0, "stream": False},
    )
    assert status == 200
    evict_json = json.loads(raw_evict)
    assert evict_json["done"] is True
    assert evict_json["done_reason"] == "unload"

    status, _, _ = _http_call(
        "POST",
        f"{fake_ollama.base_url}/api/generate",
        body={"model": "qwen2.5:32b", "prompt": "", "keep_alive": "0s"},
    )
    assert status == 200
    assert len(fake_ollama.get_evictions()) == 2

    _, _, raw_ps_empty = _http_call("GET", f"{fake_ollama.base_url}/api/ps")
    assert json.loads(raw_ps_empty)["models"] == []


def test_fake_ollama_openai_v1_strict_models_and_error_injection() -> None:
    with FakeOllamaServer(available_models=["llama3.2:latest"], strict_models=True) as srv:
        status, _, raw_models = _http_call("GET", srv.v1_models_url)
        assert status == 200
        models_data = json.loads(raw_models)
        assert models_data["object"] == "list"
        assert [m["id"] for m in models_data["data"]] == ["llama3.2:latest"]

        # Non-streaming chat completion with :latest normalization ("llama3.2" -> "llama3.2:latest")
        status, _, raw_chat = _http_call(
            "POST",
            srv.v1_chat_url,
            body={"model": "llama3.2", "messages": [{"role": "user", "content": "hi"}]},
        )
        assert status == 200
        chat = json.loads(raw_chat)
        assert chat["choices"][0]["message"]["content"] == "fake-ollama-response"
        assert any(r["path"] == "/v1/chat/completions" for r in srv.get_requests())

        # Streaming SSE /v1/chat/completions
        status, hdrs_sse, raw_sse = _http_call(
            "POST",
            srv.v1_chat_url,
            body={"model": "llama3.2:latest", "stream": True, "messages": [{"role": "user", "content": "hi"}]},
        )
        assert status == 200
        assert "text/event-stream" in hdrs_sse.get("content-type", "")
        sse_text = raw_sse.decode("utf-8")
        assert "data: [DONE]" in sse_text
        assert "fake-ollama-response" in sse_text

        # strict_models=True returns 404 on unknown model
        s_404_gen, _, _ = _http_call(
            "POST",
            f"{srv.base_url}/api/generate",
            body={"model": "nonexistent:99b", "prompt": "hi", "stream": False},
        )
        assert s_404_gen == 404

        s_404_chat, _, _ = _http_call(
            "POST",
            srv.v1_chat_url,
            body={"model": "nonexistent:99b", "messages": []},
        )
        assert s_404_chat == 404

        # Error injection on /api/ps and /api/generate, cleared by reset()
        srv.set_error("/api/ps", 500, {"error": "injected ps outage"})
        s_err_ps, _, b_err_ps = _http_call("GET", f"{srv.base_url}/api/ps")
        assert s_err_ps == 500
        assert json.loads(b_err_ps)["error"] == "injected ps outage"

        srv.set_error("/api/generate", 503)
        s_err_gen, _, _ = _http_call(
            "POST",
            f"{srv.base_url}/api/generate",
            body={"model": "llama3.2:latest", "prompt": "x"},
        )
        assert s_err_gen == 503

        srv.reset()
        s_after_reset, _, _ = _http_call("GET", f"{srv.base_url}/api/ps")
        assert s_after_reset == 200
        assert srv.get_requests() == [{"method": "GET", "path": "/api/ps", "headers": srv.get_requests()[0]["headers"], "body": None}]


# ---------------------------------------------------------------------------
# 2. FakeComfyUIServer self-checks
# ---------------------------------------------------------------------------


def test_fake_comfyui_ws_prompt_history_view_and_free(fake_comfyui: FakeComfyUIServer) -> None:
    client_id = "e2e-comfy-client"
    fake_comfyui.steps = 2
    fake_comfyui.step_delay_s = 0.02
    fake_comfyui.preview_format = 1  # JPEG

    with connect_ws(fake_comfyui.base_url, client_id=client_id, timeout=5.0) as ws:
        initial = ws.recv_json(timeout=2.0)
        assert initial["type"] == "status"

        # Ping/Pong health check
        ws.send_ping(b"hb")
        pong = ws.recv_frame(timeout=2.0)
        assert pong.is_pong
        assert pong.payload == b"hb"

        status, _, raw_prompt = _http_call(
            "POST",
            f"{fake_comfyui.base_url}/prompt",
            body={"prompt": {"3": {"class_type": "KSampler"}, "9": {"class_type": "SaveImage"}}, "client_id": client_id},
        )
        assert status == 200
        prompt_resp = json.loads(raw_prompt)
        pid = prompt_resp["prompt_id"]
        assert prompt_resp["node_errors"] == {}

        seen_types: list[str] = []
        preview_frames: list[tuple[int, int, bytes]] = []
        deadline = time.monotonic() + 5.0
        while time.monotonic() < deadline:
            frame = ws.recv_frame(timeout=2.0)
            if frame.is_binary:
                preview_frames.append(frame.parse_preview_image())
                continue
            if frame.is_text:
                msg = frame.json()
                mtype = str(msg.get("type"))
                seen_types.append(mtype)
                if mtype == "executing" and msg.get("data", {}).get("node") is None:
                    break

        assert "execution_start" in seen_types
        assert "progress" in seen_types
        assert "executed" in seen_types
        assert len(preview_frames) == 2
        for evt_type, img_fmt, img_bytes in preview_frames:
            assert evt_type == 1
            assert img_fmt == 1
            assert img_bytes.startswith(b"\xff\xd8\xff")
            assert img_bytes.endswith(b"\xff\xd9")

    # History populated
    status, _, raw_hist = _http_call("GET", f"{fake_comfyui.base_url}/history/{pid}")
    assert status == 200
    hist = json.loads(raw_hist)
    assert pid in hist
    assert hist[pid]["status"]["completed"] is True
    assert hist[pid]["status"]["status_str"] == "success"
    img_info = hist[pid]["outputs"]["9"]["images"][0]

    # /view returns valid PNG with exact Content-Length
    view_url = f"{fake_comfyui.base_url}/view?filename={img_info['filename']}&type=output"
    status, hdrs, img_data = _http_call("GET", view_url)
    assert status == 200
    assert hdrs["content-type"] == "image/png"
    assert int(hdrs["content-length"]) == len(img_data)
    assert img_data.startswith(b"\x89PNG\r\n\x1a\n")

    # /view path traversal rejected
    bad_status, _, _ = _http_call("GET", f"{fake_comfyui.base_url}/view?filename=../secret.png")
    assert bad_status == 400

    # /free records unload request
    free_status, _, free_body = _http_call(
        "POST",
        f"{fake_comfyui.base_url}/free",
        body={"unload_models": True, "free_memory": True},
    )
    assert free_status == 200
    assert json.loads(free_body) == {}
    assert len(fake_comfyui.free_calls) == 1
    assert fake_comfyui.free_calls[0]["unload_models"] is True


def test_fake_comfyui_png_preview_validation_error_and_supporting_routes(fake_comfyui: FakeComfyUIServer) -> None:
    fake_comfyui.steps = 1
    fake_comfyui.step_delay_s = 0.01
    fake_comfyui.preview_format = 2  # PNG
    fake_comfyui.register_artifact("custom.jpg", MINIMAL_JPEG)

    status, hdrs, jpg_bytes = _http_call("GET", f"{fake_comfyui.base_url}/view?filename=custom.jpg")
    assert status == 200
    assert hdrs["content-type"] == "image/jpeg"
    assert jpg_bytes == MINIMAL_JPEG

    with connect_ws(fake_comfyui.base_url, client_id="png-cid", timeout=5.0) as ws:
        _ = ws.recv_json(timeout=2.0)
        status, _, _ = _http_call(
            "POST",
            f"{fake_comfyui.base_url}/prompt",
            body={"prompt": {"3": {}}, "client_id": "png-cid"},
        )
        assert status == 200
        got_png = False
        for _ in range(10):
            frame = ws.recv_frame(timeout=2.0)
            if frame.is_binary:
                evt_type, img_fmt, payload = frame.parse_preview_image()
                assert (evt_type, img_fmt) == (1, 2)
                assert payload == MINIMAL_PNG
                got_png = True
                break
        assert got_png

    # Validation error mode
    fake_comfyui.set_validation_error(enabled=True)
    err_status, _, err_raw = _http_call(
        "POST",
        f"{fake_comfyui.base_url}/prompt",
        body={"prompt": {}, "client_id": "err-cid"},
    )
    assert err_status == 400
    err_json = json.loads(err_raw)
    assert err_json["error"]["type"] == "prompt_outputs_failed_validation"
    assert "4" in err_json["node_errors"]
    fake_comfyui.set_validation_error(enabled=False)

    # Supporting endpoints including GET /object_info, GET /object_info/<node>, GET /queue
    s_stats, _, raw_stats = _http_call("GET", f"{fake_comfyui.base_url}/system_stats")
    assert s_stats == 200
    assert "devices" in json.loads(raw_stats)

    s_models, _, raw_models = _http_call("GET", f"{fake_comfyui.base_url}/models")
    assert s_models == 200
    assert "loras" in json.loads(raw_models)

    s_obj_all, _, raw_obj_all = _http_call("GET", f"{fake_comfyui.base_url}/object_info")
    assert s_obj_all == 200
    obj_all = json.loads(raw_obj_all)
    assert "KSampler" in obj_all and "SaveImage" in obj_all

    s_obj_one, _, raw_obj_one = _http_call("GET", f"{fake_comfyui.base_url}/object_info/KSampler")
    assert s_obj_one == 200
    assert "KSampler" in json.loads(raw_obj_one)

    s_get_q, _, raw_get_q = _http_call("GET", f"{fake_comfyui.base_url}/queue")
    assert s_get_q == 200
    get_q = json.loads(raw_get_q)
    assert "queue_running" in get_q and "queue_pending" in get_q

    s_q, _, _ = _http_call("POST", f"{fake_comfyui.base_url}/queue", body={"delete": ["1"]})
    s_int, _, _ = _http_call("POST", f"{fake_comfyui.base_url}/interrupt", body={})
    assert s_q == 200 and s_int == 200

    # Multipart upload
    boundary = "----NeonTestBoundary"
    multipart_body = (
        f"--{boundary}\r\n"
        'Content-Disposition: form-data; name="image"; filename="mask.png"\r\n'
        "Content-Type: image/png\r\n\r\n"
    ).encode() + MINIMAL_PNG + f"\r\n--{boundary}--\r\n".encode()
    up_req = urllib.request.Request(
        f"{fake_comfyui.base_url}/upload/image",
        data=multipart_body,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
        method="POST",
    )
    with urllib.request.urlopen(up_req, timeout=5.0) as up_resp:
        up_json = json.loads(up_resp.read())
    assert up_resp.status == 200
    assert up_json["name"] == "mask.png"
    assert fake_comfyui.uploads["mask.png"] == MINIMAL_PNG


def test_fake_comfyui_execution_error_class_type_nodes_and_error_injection(fake_comfyui: FakeComfyUIServer) -> None:
    fake_comfyui.steps = 1
    fake_comfyui.step_delay_s = 0.01

    # class_type selection when SaveImage appears BEFORE KSampler in dict order
    with connect_ws(fake_comfyui.base_url, client_id="order-cid", timeout=5.0) as ws_order:
        _ = ws_order.recv_json(timeout=2.0)
        # Unrelated WS client must NOT receive order-cid events
        with connect_ws(fake_comfyui.base_url, client_id="other-cid", timeout=5.0) as ws_other:
            _ = ws_other.recv_json(timeout=2.0)
            workflow = {
                "1": {"class_type": "SaveImage"},
                "2": {"class_type": "KSampler"},
                "9": {"class_type": "CheckpointLoaderSimple"},
            }
            s_ok, _, raw_ok = _http_call(
                "POST",
                f"{fake_comfyui.base_url}/prompt",
                body={"prompt": workflow, "client_id": "order-cid"},
            )
            assert s_ok == 200
            pid_ok = json.loads(raw_ok)["prompt_id"]

            progress_nodes: list[str] = []
            executed_node: str | None = None
            deadline = time.monotonic() + 5.0
            while time.monotonic() < deadline:
                frame = ws_order.recv_frame(timeout=2.0)
                if frame.is_text:
                    msg = frame.json()
                    if msg.get("type") == "progress":
                        progress_nodes.append(str(msg["data"]["node"]))
                    elif msg.get("type") == "executed":
                        executed_node = str(msg["data"]["node"])
                    elif msg.get("type") == "executing" and msg.get("data", {}).get("node") is None:
                        break
            assert progress_nodes == ["2"]
            assert executed_node == "1"

            # Verify other-cid got no stray messages for order-cid
            try:
                ws_other.recv_frame(timeout=0.1)
                raise AssertionError("other-cid unexpectedly received events for order-cid")
            except TimeoutError:
                pass

    _, _, raw_h_ok = _http_call("GET", f"{fake_comfyui.base_url}/history/{pid_ok}")
    h_ok = json.loads(raw_h_ok)[pid_ok]
    assert "1" in h_ok["outputs"]
    assert "9" not in h_ok["outputs"]

    # set_execution_error triggers execution_error WS event + error status in history
    fake_comfyui.set_execution_error("CUDA out of memory in KSampler")
    with connect_ws(fake_comfyui.base_url, client_id="exec-err-cid", timeout=5.0) as ws_err:
        _ = ws_err.recv_json(timeout=2.0)
        s_p, _, raw_p = _http_call(
            "POST",
            f"{fake_comfyui.base_url}/prompt",
            body={"prompt": {"5": {"class_type": "KSampler"}, "6": {"class_type": "SaveImage"}}, "client_id": "exec-err-cid"},
        )
        assert s_p == 200
        pid_err = json.loads(raw_p)["prompt_id"]

        got_err_msg: dict[str, Any] | None = None
        deadline = time.monotonic() + 5.0
        while time.monotonic() < deadline:
            frame = ws_err.recv_frame(timeout=2.0)
            if frame.is_text:
                msg = frame.json()
                if msg.get("type") == "execution_error":
                    got_err_msg = msg
                elif msg.get("type") == "status" and msg.get("data", {}).get("status", {}).get("exec_info", {}).get("queue_remaining") == 0 and got_err_msg is not None:
                    break
        assert got_err_msg is not None
        assert "CUDA out of memory" in got_err_msg["data"]["exception_message"]

    _, _, raw_h_err = _http_call("GET", f"{fake_comfyui.base_url}/history/{pid_err}")
    h_err = json.loads(raw_h_err)[pid_err]
    assert h_err["status"]["status_str"] == "error"
    assert h_err["outputs"] == {}

    # HTTP error injection on /free and /system_stats, cleared by reset()
    fake_comfyui.set_error("/free", 503)
    fake_comfyui.set_error("/system_stats", 500)
    assert _http_call("POST", f"{fake_comfyui.base_url}/free", body={})[0] == 503
    assert _http_call("GET", f"{fake_comfyui.base_url}/system_stats")[0] == 500

    fake_comfyui.reset()
    assert _http_call("POST", f"{fake_comfyui.base_url}/free", body={})[0] == 200
    assert _http_call("GET", f"{fake_comfyui.base_url}/system_stats")[0] == 200


# ---------------------------------------------------------------------------
# 3. FakeHFHubServer self-checks
# ---------------------------------------------------------------------------


def test_fake_hf_hub_whoami_head_policies_redirect_and_sha256(fake_hf_hub: FakeHFHubServer) -> None:
    fake_hf_hub.set_valid_tokens({"tok_ok": "alice", "tok_unlicensed": "bob"})
    payload = b"safetensors-binary-content-" * 32
    expected_sha = fake_hf_hub.register_file(
        "black-forest-labs/FLUX.1-dev",
        "flux1-dev.safetensors",
        payload,
        gated=True,
        required_token="tok_ok",
        redirect_to_cdn=True,
    )
    fake_hf_hub.register_file(
        "public-org/open-model",
        "config.json",
        b'{"arch": "sdxl"}',
        gated=False,
        redirect_to_cdn=False,
    )

    # whoami-v2
    s_ok, _, b_ok = _http_call("GET", f"{fake_hf_hub.base_url}/api/whoami-v2", headers={"Authorization": "Bearer tok_ok"})
    assert s_ok == 200
    assert json.loads(b_ok)["name"] == "alice"

    s_bad, _, _ = _http_call("GET", f"{fake_hf_hub.base_url}/api/whoami-v2", headers={"Authorization": "Bearer wrong"})
    assert s_bad == 401

    # HEAD policies without redirect
    gated_url = f"{fake_hf_hub.base_url}/black-forest-labs/FLUX.1-dev/resolve/main/flux1-dev.safetensors"
    s_302, h_302, b_302 = _http_call(
        "HEAD",
        gated_url,
        headers={"Authorization": "Bearer tok_ok"},
        follow_redirects=False,
    )
    assert s_302 == 302
    assert b_302 == b""
    assert "/cdn/black-forest-labs/FLUX.1-dev/main/flux1-dev.safetensors" in h_302["location"]
    assert len(h_302["x-repo-commit"]) == 40
    assert h_302["x-linked-etag"] == f'"{expected_sha}"'
    assert int(h_302["x-linked-size"]) == len(payload)

    s_403, h_403, _ = _http_call(
        "HEAD",
        gated_url,
        headers={"Authorization": "Bearer tok_unlicensed"},
        follow_redirects=False,
    )
    assert s_403 == 403
    assert h_403["x-error-code"] == "GatedRepo"

    s_401, _, _ = _http_call("HEAD", gated_url, follow_redirects=False)
    assert s_401 == 401

    s_404, _, _ = _http_call(
        "HEAD",
        f"{fake_hf_hub.base_url}/black-forest-labs/FLUX.1-dev/resolve/main/missing.bin",
        headers={"Authorization": "Bearer tok_ok"},
        follow_redirects=False,
    )
    assert s_404 == 404

    # Direct 200 HEAD on non-redirect file
    pub_url = f"{fake_hf_hub.base_url}/public-org/open-model/resolve/main/config.json"
    s_200, h_200, b_200 = _http_call("HEAD", pub_url, follow_redirects=False)
    assert s_200 == 200
    assert b_200 == b""
    assert int(h_200["content-length"]) == len(b'{"arch": "sdxl"}')

    # GET following 302 to /cdn/... and verifying SHA-256 + Range 206 + 416 + auth capture
    s_dl, h_dl, dl_bytes = _http_call("GET", gated_url, headers={"Authorization": "Bearer tok_ok"}, follow_redirects=True)
    assert s_dl == 200
    assert int(h_dl["content-length"]) == len(payload)
    assert hashlib.sha256(dl_bytes).hexdigest() == fake_hf_hub.sha256_of("black-forest-labs/FLUX.1-dev", "flux1-dev.safetensors")

    s_rng, h_rng, rng_bytes = _http_call(
        "GET",
        f"{fake_hf_hub.base_url}/cdn/black-forest-labs/FLUX.1-dev/main/flux1-dev.safetensors",
        headers={"Range": "bytes=0-15"},
    )
    assert s_rng == 206
    assert h_rng["content-range"].startswith("bytes 0-15/")
    assert rng_bytes == payload[:16]

    s_416, h_416, _ = _http_call(
        "GET",
        f"{fake_hf_hub.base_url}/cdn/black-forest-labs/FLUX.1-dev/main/flux1-dev.safetensors",
        headers={"Range": f"bytes={len(payload) + 100}-{len(payload) + 200}"},
    )
    assert s_416 == 416
    assert h_416["content-range"] == f"bytes */{len(payload)}"

    # Model metadata + Authorization log check
    s_meta, _, b_meta = _http_call(
        "GET",
        f"{fake_hf_hub.base_url}/api/models/black-forest-labs/FLUX.1-dev",
        headers={"Authorization": "Bearer tok_ok"},
    )
    assert s_meta == 200
    assert json.loads(b_meta)["siblings"][0]["rfilename"] == "flux1-dev.safetensors"
    assert any(r["authorization"] == "Bearer tok_ok" for r in fake_hf_hub.requests_log)


def test_fake_hf_hub_edge_cases_and_reset() -> None:
    with FakeHFHubServer(
        valid_tokens={"tok_valid": "user1"},
        reject_invalid_tokens_on_public=True,
    ) as srv:
        # Single-segment repo + revision containing '/' + 307 redirect status
        srv.register_file("gpt2", "config.json", b'{"model_type":"gpt2"}', revision="refs/pr/1", status=307, redirect_to_cdn=True)
        srv.register_file("org/err-repo", "missing.bin", b"", gated=True, status=404)

        # Public repo allows anonymous request, rejects bad token with 401
        pub_url = f"{srv.base_url}/gpt2/resolve/refs/pr/1/config.json"
        s_307, h_307, _ = _http_call("HEAD", pub_url, follow_redirects=False)
        assert s_307 == 307
        assert h_307["location"].endswith("/cdn/gpt2/refs/pr/1/config.json")

        s_dl, _, dl_body = _http_call("GET", pub_url, follow_redirects=True)
        assert s_dl == 200
        assert dl_body == b'{"model_type":"gpt2"}'

        s_bad_tok, _, _ = _http_call("HEAD", pub_url, headers={"Authorization": "Bearer bad_tok"}, follow_redirects=False)
        assert s_bad_tok == 401

        # handle_model_info preserves entry.status (404 rather than collapsing to 403)
        s_info_404, _, _ = _http_call(
            "GET",
            f"{srv.base_url}/api/models/org/err-repo",
            headers={"Authorization": "Bearer tok_valid"},
        )
        assert s_info_404 == 404

        srv.set_reject_invalid_tokens_on_public(False)
        srv.reset()
        assert srv.requests_log == []
        s_after_reset, _, _ = _http_call("HEAD", pub_url, follow_redirects=False)
        assert s_after_reset == 404
        # Constructor default reject_invalid_tokens_on_public=True is preserved across reset()
        srv.register_file("gpt2", "after_reset.bin", b"ok", redirect_to_cdn=False)
        s_bad_after_reset, _, _ = _http_call(
            "HEAD",
            f"{srv.base_url}/gpt2/resolve/main/after_reset.bin",
            headers={"Authorization": "Bearer bad_tok"},
            follow_redirects=False,
        )
        assert s_bad_after_reset == 401


# ---------------------------------------------------------------------------
# 4. Server Lifecycle Safety (close without start, WS teardown)
# ---------------------------------------------------------------------------


def test_fake_servers_close_without_start_and_comfyui_ws_teardown() -> None:
    for cls in (FakeOllamaServer, FakeComfyUIServer, FakeHFHubServer):
        srv = cls()
        t = threading.Thread(target=srv.close, daemon=True)
        t.start()
        t.join(timeout=1.0)
        assert not t.is_alive(), f"{cls.__name__}.close() hung when start() was never called"

    comfy = FakeComfyUIServer().start()
    ws = connect_ws(comfy.base_url, client_id="teardown-check", timeout=2.0)
    _ = ws.recv_json(timeout=2.0)
    assert len(comfy._ws_clients) == 1
    comfy.close()
    assert len(comfy._ws_clients) == 0
    ws.close()


# ---------------------------------------------------------------------------
# 5. Live StudioServer, SSE, POST/Host/Origin, and Workspace Isolation
# ---------------------------------------------------------------------------


def test_live_studio_server_status_sse_and_isolation(tmp_path: Path) -> None:
    real_neon_root = Path(__file__).resolve().parents[2]
    real_studio_log = real_neon_root / "studio.log"
    before_stat = real_studio_log.stat() if real_studio_log.exists() else None
    real_home_before = Path.home()

    # Pre-import run_local_model and run_cloud_api before entering IsolatedWorkspace to verify non-whitelisted scripts/ re-rooting
    run_local_model = importlib.import_module("run_local_model")
    run_cloud_api = importlib.import_module("run_cloud_api")
    gpu_lease = importlib.import_module("local_runners.gpu_lease")
    crew = importlib.import_module("crew")
    studio_index = importlib.import_module("studio_index")
    config = importlib.import_module("studio_app.config")
    orig_root = config.ROOT
    orig_env_path = config.ENV_PATH

    with IsolatedWorkspace(base_dir=tmp_path / "iso_ws") as ws, StudioHarness(workspace=ws) as harness:
        bookkit = importlib.import_module("bookkit")
        layout = importlib.import_module("layout")
        jobs = importlib.import_module("studio_app.jobs")
        studio_log = importlib.import_module("studio_app.log")
        session = importlib.import_module("studio_app.session")

        # Isolation assertions: nothing points to real Neon repo or real home
        assert ws.root == config.ROOT
        assert ws.root == layout.ROOT
        assert ws.root == bookkit.ROOT
        assert ws.root == run_local_model.ROOT
        assert ws.home == run_cloud_api.CLOUD_KEYS_FILE.parents[1]
        assert str(ws.home) in config.ENV_PATH or str(real_home_before) not in config.ENV_PATH
        assert ws.root / ".studio_session.json" == session.SESSION_FILE
        assert ws.root / "studio.log" == studio_log.LOG_FILE
        assert Path.home() == ws.home
        assert os.environ["HF_HOME"] == str(ws.hf_home)
        assert os.environ["STUDIO_JOB_DIR"] == str(ws.job_dir)
        assert os.environ["STUDIO_GEN_DIR"] == str(ws.gen_dir)
        assert os.environ["STUDIO_GPU_ENVS"] == str(ws.gpu_envs_dir)
        assert os.environ["STUDIO_CACHE"] == str(ws.cache_dir)
        assert real_neon_root not in config.PROJECTS.parents
        assert gpu_lease._DEFAULT_MANAGER is None

        # Read-only bundled asset dirs preserved
        assert crew.CREW_DIR.is_dir()
        assert crew.RECIPES_DIR.is_dir()
        assert studio_index.SCHEMA.is_file()

        # Logger handlers point ONLY inside ws.root (never Neon/studio.log)
        studio_logger = logging.getLogger("studio")
        file_handlers = [h for h in studio_logger.handlers if isinstance(h, logging.FileHandler)]
        assert len(file_handlers) == 1
        assert Path(file_handlers[0].baseFilename).resolve() == (ws.root / "studio.log").resolve()

        # Unauthenticated request rejected; bad Host and bad Origin rejected
        assert harness.get("/api/status", auth=False).status == 403
        assert harness.request("GET", "/api/status", host="evil.example:1234").status == 403
        assert harness.request("GET", "/api/status", origin="http://evil.example").status == 403

        # Authenticated /api/status succeeds and creates dirs ONLY inside isolated workspace
        resp = harness.get("/api/status")
        assert resp.status == 200
        data = resp.json()
        for key in ("tools", "projects", "gpus", "gpu_profile", "image_models", "video_models"):
            assert key in data
        assert (ws.root / "projects" / "books").is_dir()

        # StudioHarness.post() works against POST route (including explicit Content-Length without duplicate header)
        post_resp = harness.post("/api/project/global_params", json_body={"book": "nonexistent_slug"})
        assert post_resp.status in {400, 404}
        explicit_bytes = json.dumps({"book": "nonexistent_slug"}).encode("utf-8")
        post_cl_resp = harness.post(
            "/api/project/global_params",
            raw_body=explicit_bytes,
            headers={"Content-Type": "application/json", "Content-Length": str(len(explicit_bytes))},
        )
        assert post_cl_resp.status in {400, 404}

        # Dynamically imported module carrying ENV_PATH string is restored on exit
        results_mod = importlib.import_module("studio_app.results")
        assert str(ws.home) in results_mod.ENV_PATH or str(real_home_before) not in results_mod.ENV_PATH

        # Emit studio log + SSE /api/v1/events and confirm Neon/studio.log untouched
        studio_log.get_logger("selfcheck").info("isolated log entry")
        jobs.JOB.log("e2e selfcheck log line")
        events = harness.read_sse_events("/api/v1/events?seconds=0.8")
        assert any(e.retry == 3000 for e in events)
        assert any(e.event == "log" and e.json() == "e2e selfcheck log line" for e in events)
        assert any(e.event == "status" and "running" in e.json() for e in events)
        assert (ws.root / "studio.log").is_file()

        # Confirm Pillow can parse our minimal images cleanly (sanity check on test assets)
        from PIL import Image

        im_png = Image.open(io.BytesIO(MINIMAL_PNG))
        im_png.load()
        im_jpg = Image.open(io.BytesIO(MINIMAL_JPEG))
        im_jpg.load()
        assert im_png.format == "PNG"
        assert im_jpg.format == "JPEG"

    # Post-exit restoration checks
    assert orig_root == config.ROOT
    assert orig_env_path == config.ENV_PATH
    assert orig_env_path == results_mod.ENV_PATH
    assert orig_root == run_local_model.ROOT
    assert Path.home() == real_home_before
    assert real_home_before == run_cloud_api.CLOUD_KEYS_FILE.parents[1]
    assert "STUDIO_GEN_DIR" not in os.environ or os.environ["STUDIO_GEN_DIR"] != str(ws.gen_dir)

    after_stat = real_studio_log.stat() if real_studio_log.exists() else None
    if before_stat is None:
        assert after_stat is None, "IsolatedWorkspace created real Neon/studio.log!"
    else:
        assert after_stat is not None
        assert after_stat.st_size == before_stat.st_size
        assert after_stat.st_mtime_ns == before_stat.st_mtime_ns


# ---------------------------------------------------------------------------
# 6. Hardware Profile Fixtures & STUDIO_RUN_E2E Collection Gating self-checks
# ---------------------------------------------------------------------------


def test_hardware_profile_fixtures(
    full_48g_profile: dict[str, Any],
    mac_8g_lite_profile: dict[str, Any],
) -> None:
    gpus = importlib.import_module("studio_app.gpus")
    expected_13_keys = {
        "platform",
        "backend",
        "name",
        "vram_gb",
        "ram_gb",
        "compute_cap",
        "is_blackwell",
        "tier",
        "supports_local_video",
        "supports_local_images",
        "default_image_backend",
        "default_video_backend",
        "legacy_cloud",
    }
    live_keys = set(gpus.gpu_profile())
    assert live_keys == expected_13_keys

    assert set(full_48g_profile) == expected_13_keys
    assert full_48g_profile["tier"] == "full_48g"
    assert full_48g_profile["vram_gb"] == 48.0
    assert full_48g_profile["ram_gb"] == 64.0
    assert full_48g_profile["is_blackwell"] is True
    assert full_48g_profile["supports_local_video"] is True
    assert FULL_48G_PLATFORM_TAG == "win_cuda"

    assert set(mac_8g_lite_profile) == expected_13_keys
    assert mac_8g_lite_profile["tier"] == "mac_8g_lite"
    assert mac_8g_lite_profile["vram_gb"] == 8.0
    assert mac_8g_lite_profile["ram_gb"] == 8.0
    assert mac_8g_lite_profile["supports_local_video"] is False
    assert mac_8g_lite_profile["default_image_backend"] == "sd_cli"
    assert MAC_8G_PLATFORM_TAG == "mac_metal"


def test_studio_run_e2e_collection_gating() -> None:
    neon_root = Path(__file__).resolve().parents[2]
    base_env = {k: v for k, v in os.environ.items() if k not in {"STUDIO_RUN_E2E", "PYTEST_ADDOPTS"}}

    proc_off = subprocess.run(
        [sys.executable, "-m", "pytest", "--collect-only", "-q"],
        cwd=str(neon_root),
        env=base_env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc_off.returncode == 0
    assert "test_infra_selfcheck.py" not in proc_off.stdout

    env_zero = dict(base_env)
    env_zero["STUDIO_RUN_E2E"] = "0"
    proc_zero = subprocess.run(
        [sys.executable, "-m", "pytest", "tests/e2e/test_infra_selfcheck.py", "-v"],
        cwd=str(neon_root),
        env=env_zero,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc_zero.returncode == 0
    assert "skipped" in proc_zero.stdout

    env_on = dict(base_env)
    env_on["STUDIO_RUN_E2E"] = "1"
    proc_on = subprocess.run(
        [sys.executable, "-m", "pytest", "tests/e2e/test_infra_selfcheck.py", "--collect-only", "-o", "addopts="],
        cwd=str(neon_root),
        env=env_on,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc_on.returncode == 0
    assert "test_studio_run_e2e_collection_gating" in proc_on.stdout


# ---------------------------------------------------------------------------
# 7. Concurrency Burst (Accept Backlog) & Adversarial HTTP Input Edge Cases
# ---------------------------------------------------------------------------


def test_fake_servers_concurrent_burst_no_connection_reset() -> None:
    targets: list[tuple[Any, str, dict[str, str]]] = [
        (FakeOllamaServer(), "/api/ps", {}),
        (FakeComfyUIServer(), "/system_stats", {}),
        (FakeHFHubServer(), "/api/whoami-v2", {"Authorization": "Bearer hf_test_valid"}),
    ]
    num_threads = 16
    reqs_per_thread = 10

    for srv, path, hdrs in targets:
        with srv:
            barrier = threading.Barrier(num_threads)
            errors: list[str] = []
            statuses: list[int] = []
            lock = threading.Lock()

            def _worker(
                url: str = f"{srv.base_url}{path}",
                req_hdrs: dict[str, str] = hdrs,
                b: threading.Barrier = barrier,
                errs: list[str] = errors,
                codes: list[int] = statuses,
                lk: threading.Lock = lock,
            ) -> None:
                try:
                    b.wait(timeout=5.0)
                    for _ in range(reqs_per_thread):
                        status, _, _ = _http_call("GET", url, headers=req_hdrs)
                        with lk:
                            codes.append(status)
                except Exception as exc:  # pragma: no cover - assertion checks empty
                    with lk:
                        errs.append(repr(exc))

            threads = [threading.Thread(target=_worker) for _ in range(num_threads)]
            for t in threads:
                t.start()
            for t in threads:
                t.join(timeout=15.0)
                assert not t.is_alive()

            assert errors == [], f"{type(srv).__name__} hit concurrency errors: {errors[:5]}"
            assert len(statuses) == num_threads * reqs_per_thread
            assert all(code == 200 for code in statuses), f"{type(srv).__name__} non-200 statuses: {set(statuses)}"


def _send_raw_http_request(host: str, port: int, raw_req: bytes) -> str:
    with socket.create_connection((host, port), timeout=5.0) as sock:
        sock.sendall(raw_req)
        chunks: list[bytes] = []
        while True:
            data = sock.recv(4096)
            if not data:
                break
            chunks.append(data)
    return b"".join(chunks).decode("latin-1", errors="replace")


def test_fake_comfyui_negative_content_length_and_reset_drains_workers() -> None:
    with FakeComfyUIServer(steps=6, step_delay_s=0.1) as comfy:
        for path in ("/upload/image", "/prompt"):
            raw_req = (
                f"POST {path} HTTP/1.1\r\n"
                f"Host: 127.0.0.1:{comfy.port}\r\n"
                "Content-Length: -5\r\n"
                "Connection: close\r\n\r\n"
            ).encode("ascii")
            resp_text = _send_raw_http_request(comfy.host, comfy.port, raw_req)
            status_line = resp_text.splitlines()[0]
            assert "400" in status_line, f"Expected 400 on {path}, got: {status_line}"

        # Reset while a prompt worker is mid-execution drains it before clearing state
        s_p, _, _ = _http_call(
            "POST",
            f"{comfy.base_url}/prompt",
            body={"prompt": {"3": {"class_type": "KSampler"}, "9": {"class_type": "SaveImage"}}},
        )
        assert s_p == 200
        comfy.reset()
        assert comfy.prompts == []
        assert comfy.history == {}
        s_q, _, raw_q = _http_call("GET", f"{comfy.base_url}/queue")
        assert s_q == 200
        assert json.loads(raw_q)["queue_running"] == []

        # Server remains usable after reset()
        comfy.steps = 1
        comfy.step_delay_s = 0.01
        with connect_ws(comfy.base_url, client_id="post-reset", timeout=5.0) as ws:
            _ = ws.recv_json(timeout=2.0)
            s_p2, _, raw_p2 = _http_call(
                "POST",
                f"{comfy.base_url}/prompt",
                body={"prompt": {"3": {"class_type": "KSampler"}, "9": {"class_type": "SaveImage"}}, "client_id": "post-reset"},
            )
            assert s_p2 == 200
            pid2 = json.loads(raw_p2)["prompt_id"]
            deadline = time.monotonic() + 5.0
            got_exec = False
            while time.monotonic() < deadline:
                frame = ws.recv_frame(timeout=2.0)
                if frame.is_text and frame.json().get("type") == "executed":
                    got_exec = True
                    break
            assert got_exec
        s_h2, _, raw_h2 = _http_call("GET", f"{comfy.base_url}/history/{pid2}")
        assert s_h2 == 200
        assert pid2 in json.loads(raw_h2)

    with FakeOllamaServer() as ollama:
        raw_req = (
            f"POST /v1/chat/completions HTTP/1.1\r\n"
            f"Host: 127.0.0.1:{ollama.port}\r\n"
            "Content-Length: -5\r\n"
            "Connection: close\r\n\r\n"
        ).encode("ascii")
        resp_text = _send_raw_http_request(ollama.host, ollama.port, raw_req)
        assert "400" in resp_text.splitlines()[0]
