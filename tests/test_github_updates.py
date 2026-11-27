"""Tests for GitHub update discovery, semantic version checks, notification toggle persistence, popup dismissal, and update execution."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import external_tools  # noqa: E402
import github_updates  # noqa: E402
from studio_app import mcp_routes  # noqa: E402
from studio_app.api import HttpError, Request  # noqa: E402


def _make_mock_git_repo(repo_dir: Path, remote_url: str) -> str:
    repo_dir.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-q"], cwd=str(repo_dir), check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=str(repo_dir), check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=str(repo_dir), check=True)
    subprocess.run(["git", "remote", "add", "origin", remote_url], cwd=str(repo_dir), check=True)
    (repo_dir / "README.md").write_text("hello", encoding="utf-8")
    subprocess.run(["git", "add", "README.md"], cwd=str(repo_dir), check=True)
    subprocess.run(["git", "commit", "-q", "-m", "init"], cwd=str(repo_dir), check=True)
    sha = subprocess.run(
        ["git", "rev-parse", "--short=8", "HEAD"],
        cwd=str(repo_dir),
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    return sha


def test_version_comparison_helpers():
    assert github_updates.is_newer_version("3.14", "3.15") is True
    assert github_updates.is_newer_version("v5.4.0", "5.4.0") is False
    assert github_updates.is_newer_version("Audacity-3.7.9", "Audacity-3.8.0") is True
    assert github_updates.is_newer_version("5.6.2", "release-5.6.1") is False


def test_discover_and_check_github_updates_and_notification_toggle(tmp_path: Path, monkeypatch):
    sha = _make_mock_git_repo(tmp_path / ".local_ai" / "Wan2GP", "https://github.com/deepbeepmeep/Wan2GP.git")
    prefs_file = tmp_path / "prefs.json"

    fake_pandoc = tmp_path / "pandoc.exe"
    fake_pandoc.write_text("", encoding="utf-8")
    monkeypatch.setattr(
        external_tools,
        "detect_all_tools",
        lambda repo_root=None: {
            "tools": [],
            "by_id": {"pandoc": {"id": "pandoc", "installed": True, "path": str(fake_pandoc)}},
            "installed_count": 1,
            "total_count": 1,
        },
    )
    monkeypatch.setattr(github_updates, "_probe_cli_version", lambda exe, args: "3.14")

    res = github_updates.check_updates(
        force=True,
        repo_root=tmp_path,
        prefs_path=prefs_file,
        release_fetcher=lambda repo: {"tag_name": "3.15", "html_url": f"https://github.com/{repo}/releases/tag/3.15"},
        git_head_fetcher=lambda d: "deadbeef",
    )
    assert res["notifications_enabled"] is True
    assert res["updates_available"] == 2
    assert res["notify_count"] == 2

    by_id = {it["id"]: it for it in res["items"]}
    assert by_id["git_wan2gp"]["installed_version"] == sha
    assert by_id["git_wan2gp"]["latest_version"] == "deadbeef"
    assert by_id["git_wan2gp"]["update_available"] is True
    assert by_id["git_wan2gp"]["notify"] is True
    assert by_id["pandoc"]["update_available"] is True

    # Dismissing pandoc's 3.15 suppresses notification for pandoc only
    github_updates.set_preferences(dismiss_id="pandoc", dismiss_version="3.15", prefs_path=prefs_file)
    res_cached = github_updates.check_updates(force=False, repo_root=tmp_path, prefs_path=prefs_file)
    assert res_cached["cached"] is True
    assert res_cached["notify_count"] == 1

    # Turning notifications OFF suppresses popup for all items while preserving updates_available count
    github_updates.set_preferences(notifications_enabled=False, prefs_path=prefs_file)
    res_off = github_updates.check_updates(force=False, repo_root=tmp_path, prefs_path=prefs_file)
    assert res_off["notifications_enabled"] is False
    assert res_off["updates_available"] == 2
    assert res_off["notify_count"] == 0

    # Turning notifications back ON restores notification for non-dismissed Wan2GP
    github_updates.set_preferences(notifications_enabled=True, prefs_path=prefs_file)
    res_on = github_updates.check_updates(force=False, repo_root=tmp_path, prefs_path=prefs_file)
    assert res_on["notifications_enabled"] is True
    assert res_on["notify_count"] == 1


def test_apply_git_pull_update_and_routes(tmp_path: Path, monkeypatch):
    _make_mock_git_repo(tmp_path / ".local_ai" / "LatentSync", "https://github.com/bytedance/LatentSync.git")
    prefs_file = tmp_path / "prefs.json"

    monkeypatch.setattr(
        external_tools,
        "detect_all_tools",
        lambda repo_root=None: {"tools": [], "by_id": {}, "installed_count": 0, "total_count": 0},
    )

    real_run = subprocess.run
    pulled: list[list[str]] = []

    def fake_run(argv, **kwargs):
        if "pull" in argv:
            pulled.append(list(argv))
            return SimpleNamespace(returncode=0, stdout="Already up to date.\n", stderr="")
        return real_run(argv, **kwargs)

    monkeypatch.setattr(github_updates.subprocess, "run", fake_run)

    res = github_updates.apply_update("git_latentsync", repo_root=tmp_path, prefs_path=prefs_file)
    assert res["ok"] is True
    assert pulled and "pull" in pulled[0] and "--ff-only" in pulled[0]

    # Route validation
    with pytest.raises(HttpError) as exc:
        mcp_routes.api_github_updates_apply(Request(body={}))
    assert exc.value.code == 400
