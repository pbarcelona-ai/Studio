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
        winget_applicable_checker=lambda wid: True,
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


def test_inapplicable_winget_or_platform_updates_are_filtered_out(tmp_path: Path, monkeypatch):
    prefs_file = tmp_path / "prefs.json"
    fake_aud = tmp_path / "audacity-win-3.7.9-64bit" / "Audacity.exe"
    fake_aud.parent.mkdir(parents=True)
    fake_aud.write_text("", encoding="utf-8")
    fake_ol = tmp_path / "ollama.exe"
    fake_ol.write_text("", encoding="utf-8")

    monkeypatch.setattr(
        external_tools,
        "detect_all_tools",
        lambda repo_root=None: {
            "tools": [],
            "by_id": {
                "audacity": {"id": "audacity", "installed": True, "path": str(fake_aud)},
                "ollama": {"id": "ollama", "installed": True, "path": str(fake_ol)},
            },
            "installed_count": 2,
            "total_count": 2,
        },
    )
    monkeypatch.setattr(github_updates, "_probe_cli_version", lambda exe, args: "0.40.18" if "ollama" in exe else "")

    def fake_rel(repo: str) -> dict:
        if "audacity" in repo:
            return {
                "tag_name": "Audacity-4.0.2",
                "html_url": "https://github.com/audacity/audacity/releases/tag/Audacity-4.0.2",
                "assets": [{"name": "audacity-win-4.0.2-x86_64.msi"}],
            }
        # Linux-only release must not notify on Windows
        return {
            "tag_name": "v0.40.19",
            "html_url": "https://github.com/ollama/ollama/releases/tag/v0.40.19",
            "assets": [{"name": "ollama-linux-amd64.tar.zst"}],
        }

    res = github_updates.check_updates(
        force=True,
        repo_root=tmp_path,
        prefs_path=prefs_file,
        release_fetcher=fake_rel,
        winget_applicable_checker=lambda wid: False,  # winget says "No applicable installer found"
    )
    by_id = {it["id"]: it for it in res["items"]}
    assert by_id["audacity"]["update_available"] is False
    assert by_id["audacity"]["notify"] is False
    if github_updates.os.name == "nt":
        assert by_id["ollama"]["update_available"] is False
    assert res["updates_available"] == 0


def test_apply_github_installer_runs_silent_installer_for_ollama(tmp_path: Path, monkeypatch):
    prefs_file = tmp_path / "prefs.json"
    fake_ol = tmp_path / "ollama.exe"
    fake_ol.write_text("", encoding="utf-8")

    monkeypatch.setattr(
        external_tools,
        "detect_all_tools",
        lambda repo_root=None: {
            "tools": [],
            "by_id": {"ollama": {"id": "ollama", "installed": True, "path": str(fake_ol)}},
            "installed_count": 1,
            "total_count": 1,
        },
    )
    monkeypatch.setattr(github_updates, "_probe_cli_version", lambda exe, args: "0.40.18")

    class _FakeResp:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self):
            return b"MZ-fake-installer"

    monkeypatch.setattr(github_updates.urllib.request, "urlopen", lambda req, timeout=240: _FakeResp())

    ran_cmds: list[list[str]] = []

    def fake_run(argv, **kwargs):
        ran_cmds.append(list(argv))
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(github_updates.subprocess, "run", fake_run)

    res = github_updates.apply_update(
        "ollama",
        repo_root=tmp_path,
        prefs_path=prefs_file,
        release_fetcher=lambda repo: {
            "tag_name": "v0.40.19",
            "html_url": "https://github.com/ollama/ollama/releases/tag/v0.40.19",
            "assets": [
                {
                    "name": "OllamaSetup.exe",
                    "browser_download_url": "https://github.com/ollama/ollama/releases/download/v0.40.19/OllamaSetup.exe",
                }
            ],
        },
    )
    assert res["ok"] is True
    assert res["new_version"] == "v0.40.19"
    assert ran_cmds and ran_cmds[0][0].endswith("OllamaSetup.exe")
    assert "/VERYSILENT" in ran_cmds[0]
    assert github_updates.load_prefs(prefs_file)["installed_versions"]["ollama"] == "v0.40.19"
