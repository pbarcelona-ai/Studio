"""GPU memory lease arbitrator between local LLMs (Ollama) and media runners (ComfyUI, sd-cli, audio).

- On ``mac_8g_lite`` (8 GB Apple Silicon): strictly evicts loaded Ollama models (``keep_alive: 0``)
  before running media runners, and frees ComfyUI when switching back to LLM if active.
- On ``full_48g`` (48 GB RTX 5090): keeps Ollama resident alongside media runners while
  ``active_llm_gb + media_vram_gb <= 42.0``, evicting Ollama only when the sum exceeds 42.0 GB.
- Calls ComfyUI ``POST /free`` (``{"unload_models": True, "free_memory": True}``) when explicitly
  requested or when ``model_key`` changes between media runs.
"""
from __future__ import annotations

import json
import os
import threading
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from typing import Any

from studio_app import gpus

DEFAULT_48G_THRESHOLD_GB: float = 42.0
DEFAULT_TIMEOUT_S: float = 5.0
DEFAULT_OLLAMA_URL: str = "http://127.0.0.1:11434"
DEFAULT_COMFYUI_URL: str = "http://127.0.0.1:8188"

_HTTP_ERRORS = (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, OSError, ValueError, TypeError)


def _origin(url: str) -> str:
    raw = url.strip()
    if not raw:
        return ""
    if "://" not in raw:
        if raw.startswith(("/", "\\")) or any(ch.isspace() for ch in raw):
            raise ValueError(f"unsupported URL {url!r}: expected http:// or https://")
        authority = raw.split("/", 1)[0].split("?", 1)[0].split("#", 1)[0]
        if authority.startswith("["):
            end_bracket = authority.find("]")
            if end_bracket <= 1:
                raise ValueError(f"unsupported URL {url!r}: expected http:// or https://")
            tail = authority[end_bracket + 1:]
            if tail and (not tail.startswith(":") or not tail[1:].isdigit()):
                raise ValueError(f"unsupported URL {url!r}: expected http:// or https://")
        elif ":" in authority:
            host_part, port_part = authority.split(":", 1)
            if not host_part or not port_part.isdigit():
                raise ValueError(f"unsupported URL {url!r}: expected http:// or https://")
        raw = f"http://{raw}"
    parts = urllib.parse.urlsplit(raw)
    try:
        _ = parts.port
    except ValueError as exc:
        raise ValueError(f"unsupported URL {url!r}: invalid port") from exc
    if parts.scheme not in ("http", "https") or not parts.netloc or not parts.hostname:
        raise ValueError(f"unsupported URL {url!r}: expected http:// or https://")
    return f"{parts.scheme}://{parts.netloc}"


def resolve_ollama_url(explicit: str | None = None) -> str:
    """Resolve the Ollama root origin (http://host:port) for /api/ps and /api/generate."""
    for candidate in (
        explicit,
        os.environ.get("OLLAMA_URL"),
        os.environ.get("OLLAMA_HOST"),
        os.environ.get("LOCAL_LLM_URL"),
    ):
        if candidate and candidate.strip():
            return _origin(candidate)
    return DEFAULT_OLLAMA_URL


def resolve_comfyui_url(explicit: str | None = None) -> str:
    """Resolve the ComfyUI base URL for POST /free."""
    for candidate in (
        explicit,
        os.environ.get("COMFYUI_URL"),
        os.environ.get("COMFY_BASE_URL"),
    ):
        if candidate and candidate.strip():
            return _origin(candidate)
    return DEFAULT_COMFYUI_URL


@dataclass
class LeaseResult:
    """Outcome of acquiring a GPU memory lease; supports use as a context manager."""

    owner: str
    tier: str
    evicted_ollama: bool = False
    evicted_models: list[str] = field(default_factory=list)
    comfyui_freed: bool = False
    active_llm_gb: float = 0.0
    media_vram_gb: float = 0.0
    threshold_gb: float | None = None
    warnings: list[str] = field(default_factory=list)
    _manager: LeaseManager | None = field(default=None, repr=False, compare=False)
    _comfyui_url: str | None = field(default=None, repr=False, compare=False)
    _model_key: str | None = field(default=None, repr=False, compare=False)
    _released: bool = field(default=False, repr=False, compare=False)
    _entered: bool = field(default=False, repr=False, compare=False)

    def __enter__(self) -> LeaseResult:
        if self._manager is not None:
            self._manager._enter_lease(self)
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self.release()

    def release(self, free_comfyui: bool = False) -> None:
        """Release the active lease; optionally unload ComfyUI models."""
        if self._released:
            return
        self._released = True
        if self._manager is not None:
            warnings = self._manager._release_lease(
                self,
                free_comfyui=free_comfyui,
                comfyui_url=self._comfyui_url,
            )
            self.warnings.extend(warnings)

    def to_dict(self) -> dict[str, Any]:
        """JSON-safe summary dictionary."""
        return {
            "owner": self.owner,
            "tier": self.tier,
            "evicted_ollama": self.evicted_ollama,
            "evicted_models": list(self.evicted_models),
            "comfyui_freed": self.comfyui_freed,
            "active_llm_gb": self.active_llm_gb,
            "media_vram_gb": self.media_vram_gb,
            "threshold_gb": self.threshold_gb,
            "warnings": list(self.warnings),
        }


class LeaseManager:
    """Thread-safe GPU memory lease coordinator using a re-entrant lock."""

    def __init__(
        self,
        comfyui_url: str | None = None,
        ollama_url: str | None = None,
        timeout: float | None = None,
        threshold_48g_gb: float = DEFAULT_48G_THRESHOLD_GB,
    ) -> None:
        self._lock = threading.RLock()
        self._cond = threading.Condition(self._lock)
        self.comfyui_url = comfyui_url
        self.ollama_url = ollama_url
        self.timeout = float(timeout) if timeout is not None else DEFAULT_TIMEOUT_S
        self.threshold_48g_gb = float(threshold_48g_gb)
        self._active_model_key: str | None = None
        self._active_owner: str | None = None
        self._comfyui_dirty: bool = False
        self._cm_depth: int = 0
        self._cm_thread: int | None = None

    def _wait_for_cm_slot(self) -> None:
        ident = threading.get_ident()
        while self._cm_depth > 0 and self._cm_thread != ident:
            self._cond.wait()

    def _enter_lease(self, lease: LeaseResult) -> None:
        ident = threading.get_ident()
        with self._cond:
            while self._cm_depth > 0 and self._cm_thread != ident:
                self._cond.wait()
            self._cm_depth += 1
            self._cm_thread = ident
            lease._entered = True
            if lease.owner == "media":
                if lease._model_key is not None and self._active_model_key != lease._model_key:
                    if self._active_model_key is not None:
                        freed, free_warn = self.free_comfyui(comfyui_url=lease._comfyui_url)
                        if free_warn:
                            lease.warnings.append(free_warn)
                        if freed:
                            lease.comfyui_freed = True
                    self._active_model_key = lease._model_key
                self._active_owner = "media"
                self._comfyui_dirty = True

    def _release_lease(
        self,
        lease: LeaseResult,
        *,
        free_comfyui: bool = False,
        comfyui_url: str | None = None,
    ) -> list[str]:
        with self._cond:
            if lease._entered:
                lease._entered = False
                if self._cm_depth > 0:
                    self._cm_depth -= 1
                if self._cm_depth == 0:
                    self._cm_thread = None
                    self._cond.notify_all()
            if lease.owner == "media":
                return self.release_media_lease(
                    free_comfyui=free_comfyui,
                    comfyui_url=comfyui_url,
                )
            return []

    def _http_json(
        self,
        method: str,
        url: str,
        payload: dict[str, Any] | None = None,
    ) -> tuple[int, Any]:
        if not url.startswith(("http://", "https://")):
            raise ValueError(f"unsupported URL scheme: {url!r}")
        data = json.dumps(payload).encode("utf-8") if payload is not None else None
        headers = {"Accept": "application/json"}
        if data is not None:
            headers["Content-Type"] = "application/json"
        req = urllib.request.Request(url, data=data, headers=headers, method=method)
        with urllib.request.urlopen(req, timeout=self.timeout) as resp:
            raw = resp.read()
            status = int(getattr(resp, "status", 200) or 200)
        if not raw:
            return status, {}
        return status, json.loads(raw.decode("utf-8"))

    def ollama_ps(self, ollama_url: str | None = None) -> tuple[list[str], float, str | None]:
        """Return (loaded_model_names, total_vram_gb, warning_or_none) from Ollama GET /api/ps."""
        try:
            origin = resolve_ollama_url(ollama_url or self.ollama_url)
            _, data = self._http_json("GET", f"{origin}/api/ps")
        except _HTTP_ERRORS as exc:
            return [], 0.0, f"Ollama /api/ps failed: {exc}"
        if not isinstance(data, dict):
            return [], 0.0, "Ollama /api/ps returned non-object JSON"
        models_raw = data.get("models")
        if not isinstance(models_raw, list):
            return [], 0.0, None
        names: list[str] = []
        seen: set[str] = set()
        total_bytes = 0.0
        for item in models_raw:
            if not isinstance(item, dict):
                continue
            name = str(item.get("model") or item.get("name") or "").strip()
            if name and name not in seen:
                seen.add(name)
                names.append(name)
            size_val = item.get("size_vram")
            if size_val is None:
                size_val = item.get("size")
            if size_val is not None:
                try:
                    total_bytes += max(0.0, float(size_val))
                except (TypeError, ValueError):
                    pass
        return names, round(total_bytes / (2**30), 3), None

    def evict_ollama(
        self,
        models: list[str],
        ollama_url: str | None = None,
    ) -> tuple[list[str], list[str]]:
        """Unload each model from Ollama via POST /api/generate with keep_alive: 0."""
        evicted: list[str] = []
        warnings: list[str] = []
        try:
            origin = resolve_ollama_url(ollama_url or self.ollama_url)
        except ValueError as exc:
            return evicted, [f"Ollama eviction skipped: {exc}"]
        for model in models:
            name = model.strip()
            if not name:
                continue
            try:
                self._http_json(
                    "POST",
                    f"{origin}/api/generate",
                    {"model": name, "keep_alive": 0},
                )
                evicted.append(name)
            except _HTTP_ERRORS as exc:
                warnings.append(f"Ollama eviction for {name!r} failed: {exc}")
        return evicted, warnings

    def free_comfyui(self, comfyui_url: str | None = None) -> tuple[bool, str | None]:
        """Request ComfyUI to unload models and free VRAM via POST /free."""
        try:
            origin = resolve_comfyui_url(comfyui_url or self.comfyui_url)
            self._http_json(
                "POST",
                f"{origin}/free",
                {"unload_models": True, "free_memory": True},
            )
            return True, None
        except _HTTP_ERRORS as exc:
            return False, f"ComfyUI /free failed: {exc}"

    def acquire_media_lease(
        self,
        media_vram_gb: float,
        active_llm_gb: float | None = None,
        comfyui_url: str | None = None,
        ollama_url: str | None = None,
        *,
        model_key: str | None = None,
        free_comfyui: bool = False,
        profile: dict[str, Any] | None = None,
        ollama_model: str | None = None,
    ) -> LeaseResult:
        """Acquire GPU memory for a media runner, evicting Ollama / freeing ComfyUI as required."""
        with self._cond:
            self._wait_for_cm_slot()
            hw = profile if profile is not None else gpus.gpu_profile()
            tier = str(hw.get("tier") or "cpu")
            vram_gb = float(hw.get("vram_gb") or 0.0)
            ram_gb = float(hw.get("ram_gb") or 0.0)
            media_gb = max(0.0, float(media_vram_gb))
            warnings: list[str] = []

            loaded_models, ps_gb, ps_warn = self.ollama_ps(ollama_url=ollama_url)
            if ps_warn:
                warnings.append(ps_warn)
            effective_llm_gb = max(0.0, float(active_llm_gb)) if active_llm_gb is not None else ps_gb

            models_to_evict = list(loaded_models)
            if not models_to_evict and ollama_model and ollama_model.strip():
                models_to_evict = [ollama_model.strip()]

            threshold_gb: float | None = None
            should_evict = False
            if tier == "mac_8g_lite":
                threshold_gb = 0.0
                should_evict = bool(models_to_evict)
            elif tier == "full_48g":
                threshold_gb = self.threshold_48g_gb
                should_evict = (effective_llm_gb + media_gb) > threshold_gb
            elif tier == "low_vram" or (tier == "cpu" and ram_gb < 16.0):
                threshold_gb = 0.0
                should_evict = bool(models_to_evict)
            else:
                capacity = vram_gb if vram_gb > 0.0 else ram_gb
                threshold_gb = max(0.0, capacity - 4.0) if capacity > 0.0 else 0.0
                should_evict = (effective_llm_gb + media_gb) > threshold_gb

            evicted_models: list[str] = []
            if should_evict and models_to_evict:
                evicted_models, evict_warns = self.evict_ollama(models_to_evict, ollama_url=ollama_url)
                warnings.extend(evict_warns)

            key_changed = (
                model_key is not None
                and self._active_model_key is not None
                and model_key != self._active_model_key
            )
            comfy_freed = False
            if free_comfyui or key_changed:
                comfy_freed, free_warn = self.free_comfyui(comfyui_url=comfyui_url)
                if free_warn:
                    warnings.append(free_warn)
                if comfy_freed:
                    self._comfyui_dirty = False
            if model_key is not None:
                self._active_model_key = model_key
            self._active_owner = "media"
            self._comfyui_dirty = True

            return LeaseResult(
                owner="media",
                tier=tier,
                evicted_ollama=bool(evicted_models),
                evicted_models=evicted_models,
                comfyui_freed=comfy_freed,
                active_llm_gb=effective_llm_gb,
                media_vram_gb=media_gb,
                threshold_gb=threshold_gb,
                warnings=warnings,
                _manager=self,
                _comfyui_url=comfyui_url,
                _model_key=model_key,
            )

    def acquire_llm_lease(
        self,
        comfyui_url: str | None = None,
        *,
        free_comfyui: bool | None = None,
        profile: dict[str, Any] | None = None,
    ) -> LeaseResult:
        """Acquire GPU memory for an LLM run, freeing ComfyUI if requested or active on mac_8g_lite."""
        with self._cond:
            self._wait_for_cm_slot()
            hw = profile if profile is not None else gpus.gpu_profile()
            tier = str(hw.get("tier") or "cpu")
            warnings: list[str] = []
            should_free = (
                bool(free_comfyui)
                if free_comfyui is not None
                else (tier == "mac_8g_lite" and (self._active_owner == "media" or self._comfyui_dirty))
            )
            comfy_freed = False
            if should_free:
                comfy_freed, free_warn = self.free_comfyui(comfyui_url=comfyui_url)
                if free_warn:
                    warnings.append(free_warn)
                if comfy_freed:
                    self._active_model_key = None
                    self._comfyui_dirty = False
            self._active_owner = "llm"
            return LeaseResult(
                owner="llm",
                tier=tier,
                comfyui_freed=comfy_freed,
                warnings=warnings,
                _manager=self,
                _comfyui_url=comfyui_url,
            )

    def release_media_lease(
        self,
        free_comfyui: bool = False,
        comfyui_url: str | None = None,
    ) -> list[str]:
        """Clear active media ownership and optionally free ComfyUI."""
        with self._cond:
            warnings: list[str] = []
            if self._active_owner == "media" and self._cm_depth == 0:
                self._active_owner = None
            if free_comfyui:
                freed, free_warn = self.free_comfyui(comfyui_url=comfyui_url)
                if free_warn:
                    warnings.append(free_warn)
                if freed:
                    self._active_model_key = None
                    self._comfyui_dirty = False
            return warnings


_DEFAULT_MANAGER_LOCK = threading.Lock()
_DEFAULT_MANAGER: LeaseManager | None = None


def get_default_manager() -> LeaseManager:
    """Return the process-wide default LeaseManager singleton."""
    global _DEFAULT_MANAGER
    with _DEFAULT_MANAGER_LOCK:
        if _DEFAULT_MANAGER is None:
            _DEFAULT_MANAGER = LeaseManager()
        return _DEFAULT_MANAGER


def acquire_media_lease(
    media_vram_gb: float,
    active_llm_gb: float | None = None,
    comfyui_url: str | None = None,
    ollama_url: str | None = None,
    *,
    model_key: str | None = None,
    free_comfyui: bool = False,
    profile: dict[str, Any] | None = None,
    ollama_model: str | None = None,
) -> LeaseResult:
    """Delegate media lease acquisition to the default LeaseManager."""
    return get_default_manager().acquire_media_lease(
        media_vram_gb=media_vram_gb,
        active_llm_gb=active_llm_gb,
        comfyui_url=comfyui_url,
        ollama_url=ollama_url,
        model_key=model_key,
        free_comfyui=free_comfyui,
        profile=profile,
        ollama_model=ollama_model,
    )


def acquire_llm_lease(
    comfyui_url: str | None = None,
    *,
    free_comfyui: bool | None = None,
    profile: dict[str, Any] | None = None,
) -> LeaseResult:
    """Delegate LLM lease acquisition to the default LeaseManager."""
    return get_default_manager().acquire_llm_lease(
        comfyui_url=comfyui_url,
        free_comfyui=free_comfyui,
        profile=profile,
    )
