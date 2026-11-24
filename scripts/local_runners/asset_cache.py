"""Content-addressed deterministic media asset cache with 20 GB LRU eviction and Windows-safe lockfile."""
from __future__ import annotations

from contextlib import contextmanager
from collections.abc import Iterator
import hashlib
import json
import os
from pathlib import Path
import shutil
import threading
import time
from typing import Any

DEFAULT_MAX_BYTES = 20 * (1024**3)  # 20 GiB
_DEFAULT_CACHE: AssetCache | None = None
_GLOBAL_LOCK = threading.Lock()


def asset_cache_enabled() -> bool:
    """Check whether asset caching is enabled via STUDIO_ASSET_CACHE or OPENMONTAGE_ASSET_CACHE."""
    for var in ("STUDIO_ASSET_CACHE", "OPENMONTAGE_ASSET_CACHE", "NEON_ASSET_CACHE"):
        raw = os.environ.get(var)
        if raw is not None:
            return raw.strip().lower() in ("1", "true", "yes", "on")
    return False


def default_max_total_bytes() -> int:
    """Return configured max cache capacity in bytes, falling back to 20 GiB on missing/invalid env vars."""
    for var in ("STUDIO_ASSET_CACHE_MAX_GB", "OPENMONTAGE_ASSET_CACHE_MAX_GB", "NEON_ASSET_CACHE_MAX_GB"):
        raw = os.environ.get(var)
        if raw is not None and raw.strip():
            try:
                val = float(raw.strip())
                if val >= 0:
                    return int(val * (1024**3))
            except ValueError:
                return DEFAULT_MAX_BYTES
    return DEFAULT_MAX_BYTES


def _hash_value(val: Any) -> Any:
    if isinstance(val, dict):
        return {str(k): _hash_value(v) for k, v in sorted(val.items()) if str(k) != "output_path"}
    if isinstance(val, (list, tuple)):
        return [_hash_value(x) for x in val]
    if isinstance(val, (str, Path)):
        s = str(val)
        # If string points to an existing local file, include its SHA-256 content digest rather than path alone
        if len(s) < 1024 and ("/" in s or "\\" in s or "." in s):
            try:
                p = Path(s)
                if p.is_file():
                    h = hashlib.sha256(p.read_bytes()).hexdigest()
                    return {"__file_sha256__": h, "suffix": p.suffix.lower()}
            except OSError:
                pass
        return s
    return val


def compute_cache_key(
    tool_name: str = "runner",
    tool_version: str = "1.0",
    inputs: dict[str, Any] | None = None,
    *,
    output_path: str | None = None,
) -> str:
    """Compute a 64-char SHA-256 content-addressed cache key independent of output directory/filename stem."""
    raw_inputs = dict(inputs or {})
    out_raw = output_path or raw_inputs.get("output_path") or ""
    out_ext = Path(str(out_raw)).suffix.lower() if out_raw else ""
    canonical = {
        "tool_name": str(tool_name),
        "tool_version": str(tool_version),
        "output_ext": out_ext,
        "inputs": _hash_value(raw_inputs),
    }
    blob = json.dumps(canonical, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()


cache_key = compute_cache_key
make_cache_key = compute_cache_key
content_key = compute_cache_key
compute_key = compute_cache_key


class AssetCache:
    """Thread-safe and process-safe content-addressed LRU media cache."""

    def __init__(self, cache_dir: Path | str | None = None, max_total_bytes: int | None = None) -> None:
        root = Path(__file__).resolve().parents[2]
        default_dir = Path(os.environ.get("STUDIO_ASSET_CACHE_DIR") or (root / ".cache" / "assets"))
        self.cache_dir = Path(cache_dir) if cache_dir is not None else default_dir
        self.max_total_bytes = int(max_total_bytes) if max_total_bytes is not None else default_max_total_bytes()
        self.manifest_path = self.cache_dir / "asset_manifest.jsonl"
        self._thread_lock = threading.RLock()
        self._access_seq: int = 0
        self._access_order: dict[str, tuple[float, int]] = {}
        self._hits_this_session = 0
        self._misses_this_session = 0
        self._evictions_this_session = 0
        self._cost_saved_usd_this_session = 0.0

    def cache_key(
        self,
        tool_name: str = "runner",
        tool_version: str = "1.0",
        inputs: dict[str, Any] | None = None,
        *,
        output_path: str | None = None,
    ) -> str:
        return compute_cache_key(tool_name=tool_name, tool_version=tool_version, inputs=inputs, output_path=output_path)

    compute_cache_key = cache_key

    @contextmanager
    def _locked(self, timeout: float = 10.0) -> Iterator[None]:
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        lock_file = self.cache_dir / ".cache.lock"
        deadline = time.monotonic() + timeout
        acquired_fd: int | None = None
        while True:
            try:
                acquired_fd = os.open(str(lock_file), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
                os.write(acquired_fd, f"{os.getpid()}:{threading.get_ident()}\n".encode("ascii"))
                os.close(acquired_fd)
                break
            except FileExistsError:
                if time.monotonic() >= deadline:
                    raise TimeoutError(f"Timed out acquiring asset cache lock {lock_file}") from None
                time.sleep(0.01)
        try:
            with self._thread_lock:
                yield
        finally:
            try:
                lock_file.unlink(missing_ok=True)
            except OSError:
                pass

    def _load_entries(self) -> dict[str, dict[str, Any]]:
        entries: dict[str, dict[str, Any]] = {}
        if not self.manifest_path.is_file():
            return entries
        try:
            lines = self.manifest_path.read_text(encoding="utf-8").splitlines()
        except OSError:
            return entries
        for ln in lines:
            s = ln.strip()
            if not s:
                continue
            try:
                obj = json.loads(s)
            except (ValueError, TypeError):
                continue
            if not isinstance(obj, dict):
                continue
            key = obj.get("key")
            fname = obj.get("file_name")
            if not isinstance(key, str) or not isinstance(fname, str):
                continue
            blob = self.cache_dir / fname
            if not blob.is_file():
                continue
            entries[key] = obj
        return entries

    def _save_entries(self, entries: dict[str, dict[str, Any]]) -> None:
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        ordered = sorted(entries.values(), key=lambda e: float(e.get("last_accessed") or 0.0))
        tmp = self.cache_dir / f".asset_manifest.{os.getpid()}.{threading.get_ident()}.tmp"
        body = "".join(json.dumps(item, sort_keys=True) + "\n" for item in ordered)
        tmp.write_text(body, encoding="utf-8")
        os.replace(tmp, self.manifest_path)

    def store(
        self,
        key: str,
        source_path: Path | str,
        *,
        tool_name: str = "runner",
        tool_version: str = "1.0",
        model: str = "",
        seed: int | None = None,
        cost_usd: float = 0.0,
        data: dict[str, Any] | None = None,
    ) -> bool:
        src = Path(source_path)
        if not src.is_file():
            return False
        size_bytes = src.stat().st_size
        if size_bytes <= 0:
            return False
        if self.max_total_bytes <= 0 or size_bytes > self.max_total_bytes:
            return False

        ext = src.suffix.lower() or ".bin"
        blob_name = f"{key}{ext}"

        with self._locked():
            entries = self._load_entries()
            # Compute current total size excluding key if overwriting
            total_bytes = sum(int(e.get("size_bytes") or 0) for k, e in entries.items() if k != key)

            if total_bytes + size_bytes > self.max_total_bytes:
                # Evict in LRU order (oldest access first), skipping unremovable files
                def _lru_key(e: dict[str, Any]) -> tuple[float, int]:
                    ek = str(e.get("key") or "")
                    if ek in self._access_order:
                        return self._access_order[ek]
                    return (float(e.get("last_accessed") or e.get("created_at") or 0.0), 0)

                victims = sorted(
                    (e for k, e in entries.items() if k != key),
                    key=_lru_key,
                )
                for v in victims:
                    if total_bytes + size_bytes <= self.max_total_bytes:
                        break
                    v_key = str(v["key"])
                    v_blob = self.cache_dir / str(v["file_name"])
                    try:
                        v_blob.unlink(missing_ok=True)
                    except OSError:
                        continue
                    total_bytes -= int(v.get("size_bytes") or 0)
                    entries.pop(v_key, None)
                    self._access_order.pop(v_key, None)
                    self._evictions_this_session += 1

            if total_bytes + size_bytes > self.max_total_bytes:
                return False

            dest_blob = self.cache_dir / blob_name
            tmp_blob = self.cache_dir / f".{blob_name}.{os.getpid()}.{threading.get_ident()}.tmp"
            shutil.copy2(src, tmp_blob)
            os.replace(tmp_blob, dest_blob)

            now = time.time()
            self._access_seq += 1
            self._access_order[key] = (now, self._access_seq)
            entries[key] = {
                "key": key,
                "file_name": blob_name,
                "size_bytes": size_bytes,
                "tool_name": tool_name,
                "tool_version": tool_version,
                "model": model,
                "seed": seed,
                "cost_usd": float(cost_usd or 0.0),
                "data": dict(data or {}),
                "created_at": now,
                "last_accessed": now,
            }
            self._save_entries(entries)
            return True

    def try_restore(self, key: str, dest_path: Path | str) -> dict[str, Any] | None:
        dest = Path(dest_path)
        with self._locked():
            entries = self._load_entries()
            entry = entries.get(key)
            if entry is None:
                self._misses_this_session += 1
                return None
            blob = self.cache_dir / str(entry["file_name"])
            if not blob.is_file():
                entries.pop(key, None)
                self._access_order.pop(key, None)
                self._save_entries(entries)
                self._misses_this_session += 1
                return None

            dest.parent.mkdir(parents=True, exist_ok=True)
            tmp_dest = dest.parent / f".{dest.name}.{os.getpid()}.{threading.get_ident()}.tmp"
            shutil.copy2(blob, tmp_dest)
            os.replace(tmp_dest, dest)

            now = time.time()
            self._access_seq += 1
            self._access_order[key] = (now, self._access_seq)
            entry["last_accessed"] = now
            self._hits_this_session += 1
            self._cost_saved_usd_this_session += float(entry.get("cost_usd") or 0.0)
            return dict(entry)

    def stats(self) -> dict[str, Any]:
        with self._locked():
            entries = self._load_entries()
            total_bytes = sum(int(e.get("size_bytes") or 0) for e in entries.values())
            return {
                "entry_count": len(entries),
                "total_bytes": total_bytes,
                "max_total_bytes": self.max_total_bytes,
                "hits_this_session": self._hits_this_session,
                "misses_this_session": self._misses_this_session,
                "evictions_this_session": self._evictions_this_session,
                "cost_saved_usd_this_session": self._cost_saved_usd_this_session,
            }


def get_default_asset_cache() -> AssetCache:
    global _DEFAULT_CACHE
    with _GLOBAL_LOCK:
        if _DEFAULT_CACHE is None:
            _DEFAULT_CACHE = AssetCache()
        return _DEFAULT_CACHE


def reset_default_asset_cache() -> None:
    global _DEFAULT_CACHE
    with _GLOBAL_LOCK:
        _DEFAULT_CACHE = None
