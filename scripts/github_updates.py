"""GitHub update checker, notification preferences, and safe updater for installed GitHub-sourced tools & repos.

Discovers:
  1. Every git clone inside `.local_ai/` (and optionally the workspace root) whose `origin` remote is on `github.com`.
  2. Every installed external tool whose upstream releases are hosted on GitHub (Pandoc, HandBrakeCLI, Audacity,
     Darktable, Subtitle Edit, Calibre, Ollama, Trelby, stable-diffusion.cpp).

All subprocess calls use explicit argv lists (no shell). Preferences persist in `~/.pistachios_studio/update_prefs.json`.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
import time
import urllib.error
import urllib.request
import zipfile
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import external_tools

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PREFS_PATH = Path.home() / ".pistachios_studio" / "update_prefs.json"
CACHE_TTL_SECONDS = 6 * 3600

_GH_REMOTE_RE = re.compile(r"github\.com[:/](?P<owner>[A-Za-z0-9_.-]+)/(?P<repo>[A-Za-z0-9_.-]+?)(?:\.git)?$", re.IGNORECASE)
_VER_RE = re.compile(r"(\d+(?:\.\d+){1,3})")

# Known external tools whose official releases live on GitHub
GITHUB_RELEASE_TOOLS: tuple[dict[str, Any], ...] = (
    {
        "id": "pandoc",
        "name": "Pandoc",
        "repo": "jgm/pandoc",
        "version_args": ("--version",),
        "update_kind": "winget",
        "winget_id": "JohnMacFarlane.Pandoc",
    },
    {
        "id": "handbrake",
        "name": "HandBrake CLI",
        "repo": "HandBrake/HandBrake",
        "version_args": ("--version",),
        "update_kind": "winget",
        "winget_id": "HandBrake.HandBrake.CLI",
    },
    {
        "id": "audacity",
        "name": "Audacity",
        "repo": "audacity/audacity",
        "version_args": (),
        "update_kind": "winget",
        "winget_id": "Audacity.Audacity",
    },
    {
        "id": "darktable",
        "name": "Darktable",
        "repo": "darktable-org/darktable",
        "version_args": ("--version",),
        "update_kind": "winget",
        "winget_id": "darktable.darktable",
    },
    {
        "id": "subtitle_edit",
        "name": "Subtitle Edit",
        "repo": "SubtitleEdit/subtitleedit",
        "version_args": (),
        "update_kind": "github_zip",
        "asset_pattern": r"^SubtitleEdit-Windows-x64\.zip$|^SE\d.*\.zip$",
    },
    {
        "id": "calibre",
        "name": "Calibre",
        "repo": "kovidgoyal/calibre",
        "version_args": ("--version",),
        "update_kind": "github_msi_extract",
        "asset_pattern": r"^calibre-64bit-.*\.msi$",
    },
    {
        "id": "ollama",
        "name": "Ollama",
        "repo": "ollama/ollama",
        "version_args": ("--version",),
        "update_kind": "github_installer",
        "asset_pattern": r"^OllamaSetup\.exe$",
        "installer_args": ("/VERYSILENT", "/NORESTART", "/SUPPRESSMSGBOXES"),
    },
    {
        "id": "trelby",
        "name": "Trelby",
        "repo": "trelby/trelby",
        "version_args": (),
        "update_kind": "manual_release",
    },
    {
        "id": "sd_cli",
        "name": "stable-diffusion.cpp (sd-cli)",
        "repo": "leejet/stable-diffusion.cpp",
        "version_args": (),
        "update_kind": "manual_release",
    },
)


def _now_iso() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def load_prefs(prefs_path: Path | None = None) -> dict[str, Any]:
    path = prefs_path or DEFAULT_PREFS_PATH
    base: dict[str, Any] = {
        "notifications_enabled": True,
        "dismissed_versions": {},
        "installed_versions": {},
        "last_checked_at": "",
        "last_checked_ts": 0.0,
        "cached_items": [],
    }
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(raw, dict):
            base.update(raw)
    except (OSError, ValueError):
        pass
    if not isinstance(base.get("dismissed_versions"), dict):
        base["dismissed_versions"] = {}
    if not isinstance(base.get("installed_versions"), dict):
        base["installed_versions"] = {}
    if not isinstance(base.get("cached_items"), list):
        base["cached_items"] = []
    base["notifications_enabled"] = bool(base.get("notifications_enabled", True))
    return base


def save_prefs(prefs: dict[str, Any], prefs_path: Path | None = None) -> dict[str, Any]:
    path = prefs_path or DEFAULT_PREFS_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(prefs, indent=2, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, path)
    return prefs


def set_preferences(
    *,
    notifications_enabled: bool | None = None,
    dismiss_id: str | None = None,
    dismiss_version: str | None = None,
    clear_dismiss_id: str | None = None,
    prefs_path: Path | None = None,
) -> dict[str, Any]:
    """Update notification on/off preference or dismiss a specific version for an item."""
    prefs = load_prefs(prefs_path)
    if notifications_enabled is not None:
        prefs["notifications_enabled"] = bool(notifications_enabled)
    if dismiss_id and dismiss_version:
        prefs["dismissed_versions"][str(dismiss_id).strip()] = str(dismiss_version).strip()
    if clear_dismiss_id:
        prefs["dismissed_versions"].pop(str(clear_dismiss_id).strip(), None)
    return save_prefs(prefs, prefs_path)


def parse_version_tuple(raw: str) -> tuple[int, ...]:
    """Extract comparable numeric version tuple from strings like 'v5.6.2', 'Audacity-3.7.9', or 'release-5.6.2'."""
    m = _VER_RE.search(str(raw or ""))
    if not m:
        return ()
    return tuple(int(p) for p in m.group(1).split("."))


def is_newer_version(installed: str, latest: str) -> bool:
    """Return True if `latest` is strictly newer than `installed`."""
    lat = str(latest or "").strip()
    inst = str(installed or "").strip()
    if not lat or not inst or inst == "unknown":
        return False
    iv = parse_version_tuple(inst)
    lv = parse_version_tuple(lat)
    if iv and lv:
        n = max(len(iv), len(lv))
        iv_p = iv + (0,) * (n - len(iv))
        lv_p = lv + (0,) * (n - len(lv))
        return lv_p > iv_p
    return lat.lower() != inst.lower()


def _parse_github_remote(url: str) -> str:
    m = _GH_REMOTE_RE.search(str(url or "").strip())
    if not m:
        return ""
    return f"{m.group('owner')}/{m.group('repo')}"


def _git_output(repo_dir: Path, *args: str, timeout: float = 10.0) -> str:
    git_exe = shutil.which("git")
    if not git_exe:
        return ""
    try:
        r = subprocess.run(
            [git_exe, "-C", str(repo_dir), *args],
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return (r.stdout or "").strip() if r.returncode == 0 else ""
    except (OSError, subprocess.SubprocessError):
        return ""


def _probe_cli_version(exe_path: str, version_args: tuple[str, ...]) -> str:
    if not exe_path or not version_args:
        return ""
    p = Path(exe_path)
    if not p.is_file():
        return ""
    try:
        r = subprocess.run(
            [str(p), *version_args],
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=8.0,
        )
        out = ((r.stdout or "") + "\n" + (r.stderr or "")).strip()
        m = _VER_RE.search(out)
        return m.group(1) if m else ""
    except (OSError, subprocess.SubprocessError):
        return ""


def _read_version_marker(exe_path: str) -> str:
    if not exe_path:
        return ""
    p = Path(exe_path)
    for parent in (p.parent, p.parent.parent):
        marker = parent / ".github_version"
        if marker.is_file():
            try:
                val = marker.read_text(encoding="utf-8-sig").strip()
                if val:
                    return val
            except OSError:
                pass
    return ""


def discover_github_items(
    repo_root: Path | None = None,
    *,
    prefs: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Discover all installed items on this computer that originate from a GitHub repository."""
    root = repo_root or REPO_ROOT
    local_ai = root / ".local_ai"
    pref_versions = (prefs or {}).get("installed_versions") or {}
    items: list[dict[str, Any]] = []
    seen_ids: set[str] = set()

    # 1. All GitHub git repositories cloned inside .local_ai/
    if local_ai.is_dir():
        for child in sorted(local_ai.iterdir()):
            if not child.is_dir() or not (child / ".git").exists():
                continue
            remote_url = _git_output(child, "remote", "get-url", "origin")
            gh_repo = _parse_github_remote(remote_url)
            if not gh_repo:
                continue
            head_sha = _git_output(child, "rev-parse", "--short=8", "HEAD") or "unknown"
            item_id = f"git_{re.sub(r'[^a-z0-9]+', '_', child.name.lower()).strip('_')}"
            seen_ids.add(item_id)
            items.append(
                {
                    "id": item_id,
                    "name": child.name,
                    "repo": gh_repo,
                    "kind": "git_repo",
                    "local_path": str(child),
                    "installed_version": head_sha,
                    "update_kind": "git_pull",
                    "can_auto_update": True,
                    "release_url": f"https://github.com/{gh_repo}",
                }
            )

    # 2. Installed external tools whose upstream releases are hosted on GitHub
    detected = external_tools.detect_all_tools(repo_root=root)["by_id"]
    for spec in GITHUB_RELEASE_TOOLS:
        tid = str(spec["id"])
        if tid in seen_ids:
            continue
        info = detected.get(tid)
        if not info or not info.get("installed"):
            continue
        exe_path = str(info.get("path") or "")
        ver = (
            _read_version_marker(exe_path)
            or str(pref_versions.get(tid) or "")
            or _probe_cli_version(exe_path, tuple(spec.get("version_args") or ()))
            or "installed"
        )
        # Try extracting version from winget package folder name if still generic (e.g. Audacity 3.7.9)
        if ver == "installed" and exe_path:
            m_path = _VER_RE.search(exe_path)
            if m_path:
                ver = m_path.group(1)
        ukind = str(spec.get("update_kind") or "manual_release")
        items.append(
            {
                "id": tid,
                "name": str(spec["name"]),
                "repo": str(spec["repo"]),
                "kind": "github_release",
                "local_path": exe_path,
                "installed_version": ver,
                "update_kind": ukind,
                "winget_id": str(spec.get("winget_id") or ""),
                "asset_pattern": str(spec.get("asset_pattern") or ""),
                "installer_args": list(spec.get("installer_args") or ()),
                "can_auto_update": ukind in ("winget", "github_zip", "github_installer", "github_msi_extract"),
                "release_url": f"https://github.com/{spec['repo']}/releases/latest",
            }
        )
    return items


def _release_has_platform_asset(assets: list[Any], *, asset_pattern: str = "") -> bool:
    """Return True if the GitHub release contains an installer/archive applicable to this OS/architecture."""
    if not assets:
        return True  # Source-only or tag-only release; cannot filter by assets
    names = [str(a.get("name") or "") for a in assets if isinstance(a, dict) and a.get("name")]
    if not names:
        return True
    if asset_pattern:
        pat = re.compile(asset_pattern, re.IGNORECASE)
        return any(pat.search(n) and "beta" not in n.lower() for n in names)
    if os.name == "nt":
        for n in names:
            low = n.lower()
            if any(bad in low for bad in ("linux", "darwin", "macos", ".dmg", ".appimage", ".deb", ".rpm", ".flatpak")):
                continue
            if "arm64" in low and "x64" not in low and "amd64" not in low and "x86_64" not in low:
                continue
            if any(good in low for good in ("win", ".exe", ".msi")):
                return True
        return False
    return True


def _winget_user_upgrade_applicable(winget_id: str, timeout: float = 12.0) -> bool:
    """Verify winget actually has an applicable user-scope installer for this Windows installation."""
    if os.name != "nt" or not winget_id:
        return True
    winget_exe = shutil.which("winget")
    if not winget_exe:
        return False
    try:
        proc = subprocess.run(
            [winget_exe, "show", "--id", winget_id, "--exact", "--scope", "user", "--accept-source-agreements"],
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        combined = ((proc.stdout or "") + "\n" + (proc.stderr or "")).lower()
        if "no applicable installer found" in combined or "no package found" in combined:
            return False
        return proc.returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def _fetch_latest_github_release(repo: str, timeout: float = 10.0) -> dict[str, Any]:
    url = f"https://api.github.com/repos/{repo}/releases/latest"
    headers = {"User-Agent": "Pistachios-Studio-Updater", "Accept": "application/vnd.github+json"}
    token = os.environ.get("GITHUB_TOKEN", "").strip()
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, headers=headers, method="GET")
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310  fixed https api.github.com URL
        data = json.loads(resp.read().decode("utf-8"))
    if not isinstance(data, dict):
        return {}
    return {
        "tag_name": str(data.get("tag_name") or "").strip(),
        "name": str(data.get("name") or "").strip(),
        "html_url": str(data.get("html_url") or f"https://github.com/{repo}/releases/latest"),
        "assets": data.get("assets") or [],
    }


def _fetch_git_remote_head(repo_dir: Path, timeout: float = 12.0) -> str:
    out = _git_output(repo_dir, "ls-remote", "origin", "HEAD", timeout=timeout)
    if not out:
        return ""
    first = out.splitlines()[0].split()[0].strip()
    return first[:8] if len(first) >= 7 else ""


def check_updates(
    *,
    force: bool = False,
    repo_root: Path | None = None,
    prefs_path: Path | None = None,
    release_fetcher: Callable[[str], dict[str, Any]] | None = None,
    git_head_fetcher: Callable[[Path], str] | None = None,
    winget_applicable_checker: Callable[[str], bool] | None = None,
) -> dict[str, Any]:
    """Check all discovered GitHub-sourced items for available updates (cached for 6h unless force=True)."""
    prefs = load_prefs(prefs_path)
    now_ts = time.time()
    dismissed: dict[str, str] = prefs.get("dismissed_versions", {})

    if not force and prefs.get("cached_items") and (now_ts - float(prefs.get("last_checked_ts") or 0.0)) < CACHE_TTL_SECONDS:
        items = []
        for raw in prefs["cached_items"]:
            it = dict(raw)
            lat = str(it.get("latest_version") or "")
            is_dismissed = bool(lat and dismissed.get(str(it.get("id") or "")) == lat)
            it["dismissed"] = is_dismissed
            it["notify"] = bool(prefs["notifications_enabled"] and it.get("update_available") and not is_dismissed)
            items.append(it)
        updates = [it for it in items if it.get("update_available")]
        notify_items = [it for it in items if it.get("notify")]
        return {
            "notifications_enabled": prefs["notifications_enabled"],
            "last_checked_at": prefs.get("last_checked_at") or "",
            "cached": True,
            "items": items,
            "updates_available": len(updates),
            "notify_count": len(notify_items),
        }

    discovered = discover_github_items(repo_root=repo_root, prefs=prefs)
    rel_fetch = release_fetcher or _fetch_latest_github_release
    git_fetch = git_head_fetcher or _fetch_git_remote_head
    wg_check = winget_applicable_checker or _winget_user_upgrade_applicable

    checked: list[dict[str, Any]] = []
    for item in discovered:
        entry = dict(item)
        entry["latest_version"] = ""
        entry["update_available"] = False
        entry["error"] = ""
        try:
            if entry["kind"] == "git_repo":
                remote_sha = git_fetch(Path(str(entry["local_path"])))
                if remote_sha:
                    entry["latest_version"] = remote_sha
                    entry["update_available"] = (
                        entry["installed_version"] not in ("", "unknown")
                        and remote_sha.lower() != str(entry["installed_version"]).lower()
                    )
            else:
                rel = rel_fetch(str(entry["repo"]))
                tag = str(rel.get("tag_name") or "").strip()
                if rel.get("html_url"):
                    entry["release_url"] = str(rel["html_url"])
                if tag:
                    entry["latest_version"] = tag
                    if entry["installed_version"] not in ("", "installed", "unknown") and is_newer_version(str(entry["installed_version"]), tag):
                        has_asset = _release_has_platform_asset(
                            list(rel.get("assets") or []),
                            asset_pattern=str(entry.get("asset_pattern") or ""),
                        )
                        if has_asset:
                            if entry.get("update_kind") == "winget":
                                entry["update_available"] = bool(wg_check(str(entry.get("winget_id") or "")))
                            else:
                                entry["update_available"] = True
        except Exception as e:
            entry["error"] = str(e)[:180]

        lat = str(entry["latest_version"])
        is_dismissed = bool(lat and dismissed.get(str(entry["id"])) == lat)
        entry["dismissed"] = is_dismissed
        entry["notify"] = bool(prefs["notifications_enabled"] and entry["update_available"] and not is_dismissed)
        checked.append(entry)

    prefs["last_checked_at"] = _now_iso()
    prefs["last_checked_ts"] = now_ts
    prefs["cached_items"] = checked
    save_prefs(prefs, prefs_path)

    return {
        "notifications_enabled": prefs["notifications_enabled"],
        "last_checked_at": prefs["last_checked_at"],
        "cached": False,
        "items": checked,
        "updates_available": sum(1 for it in checked if it.get("update_available")),
        "notify_count": sum(1 for it in checked if it.get("notify")),
    }


def apply_update(
    item_id: str,
    *,
    repo_root: Path | None = None,
    prefs_path: Path | None = None,
    release_fetcher: Callable[[str], dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Apply an update for a discovered GitHub item (git pull, winget user-scope upgrade, or portable GitHub zip)."""
    root = repo_root or REPO_ROOT
    prefs = load_prefs(prefs_path)
    items = discover_github_items(repo_root=root, prefs=prefs)
    target = next((it for it in items if it["id"] == item_id), None)
    if target is None:
        raise ValueError(f"Unknown or uninstalled GitHub item: {item_id!r}")

    ukind = str(target.get("update_kind") or "")
    if ukind == "git_pull":
        git_exe = shutil.which("git")
        if not git_exe:
            return {"ok": False, "id": item_id, "error": "git executable not found on PATH"}
        repo_dir = Path(str(target["local_path"]))
        proc = subprocess.run(
            [git_exe, "-C", str(repo_dir), "pull", "--ff-only"],
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=180,
        )
        if proc.returncode != 0:
            return {
                "ok": False,
                "id": item_id,
                "error": (proc.stderr or proc.stdout or f"git pull failed ({proc.returncode})").strip()[:400],
            }
        # If it is a uv-managed project (e.g., ACE-Step-1.5), sync dependencies cleanly
        uv_exe = shutil.which("uv")
        if uv_exe and (repo_dir / "uv.lock").is_file():
            subprocess.run(
                [uv_exe, "sync"],
                cwd=str(repo_dir),
                stdin=subprocess.DEVNULL,
                capture_output=True,
                text=True,
                timeout=300,
                check=False,
            )
        new_sha = _git_output(repo_dir, "rev-parse", "--short=8", "HEAD") or target["installed_version"]
        prefs["dismissed_versions"].pop(item_id, None)
        prefs["last_checked_ts"] = 0.0
        save_prefs(prefs, prefs_path)
        return {
            "ok": True,
            "id": item_id,
            "name": target["name"],
            "new_version": new_sha,
            "message": f"Updated {target['name']} to {new_sha}.",
        }

    if ukind == "winget":
        winget_exe = shutil.which("winget")
        wid = str(target.get("winget_id") or "")
        if not winget_exe or not wid:
            return {
                "ok": False,
                "id": item_id,
                "release_url": target["release_url"],
                "error": "winget is unavailable; download the latest release manually.",
            }
        proc = subprocess.run(
            [
                winget_exe,
                "upgrade",
                "--id",
                wid,
                "--exact",
                "--scope",
                "user",
                "--silent",
                "--accept-package-agreements",
                "--accept-source-agreements",
            ],
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=240,
        )
        if proc.returncode != 0:
            detail = (proc.stderr or proc.stdout or f"winget upgrade exited {proc.returncode}").strip()
            low = detail.lower()
            if "no applicable upgrade found" in low or "no applicable update found" in low or "no applicable installer found" in low:
                prefs["last_checked_ts"] = 0.0
                save_prefs(prefs, prefs_path)
                return {
                    "ok": True,
                    "inapplicable": True,
                    "id": item_id,
                    "name": target["name"],
                    "message": f"No applicable Windows upgrade for {target['name']} on this installation.",
                }
            return {
                "ok": False,
                "id": item_id,
                "release_url": target["release_url"],
                "error": detail[:400],
            }
        prefs["dismissed_versions"].pop(item_id, None)
        prefs["last_checked_ts"] = 0.0
        save_prefs(prefs, prefs_path)
        return {
            "ok": True,
            "id": item_id,
            "name": target["name"],
            "message": f"Upgraded {target['name']} via winget.",
        }

    if ukind == "github_zip":
        rel = (release_fetcher or _fetch_latest_github_release)(str(target["repo"]))
        pat = re.compile(str(target.get("asset_pattern") or r"\.zip$"), re.IGNORECASE)
        asset = next(
            (
                a
                for a in (rel.get("assets") or [])
                if isinstance(a, dict) and pat.search(str(a.get("name") or "")) and "beta" not in str(a.get("name") or "").lower()
            ),
            None,
        )
        if not asset or not asset.get("browser_download_url"):
            return {
                "ok": False,
                "id": item_id,
                "release_url": target["release_url"],
                "error": f"No matching Windows portable archive found in latest release for {target['name']}.",
            }
        dest_dir = Path(str(target["local_path"])).parent
        dest_dir.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="studio-gh-upd-") as tmp:
            zip_path = Path(tmp) / str(asset["name"])
            req = urllib.request.Request(str(asset["browser_download_url"]), headers={"User-Agent": "Pistachios-Studio-Updater"})
            with urllib.request.urlopen(req, timeout=120) as resp:  # noqa: S310  GitHub release asset URL
                zip_path.write_bytes(resp.read())
            with zipfile.ZipFile(zip_path, "r") as zf:
                zf.extractall(dest_dir)
        tag = str(rel.get("tag_name") or "").strip()
        if tag:
            (dest_dir / ".github_version").write_text(tag, encoding="utf-8")
            prefs["installed_versions"][item_id] = tag
        prefs["dismissed_versions"].pop(item_id, None)
        prefs["last_checked_ts"] = 0.0
        save_prefs(prefs, prefs_path)
        return {
            "ok": True,
            "id": item_id,
            "name": target["name"],
            "new_version": tag,
            "message": f"Updated {target['name']} to {tag or 'latest'}.",
        }

    if ukind in ("github_installer", "github_msi_extract"):
        rel = (release_fetcher or _fetch_latest_github_release)(str(target["repo"]))
        pat = re.compile(str(target.get("asset_pattern") or r"\.(?:exe|msi)$"), re.IGNORECASE)
        asset = next(
            (
                a
                for a in (rel.get("assets") or [])
                if isinstance(a, dict) and pat.search(str(a.get("name") or "")) and "beta" not in str(a.get("name") or "").lower()
            ),
            None,
        )
        dl_url = str(asset.get("browser_download_url") or "") if asset else ""
        if not asset or not dl_url.startswith(("https://github.com/", "https://objects.githubusercontent.com/")):
            return {
                "ok": False,
                "id": item_id,
                "manual": True,
                "release_url": target["release_url"],
                "error": f"No matching Windows installer found in latest release for {target['name']}.",
            }
        tag = str(rel.get("tag_name") or "").strip()
        with tempfile.TemporaryDirectory(prefix="studio-gh-inst-") as tmp:
            inst_path = Path(tmp) / Path(str(asset["name"])).name
            req = urllib.request.Request(dl_url, headers={"User-Agent": "Pistachios-Studio-Updater"})
            with urllib.request.urlopen(req, timeout=240) as resp:  # noqa: S310  verified https github.com release asset URL
                inst_path.write_bytes(resp.read())

            if ukind == "github_msi_extract":
                # Portable MSI extraction (e.g. Calibre into .local_ai/apps/CalibrePortable)
                cur_exe = Path(str(target["local_path"]))
                dest_dir = cur_exe.parent
                for anc in cur_exe.parents:
                    if anc.name == "CalibrePortable":
                        dest_dir = anc
                        break
                dest_dir.mkdir(parents=True, exist_ok=True)
                argv = ["msiexec.exe", "/a", str(inst_path), "/qn", f"TARGETDIR={dest_dir}"]
                proc = subprocess.run(argv, stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=300)
                if proc.returncode != 0:
                    return {
                        "ok": False,
                        "id": item_id,
                        "release_url": target["release_url"],
                        "error": (proc.stderr or proc.stdout or f"MSI extract failed ({proc.returncode})").strip()[:400],
                    }
                if tag:
                    (dest_dir / ".github_version").write_text(tag, encoding="utf-8")
            else:
                extra_args = [str(a) for a in (target.get("installer_args") or ())]
                proc = subprocess.run(
                    [str(inst_path), *extra_args],
                    stdin=subprocess.DEVNULL,
                    capture_output=True,
                    text=True,
                    timeout=300,
                )
                if proc.returncode != 0:
                    return {
                        "ok": False,
                        "id": item_id,
                        "release_url": target["release_url"],
                        "error": (proc.stderr or proc.stdout or f"Installer exited with code {proc.returncode}").strip()[:400],
                    }

        if tag:
            prefs["installed_versions"][item_id] = tag
        prefs["dismissed_versions"].pop(item_id, None)
        prefs["last_checked_ts"] = 0.0
        save_prefs(prefs, prefs_path)
        return {
            "ok": True,
            "id": item_id,
            "name": target["name"],
            "new_version": tag,
            "message": f"Installed {target['name']} {tag or 'latest'}.",
        }

    return {
        "ok": False,
        "id": item_id,
        "manual": True,
        "release_url": target["release_url"],
        "message": f"Open {target['release_url']} to download the latest {target['name']} installer.",
    }
