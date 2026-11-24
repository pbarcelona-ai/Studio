"""Loopback fake Ollama HTTP server (native /api/* and OpenAI-compatible /v1/*) for E2E tests."""
from __future__ import annotations

import json
import threading
import time
from datetime import UTC, datetime
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import urlparse


def _iso_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _default_model_record(
    name: str,
    *,
    size: int = 2_019_377_152,
    size_vram: int | None = None,
    context_length: int = 4096,
) -> dict[str, Any]:
    vram = size if size_vram is None else size_vram
    return {
        "name": name,
        "model": name,
        "size": size,
        "size_vram": vram,
        "digest": f"sha256:{name.encode('utf-8').hex():0<64}"[:71],
        "modified_at": _iso_now(),
        "expires_at": "2026-12-31T23:59:59Z",
        "context_length": context_length,
        "details": {
            "parent_model": "",
            "format": "gguf",
            "family": "qwen2",
            "families": ["qwen2"],
            "parameter_size": "3.1B",
            "quantization_level": "Q4_K_M",
        },
    }


def _is_zero_keep_alive(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, bool):
        return False
    if isinstance(value, (int, float)):
        return float(value) == 0.0
    if isinstance(value, str):
        text = value.strip().lower()
        return text in {"0", "0.0", "0s", "0m", "0h", "0ms"}
    return False


class _OllamaHTTPServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True
    request_queue_size = 128

    def __init__(self, server_address: tuple[str, int], fake: FakeOllamaServer) -> None:
        self.fake = fake
        super().__init__(server_address, _OllamaHandler)


class _OllamaHandler(BaseHTTPRequestHandler):
    server: _OllamaHTTPServer
    protocol_version = "HTTP/1.1"

    def log_message(self, format: str, *args: Any) -> None:
        return

    def _send_bytes(self, status: int, content_type: str, payload: bytes) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Connection", "close")
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(payload)

    def _send_json(self, status: int, obj: Any) -> None:
        self._send_bytes(status, "application/json", json.dumps(obj).encode("utf-8"))

    def _read_json(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length") or "0")
        if length < 0:
            raise ValueError(f"negative Content-Length: {length}")
        raw = self.rfile.read(length) if length > 0 else b"{}"
        if not raw.strip():
            return {}
        parsed = json.loads(raw.decode("utf-8"))
        return parsed if isinstance(parsed, dict) else {}

    def _maybe_send_injected_error(self, path: str) -> bool:
        err = self.server.fake.get_error(path)
        if err is None:
            return False
        status, ctype, payload = err
        self._send_bytes(status, ctype, payload)
        return True

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path
        fake = self.server.fake
        fake.record_request("GET", path, dict(self.headers), None)

        if self._maybe_send_injected_error(path):
            return

        if path == "/":
            self._send_bytes(HTTPStatus.OK, "text/plain; charset=utf-8", b"Ollama is running")
            return
        if path == "/api/ps":
            self._send_json(HTTPStatus.OK, {"models": fake.get_loaded_models()})
            return
        if path == "/api/tags":
            self._send_json(HTTPStatus.OK, {"models": fake.get_available_models()})
            return
        if path == "/v1/models":
            models = fake.get_available_models()
            data = [
                {
                    "id": m["name"],
                    "object": "model",
                    "created": int(time.time()),
                    "owned_by": "ollama",
                }
                for m in models
            ]
            self._send_json(HTTPStatus.OK, {"object": "list", "data": data})
            return
        self._send_json(HTTPStatus.NOT_FOUND, {"error": f"not found: {path}"})

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path
        fake = self.server.fake
        try:
            body = self._read_json()
        except ValueError as exc:
            self._send_json(HTTPStatus.BAD_REQUEST, {"error": f"invalid json: {exc}"})
            return

        fake.record_request("POST", path, dict(self.headers), body)

        if self._maybe_send_injected_error(path):
            return

        if path == "/api/generate":
            status, ctype, payload = fake.handle_generate(body)
            self._send_bytes(status, ctype, payload)
            return
        if path == "/v1/chat/completions":
            status, ctype, payload = fake.handle_chat_completions(body)
            self._send_bytes(status, ctype, payload)
            return
        self._send_json(HTTPStatus.NOT_FOUND, {"error": f"not found: {path}"})


class FakeOllamaServer:
    """Thread-safe loopback Ollama server supporting /api/* and /v1/* endpoints."""

    def __init__(
        self,
        *,
        available_models: list[str] | list[dict[str, Any]] | None = None,
        loaded_models: list[dict[str, Any]] | None = None,
        strict_models: bool = False,
        default_reply: str = "fake-ollama-response",
    ) -> None:
        self._lock = threading.Lock()
        self._strict_models = strict_models
        self._default_reply = default_reply
        self._available: dict[str, dict[str, Any]] = {}
        self._loaded: dict[str, dict[str, Any]] = {}
        self._errors: dict[str, tuple[int, str, bytes]] = {}
        self.requests: list[dict[str, Any]] = []
        self.evictions: list[dict[str, Any]] = []

        if available_models is None:
            self.set_available_models(["qwen2.5:3b"])
        else:
            self.set_available_models(available_models)

        if loaded_models is not None:
            self.set_loaded_models(loaded_models)

        self._httpd = _OllamaHTTPServer(("127.0.0.1", 0), self)
        self._thread: threading.Thread | None = None

    @property
    def host(self) -> str:
        return "127.0.0.1"

    @property
    def port(self) -> int:
        return int(self._httpd.server_port)

    @property
    def base_url(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    @property
    def v1_chat_url(self) -> str:
        return f"{self.base_url}/v1/chat/completions"

    @property
    def v1_models_url(self) -> str:
        return f"{self.base_url}/v1/models"

    def start(self) -> FakeOllamaServer:
        if self._thread is None:
            self._thread = threading.Thread(target=self._httpd.serve_forever, daemon=True)
            self._thread.start()
        return self

    def close(self) -> None:
        if self._thread is not None:
            self._httpd.shutdown()
            self._thread.join(timeout=2.0)
            self._thread = None
        self._httpd.server_close()

    def __enter__(self) -> FakeOllamaServer:
        return self.start()

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self.close()

    def set_error(self, endpoint: str, status: int | None, body: Any = None) -> None:
        key = endpoint if endpoint.startswith("/") else f"/{endpoint}"
        with self._lock:
            if status is None:
                self._errors.pop(key, None)
                return
            if body is None:
                payload = json.dumps({"error": f"injected error {status} on {key}"}).encode("utf-8")
                ctype = "application/json"
            elif isinstance(body, bytes):
                payload = body
                ctype = "application/json"
            elif isinstance(body, str):
                payload = body.encode("utf-8")
                ctype = "text/plain; charset=utf-8"
            else:
                payload = json.dumps(body).encode("utf-8")
                ctype = "application/json"
            self._errors[key] = (int(status), ctype, payload)

    def clear_errors(self) -> None:
        with self._lock:
            self._errors.clear()

    def get_error(self, path: str) -> tuple[int, str, bytes] | None:
        with self._lock:
            return self._errors.get(path)

    def record_request(self, method: str, path: str, headers: dict[str, str], body: dict[str, Any] | None) -> None:
        with self._lock:
            self.requests.append({
                "method": method,
                "path": path,
                "headers": headers,
                "body": body,
            })

    def get_requests(self) -> list[dict[str, Any]]:
        with self._lock:
            return [dict(r) for r in self.requests]

    def get_evictions(self) -> list[dict[str, Any]]:
        class _EvictionRecord(dict[str, Any]):
            def __eq__(self, other: object) -> bool:
                if isinstance(other, str):
                    return self.get("model") == other
                return super().__eq__(other)

        with self._lock:
            return [_EvictionRecord(e) for e in self.evictions]

    def set_available_models(self, models: list[str] | list[dict[str, Any]]) -> None:
        with self._lock:
            self._available.clear()
            for item in models:
                if isinstance(item, str):
                    rec = _default_model_record(item)
                else:
                    name = str(item.get("name") or item.get("model") or "")
                    rec = _default_model_record(
                        name,
                        size=int(item.get("size", 2_019_377_152)),
                        size_vram=int(item["size_vram"]) if "size_vram" in item else None,
                        context_length=int(item.get("context_length", 4096)),
                    )
                    rec.update(item)
                    rec.setdefault("name", name)
                    rec.setdefault("model", name)
                self._available[rec["name"]] = rec

    def set_loaded_models(self, models: list[dict[str, Any]] | dict[str, dict[str, Any]]) -> None:
        with self._lock:
            self._loaded.clear()
            items = list(models.values()) if isinstance(models, dict) else models
            for item in items:
                name = str(item.get("name") or item.get("model") or "")
                rec = _default_model_record(
                    name,
                    size=int(item.get("size", 2_019_377_152)),
                    size_vram=int(item["size_vram"]) if "size_vram" in item else None,
                    context_length=int(item.get("context_length", 4096)),
                )
                rec.update(item)
                rec.setdefault("name", name)
                rec.setdefault("model", name)
                self._loaded[rec["name"]] = rec

    def load_model(
        self,
        name: str,
        *,
        size_vram: int = 2_019_377_152,
        size: int | None = None,
        context_length: int = 4096,
    ) -> dict[str, Any]:
        with self._lock:
            rec = _default_model_record(
                name,
                size=size_vram if size is None else size,
                size_vram=size_vram,
                context_length=context_length,
            )
            self._available.setdefault(name, dict(rec))
            self._loaded[name] = rec
            return dict(rec)

    def unload_model(self, name: str) -> bool:
        with self._lock:
            return self._unload_locked(name)

    @staticmethod
    def _tag_candidates(name: str) -> list[str]:
        candidates = [name]
        if ":" not in name:
            candidates.append(f"{name}:latest")
        elif name.endswith(":latest"):
            candidates.append(name.removesuffix(":latest"))
        return candidates

    def _resolve_available_locked(self, name: str) -> tuple[str, dict[str, Any]] | None:
        for key in self._tag_candidates(name):
            if key in self._available:
                return key, self._available[key]
        return None

    def _unload_locked(self, name: str) -> bool:
        removed = False
        for key in self._tag_candidates(name):
            if key in self._loaded:
                del self._loaded[key]
                removed = True
        return removed

    def get_loaded_models(self) -> list[dict[str, Any]]:
        with self._lock:
            return [dict(m) for m in self._loaded.values()]

    def get_available_models(self) -> list[dict[str, Any]]:
        with self._lock:
            return [dict(m) for m in self._available.values()]

    def reset(self) -> None:
        with self._lock:
            self._loaded.clear()
            self._errors.clear()
            self.requests.clear()
            self.evictions.clear()
            self._available.clear()
            rec = _default_model_record("qwen2.5:3b")
            self._available[rec["name"]] = rec

    def handle_generate(self, body: dict[str, Any]) -> tuple[int, str, bytes]:
        model = str(body.get("model") or "").strip()
        if not model:
            return HTTPStatus.BAD_REQUEST, "application/json", json.dumps({"error": "model is required"}).encode("utf-8")

        prompt = str(body.get("prompt") or "")
        keep_alive = body.get("keep_alive")
        stream_opt = body.get("stream")
        evict = _is_zero_keep_alive(keep_alive)

        with self._lock:
            resolved = self._resolve_available_locked(model)
            if self._strict_models and resolved is None:
                return (
                    HTTPStatus.NOT_FOUND,
                    "application/json",
                    json.dumps({"error": f"model '{model}' not found"}).encode("utf-8"),
                )

            if evict:
                was_loaded = self._unload_locked(model)
                self.evictions.append({
                    "model": model,
                    "path": "/api/generate",
                    "keep_alive": keep_alive,
                    "was_loaded": was_loaded,
                })
                done_reason = "unload" if prompt == "" else "stop"
            else:
                if resolved is not None:
                    load_key, base = resolved
                else:
                    load_key = model
                    base = _default_model_record(model)
                    self._available[load_key] = dict(base)
                loaded = dict(base)
                loaded["expires_at"] = "2026-12-31T23:59:59Z"
                self._loaded[load_key] = loaded
                done_reason = "stop"

        reply_text = "" if prompt == "" else self._default_reply
        now = _iso_now()
        final_obj: dict[str, Any] = {
            "model": model,
            "created_at": now,
            "response": reply_text,
            "done": True,
            "done_reason": done_reason,
            "total_duration": 1_000_000,
            "load_duration": 100_000,
            "prompt_eval_count": 4 if prompt else 0,
            "eval_count": 8 if prompt else 0,
        }

        if stream_opt is False or (stream_opt is None and prompt == "" and evict):
            return HTTPStatus.OK, "application/json", json.dumps(final_obj).encode("utf-8")

        lines: list[bytes] = []
        if prompt:
            chunk = {
                "model": model,
                "created_at": now,
                "response": reply_text,
                "done": False,
            }
            lines.append((json.dumps(chunk) + "\n").encode("utf-8"))
        done_obj = dict(final_obj)
        done_obj["response"] = ""
        lines.append((json.dumps(done_obj) + "\n").encode("utf-8"))
        return HTTPStatus.OK, "application/x-ndjson", b"".join(lines)

    def handle_chat_completions(self, body: dict[str, Any]) -> tuple[int, str, bytes]:
        model = str(body.get("model") or "").strip() or "qwen2.5:3b"
        keep_alive = body.get("keep_alive")
        stream_opt = bool(body.get("stream", False))
        evict = _is_zero_keep_alive(keep_alive)

        with self._lock:
            resolved = self._resolve_available_locked(model)
            if self._strict_models and resolved is None:
                return (
                    HTTPStatus.NOT_FOUND,
                    "application/json",
                    json.dumps({"error": f"model '{model}' not found"}).encode("utf-8"),
                )
            if evict:
                was_loaded = self._unload_locked(model)
                self.evictions.append({
                    "model": model,
                    "path": "/v1/chat/completions",
                    "keep_alive": keep_alive,
                    "was_loaded": was_loaded,
                })
            else:
                if resolved is not None:
                    load_key, base = resolved
                else:
                    load_key = model
                    base = _default_model_record(model)
                    self._available[load_key] = dict(base)
                self._loaded[load_key] = dict(base)

        reply = self._default_reply
        created = int(time.time())
        if stream_opt:
            chunk = {
                "id": "chatcmpl-fake",
                "object": "chat.completion.chunk",
                "created": created,
                "model": model,
                "choices": [{"index": 0, "delta": {"role": "assistant", "content": reply}, "finish_reason": None}],
            }
            end_chunk = {
                "id": "chatcmpl-fake",
                "object": "chat.completion.chunk",
                "created": created,
                "model": model,
                "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
            }
            body_bytes = (
                f"data: {json.dumps(chunk)}\n\n"
                f"data: {json.dumps(end_chunk)}\n\n"
                "data: [DONE]\n\n"
            ).encode()
            return HTTPStatus.OK, "text/event-stream", body_bytes

        payload = {
            "id": "chatcmpl-fake",
            "object": "chat.completion",
            "created": created,
            "model": model,
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": reply},
                    "finish_reason": "stop",
                }
            ],
        }
        return HTTPStatus.OK, "application/json", json.dumps(payload).encode("utf-8")
