"""Hugging Face Model Pack Manager: token storage (0600), no-redirect HEAD license probing, 2 GB disk headroom guard, and Windows-safe lockfile downloads."""
from __future__ import annotations

from contextlib import contextmanager
from collections.abc import Iterator
import json
import os
from pathlib import Path
import re
import shutil
import stat
import threading
import time
import urllib.error
import urllib.request
from typing import Any

_TOKEN_RE = re.compile(r"^hf_[A-Za-z0-9_]{27,128}$")
_PROCESS_LOCK = threading.Lock()
MIN_HEADROOM_GB = 2.0


class _NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req: Any, fp: Any, code: int, msg: str, headers: Any, newurl: str) -> Any:
        return None


_NO_REDIRECT_OPENER = urllib.request.build_opener(_NoRedirectHandler())


def _hf_endpoint() -> str:
    return (os.environ.get("HF_ENDPOINT") or "https://huggingface.co").rstrip("/")


def _default_models_dir() -> Path:
    env_dir = os.environ.get("STUDIO_MODELS_DIR") or os.environ.get("FREEFIELD_MODELS_DIR")
    if env_dir:
        return Path(env_dir)
    return Path(__file__).resolve().parents[2] / "models"


def _studio_token_path() -> Path:
    data_dir = os.environ.get("STUDIO_DATA_DIR")
    if data_dir:
        return Path(data_dir) / "hf_token"
    hf_home = os.environ.get("HF_HOME")
    if hf_home:
        return Path(hf_home) / "studio_hf_token"
    return Path.home() / ".pistachios_studio" / "hf_token"


def looks_like_token(token: Any) -> bool:
    """True when token is an ASCII string matching `^hf_[A-Za-z0-9]{27,128}$` (length >= 30) with no leading/trailing spaces."""
    if not isinstance(token, str):
        return False
    return bool(_TOKEN_RE.fullmatch(token))


def env_problem() -> str | None:
    """Return a human-readable problem string when HF_TOKEN in the environment is a template placeholder or malformed."""
    raw = os.environ.get("HF_TOKEN")
    if not raw:
        return None
    stripped = raw.strip()
    if not stripped:
        return None
    if "{{" in stripped or "RUNPOD_SECRET" in stripped or not looks_like_token(stripped):
        return "HF_TOKEN environment variable is malformed or contains an unexpanded secret template"
    return None


def get_token() -> tuple[str, str]:
    """Return `(token, source)` where source is `'studio'`, `'env'`, or `''`. Studio-saved token takes precedence over HF_TOKEN."""
    tok_path = _studio_token_path()
    if tok_path.is_file():
        try:
            saved = tok_path.read_text(encoding="utf-8").strip()
            if looks_like_token(saved):
                return saved, "studio"
        except OSError:
            pass
    if env_problem() is None:
        env_tok = (os.environ.get("HF_TOKEN") or "").strip()
        if looks_like_token(env_tok):
            return env_tok, "env"
    return "", ""


def verify_token(token: str) -> dict[str, Any]:
    """Validate an HF token against `{HF_ENDPOINT}/api/whoami-v2`."""
    clean = str(token or "").strip()
    if not looks_like_token(clean):
        raise ValueError("Invalid Hugging Face token format (must start with 'hf_' and be at least 30 ASCII characters)")
    req = urllib.request.Request(
        f"{_hf_endpoint()}/api/whoami-v2",
        headers={"Authorization": f"Bearer {clean}"},
        method="GET",
    )
    try:
        with urllib.request.urlopen(req, timeout=5.0) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            user = str(data.get("name") or data.get("user") or "hf_user")
            return {"ok": True, "user": user}
    except urllib.error.HTTPError as exc:
        if exc.code in (401, 403):
            raise PermissionError("Hugging Face rejected this token (401 Unauthorized)") from exc
        raise RuntimeError(f"Hugging Face whoami error (HTTP {exc.code})") from exc
    except (urllib.error.URLError, OSError) as exc:
        raise ConnectionError(f"Could not reach Hugging Face Hub: {exc}") from exc


def save_token(token: str, *, verify: bool = False) -> Path:
    """Persist a validated HF token with strict 0600 permissions via atomic temp file replacement."""
    if not isinstance(token, str):
        raise ValueError("Token must be a string")
    clean = token.strip()
    if not looks_like_token(clean):
        raise ValueError("Invalid Hugging Face token format (must start with 'hf_' and be at least 30 ASCII characters)")
    if verify:
        verify_token(clean)
    dest = _studio_token_path()
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_name(f".{dest.name}.{os.getpid()}.{threading.get_ident()}.tmp")
    fd = os.open(str(tmp), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        os.write(fd, (clean + "\n").encode("utf-8"))
    finally:
        os.close(fd)
    try:
        os.chmod(tmp, stat.S_IRUSR | stat.S_IWUSR)
    except OSError:
        pass
    os.replace(tmp, dest)
    try:
        os.chmod(dest, stat.S_IRUSR | stat.S_IWUSR)
    except OSError:
        pass
    return dest


def forget_token() -> None:
    """Remove any studio-saved HF token file."""
    p = _studio_token_path()
    try:
        p.unlink(missing_ok=True)
    except OSError:
        pass


def probe_license(repo: str, file: str, token: str | None = None) -> str:
    """Probe a gated HF file via no-redirect HEAD request.
    Returns `'ok'` (200/302/307), `'token'` (401 or missing token), `'license'` (403), `'missing'` (404), or `'unknown'` (network/5xx).
    """
    tok = token if token is not None else get_token()[0]
    url = f"{_hf_endpoint()}/{repo}/resolve/main/{file}"
    headers: dict[str, str] = {}
    if tok:
        headers["Authorization"] = f"Bearer {tok}"
    req = urllib.request.Request(url, headers=headers, method="HEAD")
    try:
        resp = _NO_REDIRECT_OPENER.open(req, timeout=4.0)
        code = getattr(resp, "status", 200)
        resp.close()
        if code in (200, 301, 302, 303, 307, 308):
            return "ok"
        return "unknown"
    except urllib.error.HTTPError as exc:
        if exc.code in (301, 302, 303, 307, 308, 200):
            return "ok"
        if exc.code == 401:
            return "token"
        if exc.code == 403:
            return "license" if tok else "token"
        if exc.code == 404:
            return "missing"
        return "unknown"
    except (urllib.error.URLError, OSError, TimeoutError):
        return "unknown"


@contextmanager
def _download_lock(models_dir: Path, timeout: float = 30.0) -> Iterator[Path]:
    """Cross-platform process + thread lock using `.download.lock` inside `models_dir`."""
    models_dir.mkdir(parents=True, exist_ok=True)
    lock_path = models_dir / ".download.lock"
    token_path = models_dir / ".download.lock.active"
    deadline = time.monotonic() + timeout
    with _PROCESS_LOCK:
        while True:
            try:
                fd = os.open(str(token_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
                os.write(fd, f"{os.getpid()}\n".encode("ascii"))
                os.close(fd)
                break
            except FileExistsError:
                if time.monotonic() >= deadline:
                    raise TimeoutError(f"Timed out waiting for download lock {lock_path}") from None
                time.sleep(0.02)
        try:
            lock_path.write_text(f"{os.getpid()}\n", encoding="utf-8")
            yield lock_path
        finally:
            try:
                token_path.unlink(missing_ok=True)
            except OSError:
                pass


def _read_downloads_file(models_dir: Path) -> dict[str, Any]:
    dl_file = models_dir / ".downloads.json"
    if not dl_file.is_file():
        return {"job": None, "failed": {}}
    try:
        data = json.loads(dl_file.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return {"job": None, "failed": {}}
        return {
            "job": data.get("job"),
            "failed": dict(data.get("failed") or {}) if isinstance(data.get("failed"), dict) else {},
        }
    except Exception:
        return {"job": None, "failed": {}}


def _write_downloads_file(models_dir: Path, state: dict[str, Any]) -> None:
    models_dir.mkdir(parents=True, exist_ok=True)
    dl_file = models_dir / ".downloads.json"
    tmp = models_dir / f".downloads.json.{os.getpid()}.{threading.get_ident()}.tmp"
    tmp.write_text(json.dumps(state, indent=2), encoding="utf-8")
    os.replace(tmp, dl_file)


def downloads_status(models_dir: Path | str | None = None) -> dict[str, Any]:
    """Return current download status `{job, failed}`, pruning stale failure records whose files now exist on disk."""
    mdir = Path(models_dir) if models_dir is not None else _default_models_dir()
    state = _read_downloads_file(mdir)
    failed = dict(state.get("failed") or {})
    pruned = {rel: info for rel, info in failed.items() if not (mdir / rel).is_file()}
    if len(pruned) != len(failed) and mdir.is_dir():
        state["failed"] = pruned
        try:
            _write_downloads_file(mdir, state)
        except OSError:
            pass
    else:
        state["failed"] = pruned
    return state


def load_pack_catalog(packs_dir: Path | str | None = None) -> dict[str, dict[str, Any]]:
    """Load bundled `packs/*.json` manifests indexed by pack id."""
    pdir = Path(packs_dir) if packs_dir is not None else (Path(__file__).resolve().parents[2] / "packs")
    catalog: dict[str, dict[str, Any]] = {}
    if not pdir.is_dir():
        return catalog
    for f in sorted(pdir.glob("*.json")):
        if f.name == "index.json":
            continue
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            pid = str(data.get("pack") or f.stem)
            catalog[pid] = data
        except (OSError, ValueError, TypeError):
            continue
    return catalog


def _download_single_file(repo: str, file: str, dest: Path, *, token: str, gated: bool) -> None:
    url = f"{_hf_endpoint()}/{repo}/resolve/main/{file}"
    headers: dict[str, str] = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    def _fetch(hdrs: dict[str, str]) -> bytes:
        req = urllib.request.Request(url, headers=hdrs, method="GET")
        with urllib.request.urlopen(req, timeout=30.0) as resp:
            return resp.read()

    try:
        payload = _fetch(headers)
    except urllib.error.HTTPError as exc:
        if exc.code == 401 and token and not gated:
            # Stale token on a public model: retry anonymously
            payload = _fetch({})
        elif exc.code == 401:
            raise PermissionError(f"401 Unauthorized downloading {repo}/{file}: valid HF token required") from exc
        elif exc.code == 403:
            raise PermissionError(f"403 GatedRepo: accept the model license at huggingface.co/{repo}") from exc
        else:
            raise RuntimeError(f"HTTP {exc.code} downloading {repo}/{file}") from exc
    except (urllib.error.URLError, OSError) as exc:
        raise RuntimeError(f"Network failure downloading {repo}/{file}: {exc}") from exc

    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.parent / f".{dest.name}.{os.getpid()}.{threading.get_ident()}.tmp"
    tmp.write_bytes(payload)
    os.replace(tmp, dest)


def download_packs(
    packs: list[dict[str, Any] | str],
    *,
    models_dir: Path | str | None = None,
    packs_dir: Path | str | None = None,
) -> dict[str, Any]:
    """Download one or more model packs with a 2 GB disk headroom check and serialized `.download.lock`."""
    if not packs:
        raise ValueError("No model packs specified for download")

    mdir = Path(models_dir) if models_dir is not None else _default_models_dir()
    mdir.mkdir(parents=True, exist_ok=True)
    catalog = load_pack_catalog(packs_dir)

    resolved_packs: list[dict[str, Any]] = []
    for item in packs:
        if isinstance(item, str):
            if item not in catalog:
                raise KeyError(f"Unknown model pack {item!r}")
            resolved_packs.append(catalog[item])
        elif isinstance(item, dict):
            resolved_packs.append(item)
        else:
            raise ValueError(f"Invalid pack specification: {item!r}")

    # Calculate missing GB and check 2 GB disk headroom before acquiring lock or making network calls
    missing_models: list[dict[str, Any]] = []
    needed_gb = 0.0
    for p in resolved_packs:
        for m in p.get("models") or []:
            fname = str(m.get("name") or Path(str(m["file"])).name)
            dest = mdir / str(m["dir"]) / fname
            if not dest.is_file():
                missing_models.append(m)
                needed_gb += float(m.get("gb") or 0.0)

    free_gb = shutil.disk_usage(mdir).free / 1e9
    if needed_gb > 0 and (free_gb - needed_gb) < MIN_HEADROOM_GB:
        raise RuntimeError(
            f"Insufficient disk space: {free_gb:.1f} GB free, {needed_gb:.1f} GB needed "
            f"(requires at least {MIN_HEADROOM_GB:.1f} GB free disk headroom)"
        )

    token, _ = get_token()
    downloaded: list[str] = []

    with _download_lock(mdir):
        state = _read_downloads_file(mdir)
        failed = dict(state.get("failed") or {})
        # Prune already-present files
        failed = {rel: info for rel, info in failed.items() if not (mdir / rel).is_file()}

        for m in missing_models:
            repo = str(m["repo"])
            rfile = str(m["file"])
            mdir_sub = str(m["dir"])
            fname = str(m.get("name") or Path(rfile).name)
            rel_key = f"{mdir_sub}/{fname}"
            dest = mdir / mdir_sub / fname
            if dest.is_file():
                failed.pop(rel_key, None)
                continue

            gated = bool(m.get("gated"))
            if gated:
                probe = probe_license(repo, rfile, token=token)
                if probe == "token":
                    failed[rel_key] = {"reason": "token", "repo": repo, "at": int(time.time())}
                    continue
                if probe == "license":
                    failed[rel_key] = {"reason": "license", "repo": repo, "at": int(time.time())}
                    continue

            try:
                _download_single_file(repo, rfile, dest, token=token, gated=gated)
                failed.pop(rel_key, None)
                downloaded.append(rel_key)
            except Exception as exc:
                failed[rel_key] = {"reason": str(exc), "repo": repo, "at": int(time.time())}

        state["job"] = None
        state["failed"] = failed
        _write_downloads_file(mdir, state)

    return {"ok": len(state["failed"]) == 0, "downloaded": downloaded, "failed": state["failed"]}
