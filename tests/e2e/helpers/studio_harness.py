"""Isolated workspace and live StudioServer HTTP/SSE test harness for E2E tests."""
from __future__ import annotations

from dataclasses import dataclass
import http.client
import importlib
import json
import logging
import logging.handlers
import os
from pathlib import Path
import shutil
import sys
import tempfile
import threading
from typing import Any

_SCRIPTS_DIR = Path(__file__).resolve().parents[3] / "scripts"
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

_KEEP_ATTRS = frozenset({"WEB", "CATALOG_FILE", "SCHEMA", "CREW_DIR", "RECIPES_DIR"})

_PRELOAD_MODULES = (
    "layout",
    "bookkit",
    "character_tokens",
    "prompts",
    "crew",
    "setup_check",
    "run_local_model",
    "studio_app.config",
    "studio_app.log",
    "studio_app.session",
    "studio_app.jobs",
    "studio_app.gpus",
    "studio_app.llm",
    "studio_app.overview",
    "studio_app.projects",
    "studio_app.kaggle_cleanup",
    "studio_app.kaggle_runs",
    "studio_app.gallery",
    "studio_app.cleanup",
    "studio_app.generation",
    "studio_app.media",
    "studio_app.direction",
    "studio_app.planner",
    "studio_app.scenes",
    "studio_app.steps",
    "studio_app.takes",
    "studio_app.single_prompts",
    "studio_app.common",
    "studio_app.routes_get",
    "studio_app.routes_post",
    "studio_app.handler",
    "studio_app.server",
)

_ENV_KEYS = (
    "HOME",
    "HF_HOME",
    "HF_HUB_CACHE",
    "HF_HUB_OFFLINE",
    "XDG_CACHE_HOME",
    "TORCH_HOME",
    "STUDIO_JOB_DIR",
    "STUDIO_NO_BUSY_CHECK",
    "STUDIO_DATA_DIR",
    "DATA_DIR",
    "STUDIO_GEN_DIR",
    "STUDIO_GPU_ENVS",
    "STUDIO_CACHE",
    "STUDIO_ADULT_MODELS",
    "OLLAMA_HOST",
    "OLLAMA_URL",
    "COMFYUI_URL",
    "COMFY_BASE_URL",
    "LOCAL_LLM_URL",
    "STUDIO_LEGACY_CLOUD",
    "STUDIO_LOCAL_LLM",
    "HF_TOKEN",
)


@dataclass
class HttpResponse:
    """HTTP response returned by StudioHarness requests."""

    status: int
    headers: dict[str, str]
    body: bytes

    @property
    def text(self) -> str:
        return self.body.decode("utf-8", errors="replace")

    def header(self, name: str, default: str = "") -> str:
        target = name.lower()
        for k, v in self.headers.items():
            if k.lower() == target:
                return v
        return default

    def json(self) -> Any:
        return json.loads(self.body.decode("utf-8"))


@dataclass
class SSEEvent:
    """Single Server-Sent Event parsed from /api/v1/events."""

    id: str | None
    event: str
    data: str
    retry: int | None = None

    def json(self) -> Any:
        return json.loads(self.data)


class IsolatedWorkspace:
    """Redirects Neon's import-time Path globals, env vars, loggers, and caches into a temp directory."""

    def __init__(self, base_dir: Path | None = None, *, local_llm_url: str | None = None) -> None:
        self._owns_dir = base_dir is None
        self.base_dir = Path(tempfile.mkdtemp(prefix="neon-e2e-")) if base_dir is None else base_dir
        self.root = self.base_dir / "studio"
        self.home = self.base_dir / "home"
        self.data_dir = self.base_dir / "data"
        self.hf_home = self.base_dir / "hf_home"
        self.hf_hub_cache = self.hf_home / "hub"
        self.xdg_cache_dir = self.base_dir / "xdg_cache"
        self.torch_home = self.base_dir / "torch_home"
        self.job_dir = self.base_dir / "jobs"
        self.gen_dir = self.base_dir / "gen"
        self.gpu_envs_dir = self.base_dir / "gpu_envs"
        self.cache_dir = self.base_dir / "cache"
        self._local_llm_url = local_llm_url

        self._saved_env: dict[str, str | None] = {}
        self._saved_attrs: list[tuple[Any, str, Any]] = []
        self._saved_home_fn: Any = None
        self._saved_session: tuple[str, int | None] | None = None
        self._saved_job: dict[str, Any] | None = None
        self._saved_studio_handlers: list[logging.Handler] = []
        self._attached_studio_handlers: list[logging.Handler] = []
        self._saved_log_configured: bool | None = None
        self._saved_gpu_lease_mgr: tuple[bool, Any] = (False, None)
        self._real_root: Path | None = None
        self._real_home: Path | None = None
        self._entered = False

    def _map_path_to_isolated(self, val: Path, real_root: Path, real_home: Path) -> Path | None:
        try:
            rel = val.relative_to(real_root)
            return self.root / rel
        except ValueError:
            pass
        try:
            rel_home = val.relative_to(real_home)
            return self.home / rel_home
        except ValueError:
            return None

    def _reroot_env_path(self, env_path: str, real_root: Path, real_home: Path) -> str:
        root_str = str(real_root)
        home_str = str(real_home)
        iso_root_str = str(self.root)
        iso_home_str = str(self.home)
        parts: list[str] = []
        for seg in env_path.split(os.pathsep):
            if seg == root_str or seg.startswith(root_str + os.sep):
                parts.append(iso_root_str + seg[len(root_str):])
            elif seg == home_str or seg.startswith(home_str + os.sep):
                parts.append(iso_home_str + seg[len(home_str):])
            else:
                parts.append(seg)
        return os.pathsep.join(parts)

    def _unroot_env_path(self, env_path: str, real_root: Path, real_home: Path) -> str:
        root_str = str(real_root)
        home_str = str(real_home)
        iso_roots = (str(self.root), str(self.root.resolve()))
        iso_homes = (str(self.home), str(self.home.resolve()))
        parts: list[str] = []
        for seg in env_path.split(os.pathsep):
            replaced = False
            for iso_r in iso_roots:
                if seg == iso_r or seg.startswith(iso_r + os.sep):
                    parts.append(root_str + seg[len(iso_r):])
                    replaced = True
                    break
            if replaced:
                continue
            for iso_h in iso_homes:
                if seg == iso_h or seg.startswith(iso_h + os.sep):
                    parts.append(home_str + seg[len(iso_h):])
                    replaced = True
                    break
            if not replaced:
                parts.append(seg)
        return os.pathsep.join(parts)

    @staticmethod
    def _is_scripts_module(mod: Any, scripts_resolved: Path) -> bool:
        mod_file = getattr(mod, "__file__", None)
        if not mod_file or not isinstance(mod_file, str):
            return False
        try:
            mod_path = Path(mod_file).resolve()
        except OSError:
            return False
        return scripts_resolved == mod_path or scripts_resolved in mod_path.parents

    def _isolate_studio_logger(self, studio_log: Any) -> None:
        studio_logger = logging.getLogger("studio")
        self._saved_studio_handlers = list(studio_logger.handlers)
        self._saved_log_configured = bool(getattr(studio_log, "_configured", False))

        root_resolved = self.root.resolve()
        target_log_file = (self.root / "studio.log").resolve()
        has_target_file_handler = False

        for handler in list(studio_logger.handlers):
            if isinstance(handler, logging.FileHandler):
                try:
                    h_path = Path(handler.baseFilename).resolve()
                except OSError:
                    h_path = Path(handler.baseFilename)
                if h_path == target_log_file:
                    has_target_file_handler = True
                    continue
                if root_resolved not in h_path.parents and h_path != root_resolved:
                    try:
                        handler.flush()
                    except OSError:
                        pass
                    handler.close()
                    studio_logger.removeHandler(handler)

        fmt = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
        studio_logger.setLevel(logging.INFO)
        if not has_target_file_handler:
            fh = logging.handlers.RotatingFileHandler(
                self.root / "studio.log",
                maxBytes=1_000_000,
                backupCount=2,
                encoding="utf-8",
            )
            fh.setFormatter(fmt)
            studio_logger.addHandler(fh)
            self._attached_studio_handlers.append(fh)

        if not any(
            isinstance(h, logging.StreamHandler) and not isinstance(h, logging.FileHandler)
            for h in studio_logger.handlers
        ):
            sh = logging.StreamHandler()
            sh.setLevel(logging.WARNING)
            sh.setFormatter(fmt)
            studio_logger.addHandler(sh)
            self._attached_studio_handlers.append(sh)

        studio_log._configured = True

    def __enter__(self) -> IsolatedWorkspace:
        if self._entered:
            return self
        self._entered = True

        for d in (
            self.root / "projects" / "books",
            self.root / "projects" / "characters",
            self.root / "projects" / "prompts",
            self.root / "projects" / "regression",
            self.root / "books",
            self.root / "logs",
            self.root / "my_downloads",
            self.home,
            self.data_dir,
            self.hf_home,
            self.hf_hub_cache,
            self.xdg_cache_dir,
            self.torch_home,
            self.job_dir,
            self.gen_dir,
            self.gpu_envs_dir,
            self.cache_dir,
        ):
            d.mkdir(parents=True, exist_ok=True)

        real_home = Path.home()
        self._real_home = real_home
        for k in _ENV_KEYS:
            self._saved_env[k] = os.environ.get(k)

        os.environ["HOME"] = str(self.home)
        os.environ["HF_HOME"] = str(self.hf_home)
        os.environ["HF_HUB_CACHE"] = str(self.hf_hub_cache)
        os.environ["XDG_CACHE_HOME"] = str(self.xdg_cache_dir)
        os.environ["TORCH_HOME"] = str(self.torch_home)
        os.environ["STUDIO_JOB_DIR"] = str(self.job_dir)
        os.environ["STUDIO_NO_BUSY_CHECK"] = "1"
        os.environ["STUDIO_DATA_DIR"] = str(self.data_dir)
        os.environ["DATA_DIR"] = str(self.data_dir)
        os.environ["STUDIO_GEN_DIR"] = str(self.gen_dir)
        os.environ["STUDIO_GPU_ENVS"] = str(self.gpu_envs_dir)
        os.environ["STUDIO_CACHE"] = str(self.cache_dir)
        if self._local_llm_url:
            os.environ["LOCAL_LLM_URL"] = self._local_llm_url

        # Import config and log first and re-root studio.log BEFORE loading jobs/session/etc.
        config: Any = importlib.import_module("studio_app.config")
        studio_log: Any = importlib.import_module("studio_app.log")
        real_root = config.ROOT
        self._real_root = real_root

        self._saved_attrs.append((studio_log, "LOG_FILE", studio_log.LOG_FILE))
        studio_log.LOG_FILE = self.root / "studio.log"
        self._isolate_studio_logger(studio_log)

        for mod_name in _PRELOAD_MODULES:
            try:
                importlib.import_module(mod_name)
            except ImportError:
                continue

        gpus: Any = importlib.import_module("studio_app.gpus")
        jobs: Any = importlib.import_module("studio_app.jobs")
        llm: Any = importlib.import_module("studio_app.llm")
        session: Any = importlib.import_module("studio_app.session")

        scripts_resolved = _SCRIPTS_DIR.resolve()
        for mod in list(sys.modules.values()):
            if not self._is_scripts_module(mod, scripts_resolved):
                continue
            for attr, val in list(vars(mod).items()):
                if attr in _KEEP_ATTRS:
                    continue
                if attr == "ENV_PATH" and isinstance(val, str):
                    new_env_path = self._reroot_env_path(val, real_root, real_home)
                    if new_env_path != val:
                        self._saved_attrs.append((mod, attr, val))
                        setattr(mod, attr, new_env_path)
                    continue
                if not isinstance(val, Path):
                    continue
                target = self._map_path_to_isolated(val, real_root, real_home)
                if target is not None:
                    self._saved_attrs.append((mod, attr, val))
                    setattr(mod, attr, target)

        self._saved_home_fn = Path.__dict__.get("home")
        isolated_home = self.home
        type.__setattr__(Path, "home", classmethod(lambda cls: isolated_home))

        if self._local_llm_url:
            bookkit: Any = importlib.import_module("bookkit")
            self._saved_attrs.append((bookkit, "LOCAL_LLM_URL", bookkit.LOCAL_LLM_URL))
            self._saved_attrs.append((llm, "LOCAL_LLM_URL", llm.LOCAL_LLM_URL))
            bookkit.LOCAL_LLM_URL = self._local_llm_url
            llm.LOCAL_LLM_URL = self._local_llm_url

        real_gpus = gpus.all_gpus()
        self._saved_attrs.append((gpus, "_ALL_GPUS", gpus._ALL_GPUS))
        if not gpus.run_local_model.usable(real_gpus):
            gpus._ALL_GPUS = [
                {
                    "name": "Apple M2",
                    "vendor": "Apple",
                    "gb": 16.0,
                    "shared": True,
                    "cap": "MPS",
                    "nvidia_ready": False,
                    "rocm_ready": False,
                    "mps_ready": True,
                }
            ]
        else:
            gpus._ALL_GPUS = list(real_gpus)

        self._saved_attrs.append((llm, "_LOCAL_CACHE", dict(llm._LOCAL_CACHE)))
        llm._LOCAL_CACHE.update(at=0.0, value=None)

        gpu_lease_mod: Any = sys.modules.get("local_runners.gpu_lease")
        if gpu_lease_mod is not None and hasattr(gpu_lease_mod, "_DEFAULT_MANAGER"):
            self._saved_gpu_lease_mgr = (True, gpu_lease_mod._DEFAULT_MANAGER)
            gpu_lease_mod._DEFAULT_MANAGER = None

        self._saved_session = (session.SESSION.token, session.SESSION.port)

        with jobs.JOB.lock:
            self._saved_job = {
                "lines": list(jobs.JOB.lines),
                "running": jobs.JOB.running,
                "current": jobs.JOB.current,
                "state": dict(jobs.JOB.state),
                "queue": list(jobs.JOB.queue),
                "on_finish": jobs.JOB.on_finish,
            }
            jobs.JOB.lines.clear()
            jobs.JOB.running = False
            jobs.JOB.current = ""
            jobs.JOB.state = {}
            jobs.JOB.queue.clear()
            jobs.JOB.on_finish = None

        handler_mod: Any = sys.modules.get("studio_app.handler")
        if handler_mod is not None and hasattr(handler_mod, "clear_previews"):
            handler_mod.clear_previews()

        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self.close()

    def close(self) -> None:
        if not self._entered:
            return
        self._entered = False

        jobs: Any = importlib.import_module("studio_app.jobs")
        llm: Any = importlib.import_module("studio_app.llm")
        studio_log: Any = importlib.import_module("studio_app.log")
        session: Any = importlib.import_module("studio_app.session")

        if self._saved_job is not None:
            with jobs.JOB.lock:
                jobs.JOB.lines[:] = self._saved_job["lines"]
                jobs.JOB.running = self._saved_job["running"]
                jobs.JOB.current = self._saved_job["current"]
                jobs.JOB.state = self._saved_job["state"]
                jobs.JOB.queue[:] = self._saved_job["queue"]
                jobs.JOB.on_finish = self._saved_job["on_finish"]

        handler_mod: Any = sys.modules.get("studio_app.handler")
        if handler_mod is not None and hasattr(handler_mod, "clear_previews"):
            handler_mod.clear_previews()

        if self._saved_session is not None:
            session.SESSION.token, session.SESSION.port = self._saved_session

        gpu_lease_mod: Any = sys.modules.get("local_runners.gpu_lease")
        if gpu_lease_mod is not None and hasattr(gpu_lease_mod, "_DEFAULT_MANAGER"):
            had_saved, prev_mgr = self._saved_gpu_lease_mgr
            gpu_lease_mod._DEFAULT_MANAGER = prev_mgr if had_saved else None

        if self._saved_home_fn is not None:
            type.__setattr__(Path, "home", self._saved_home_fn)

        for mod, attr, orig in reversed(self._saved_attrs):
            if mod is llm and attr == "_LOCAL_CACHE":
                llm._LOCAL_CACHE.clear()
                llm._LOCAL_CACHE.update(orig)
            else:
                setattr(mod, attr, orig)
        self._saved_attrs.clear()

        # Restore any scripts/ module attributes imported dynamically inside the workspace
        if self._real_root is not None and self._real_home is not None:
            scripts_resolved = _SCRIPTS_DIR.resolve()
            iso_root_resolved = self.root.resolve()
            iso_home_resolved = self.home.resolve()
            for mod in list(sys.modules.values()):
                if not self._is_scripts_module(mod, scripts_resolved):
                    continue
                for attr, val in list(vars(mod).items()):
                    if attr in _KEEP_ATTRS:
                        continue
                    if attr == "ENV_PATH" and isinstance(val, str):
                        restored_env = self._unroot_env_path(val, self._real_root, self._real_home)
                        if restored_env != val:
                            setattr(mod, attr, restored_env)
                        continue
                    if not isinstance(val, Path):
                        continue
                    try:
                        rel_home = val.relative_to(self.home)
                        setattr(mod, attr, self._real_home / rel_home)
                        continue
                    except ValueError:
                        pass
                    try:
                        rel_home = val.resolve().relative_to(iso_home_resolved)
                        setattr(mod, attr, self._real_home / rel_home)
                        continue
                    except (OSError, ValueError):
                        pass
                    try:
                        rel_root = val.relative_to(self.root)
                        setattr(mod, attr, self._real_root / rel_root)
                        continue
                    except ValueError:
                        pass
                    try:
                        rel_root = val.resolve().relative_to(iso_root_resolved)
                        setattr(mod, attr, self._real_root / rel_root)
                    except (OSError, ValueError):
                        pass

        studio_logger = logging.getLogger("studio")
        root_resolved = self.root.resolve()
        for handler in list(studio_logger.handlers):
            remove_it = handler in self._attached_studio_handlers
            if not remove_it and isinstance(handler, logging.FileHandler):
                try:
                    h_path = Path(handler.baseFilename).resolve()
                    if h_path == root_resolved or root_resolved in h_path.parents:
                        remove_it = True
                except OSError:
                    pass
            if remove_it:
                try:
                    handler.flush()
                except OSError:
                    pass
                handler.close()
                studio_logger.removeHandler(handler)
        self._attached_studio_handlers.clear()
        extra_handlers = [h for h in studio_logger.handlers if h not in self._saved_studio_handlers]
        for h in list(studio_logger.handlers):
            studio_logger.removeHandler(h)
        for orig_handler in self._saved_studio_handlers:
            studio_logger.addHandler(orig_handler)
        for extra_handler in extra_handlers:
            studio_logger.addHandler(extra_handler)
        self._saved_studio_handlers.clear()
        if self._saved_log_configured is not None:
            studio_log._configured = self._saved_log_configured
            self._saved_log_configured = None

        for k, prev in self._saved_env.items():
            if prev is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = prev
        self._saved_env.clear()

        if self._owns_dir:
            shutil.rmtree(self.base_dir, ignore_errors=True)


class StudioHarness:
    """Live StudioServer wrapper bound to 127.0.0.1:0 with isolated workspace and HTTP/SSE client."""

    def __init__(self, workspace: IsolatedWorkspace | None = None) -> None:
        self._owns_workspace = workspace is None
        self.workspace = workspace or IsolatedWorkspace()
        self._server: Any = None
        self._thread: threading.Thread | None = None
        self.token: str = ""

    @property
    def port(self) -> int:
        if self._server is None:
            raise RuntimeError("StudioHarness has not been started")
        return int(self._server.server_port)

    @property
    def base_url(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    def start(self) -> StudioHarness:
        if self._owns_workspace:
            self.workspace.__enter__()
        server_mod = importlib.import_module("studio_app.server")
        session_mod = importlib.import_module("studio_app.session")
        make_server = server_mod.make_server
        session_obj = session_mod.SESSION

        self.token = session_obj.new_token()
        session_obj.token = self.token
        session_obj.port = None
        self._server = make_server([0])
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()
        return self

    def close(self) -> None:
        if self._server is not None:
            if self._thread is not None:
                self._server.shutdown()
            self._server.server_close()
            self._server = None
        if self._thread is not None:
            self._thread.join(timeout=3.0)
            self._thread = None
        if self._owns_workspace:
            self.workspace.close()

    def __enter__(self) -> StudioHarness:
        return self.start()

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self.close()

    def request(
        self,
        method: str,
        path: str,
        *,
        json_body: Any = None,
        raw_body: bytes | None = None,
        headers: dict[str, str] | None = None,
        auth: bool = True,
        host: str | None = None,
        origin: str | None = None,
        timeout: float = 10.0,
    ) -> HttpResponse:
        req_headers: dict[str, str] = {"Host": host or f"127.0.0.1:{self.port}"}
        if origin is not None:
            req_headers["Origin"] = origin
        if auth:
            req_headers["X-Studio-Token"] = self.token
        if headers:
            req_headers.update(headers)

        data: bytes | None = None
        if raw_body is not None:
            data = raw_body
        elif json_body is not None:
            data = json.dumps(json_body).encode("utf-8")
            if not any(k.lower() == "content-type" for k in req_headers):
                req_headers["Content-Type"] = "application/json"

        has_content_length = any(k.lower() == "content-length" for k in req_headers)
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=timeout)
        try:
            conn.putrequest(method, path, skip_host=True, skip_accept_encoding=True)
            for k, v in req_headers.items():
                conn.putheader(k, v)
            if data is not None and not has_content_length:
                conn.putheader("Content-Length", str(len(data)))
            conn.endheaders(data)
            resp = conn.getresponse()
            body = resp.read()
            resp_headers = dict(resp.getheaders())
            return HttpResponse(status=resp.status, headers=resp_headers, body=body)
        finally:
            conn.close()

    def get(
        self,
        path: str,
        *,
        headers: dict[str, str] | None = None,
        auth: bool = True,
        timeout: float = 10.0,
    ) -> HttpResponse:
        return self.request("GET", path, headers=headers, auth=auth, timeout=timeout)

    def post(
        self,
        path: str,
        json_body: Any = None,
        *,
        raw_body: bytes | None = None,
        headers: dict[str, str] | None = None,
        auth: bool = True,
        timeout: float = 10.0,
    ) -> HttpResponse:
        return self.request(
            "POST",
            path,
            json_body=json_body,
            raw_body=raw_body,
            headers=headers,
            auth=auth,
            timeout=timeout,
        )

    def read_sse_events(
        self,
        path: str = "/api/v1/events?seconds=0.8",
        *,
        auth: bool = True,
        headers: dict[str, str] | None = None,
        max_events: int | None = None,
        timeout: float = 5.0,
    ) -> list[SSEEvent]:
        req_headers: dict[str, str] = {"Host": f"127.0.0.1:{self.port}"}
        if auth:
            req_headers["X-Studio-Token"] = self.token
        if headers:
            req_headers.update(headers)

        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=timeout)
        events: list[SSEEvent] = []
        try:
            conn.putrequest("GET", path, skip_host=True, skip_accept_encoding=True)
            for k, v in req_headers.items():
                conn.putheader(k, v)
            conn.endheaders()
            resp = conn.getresponse()
            if resp.status != 200:
                body = resp.read()
                raise AssertionError(f"SSE endpoint returned {resp.status}: {body!r}")

            cur_id: str | None = None
            cur_event = "message"
            cur_data: list[str] = []
            cur_retry: int | None = None

            while True:
                raw_line = resp.readline()
                if not raw_line:
                    break
                line = raw_line.decode("utf-8", errors="replace").rstrip("\r\n")
                if line == "":
                    if cur_data or cur_retry is not None or cur_id is not None or cur_event != "message":
                        events.append(
                            SSEEvent(
                                id=cur_id,
                                event=cur_event,
                                data="\n".join(cur_data),
                                retry=cur_retry,
                            )
                        )
                        cur_id = None
                        cur_event = "message"
                        cur_data = []
                        cur_retry = None
                        if max_events is not None and len(events) >= max_events:
                            break
                    continue
                if line.startswith(":"):
                    continue
                if ":" in line:
                    field, value = line.split(":", 1)
                    if value.startswith(" "):
                        value = value[1:]
                else:
                    field, value = line, ""
                if field == "id":
                    cur_id = value
                elif field == "event":
                    cur_event = value
                elif field == "data":
                    cur_data.append(value)
                elif field == "retry":
                    try:
                        cur_retry = int(value)
                    except ValueError:
                        pass
            return events
        finally:
            conn.close()
