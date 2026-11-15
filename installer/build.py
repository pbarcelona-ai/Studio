#!/usr/bin/env python3
"""Build the installers (milestone MI, rule 12):  python installer/build.py windows|macos [--arch arm64|x86_64] [--out dist]

  windows  dist/PistachiosStudio-<version>-Setup.exe   Inno Setup 6 (ISCC), per user, no admin rights, Start-menu + desktop shortcuts, uninstaller
  macos    dist/PistachiosStudio-<version>-<arch>.dmg   "Pistachio's Studio.app" + an Applications link (drag to install)

Both carry the Studio's files, their own Python 3.12 (python-build-standalone, fetched with `uv python install`) and uv. The first start
runs scripts/install_studio.py, which makes .venv with uv and shows the progress page. Needs uv on PATH (pip install uv) and, for the
icon, Pillow. Signing is optional: set WIN_SIGN_CMD (an Inno Setup SignTool command) or MAC_SIGN_ID (+ MAC_NOTARY_PROFILE to notarise).
"""
from __future__ import annotations

import argparse
import os
import platform
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PY = "3.12"
APP = "Pistachio's Studio"
# what the installed Studio does not need: tests, reviews, design notes, the owner's own projects and logs
SKIP = ("tests/", "code_reviews/", "replica/", "adr/", "graphify-out/", "projects/", "books/", "my_downloads/", "logs/", ".github/", ".claude/",
        "installer/", "results.txt", "studio.log", "uv.lock", ".coverage", ".studio_session.json")


def say(text: str) -> None:
    print(text, flush=True)


def version() -> str:
    for line in (ROOT / "pyproject.toml").read_text(encoding="utf-8").splitlines():
        if line.startswith("version"):
            return line.split("=", 1)[1].strip().strip('"')
    return "0.0.0"


def payload_files() -> list[str]:
    out = subprocess.run(["git", "ls-files", "-z"], cwd=ROOT, capture_output=True, text=True, check=True).stdout
    return [f for f in out.split("\0") if f and not f.startswith(SKIP) and not f.endswith(".pdf") and (ROOT / f).is_file()]


def stage_app(dest: Path) -> None:
    files = payload_files()
    for f in files:
        (dest / f).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / f, dest / f)
    sha = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, capture_output=True, text=True, check=False).stdout.strip()
    (dest / "BUILD_ID").write_text(f"{version()} {sha} {time.strftime('%Y-%m-%dT%H:%M:%S')}\n", encoding="utf-8")
    say(f"staged {len(files)} files")


def uv() -> str:
    found = shutil.which("uv")
    if not found:
        sys.exit("uv is needed to fetch the bundled Python: pip install uv")
    return found


def stage_runtime(dest: Path, target: str, arch: str) -> None:
    """dest/runtime/python (python-build-standalone) and dest/runtime/uv(.exe)."""
    key = f"cpython-{PY}-{target}-{'aarch64' if arch == 'arm64' else arch}-none"
    env = {**os.environ, "UV_PYTHON_PREFERENCE": "only-managed"}       # python-build-standalone, never a Python already on this computer
    subprocess.run([uv(), "python", "install", key], check=True, env=env)
    pydir = Path(subprocess.run([uv(), "python", "dir"], capture_output=True, text=True, check=True, env=env).stdout.strip())
    found = sorted((d for d in pydir.glob(f"cpython-{PY}.*-{key.split('-', 2)[2]}") if d.is_dir() and not d.is_symlink()),
                   key=lambda d: [int(x) for x in d.name.split("-")[1].split(".")[:3] if x.isdigit()])
    if not found:
        sys.exit(f"uv did not install {key} into {pydir}")
    home = found[-1]                                           # the newest 3.12.x (not "uv python find": that prefers an active .venv)
    shutil.copytree(home, dest / "runtime" / "python", symlinks=True)
    (dest / "runtime" / "python" / "EXTERNALLY-MANAGED").unlink(missing_ok=True)   # ours alone; .venv is made from it
    uv_name = "uv.exe" if target == "windows" else "uv"
    host_arch = {"amd64": "x86_64", "x86_64": "x86_64", "arm64": "aarch64", "aarch64": "aarch64"}.get(platform.machine().lower(), "")
    want_arch = {"x86_64": "x86_64", "arm64": "aarch64", "aarch64": "aarch64"}[arch]
    if host_arch == want_arch:
        shutil.copy2(uv(), dest / "runtime" / uv_name)
    else:                                                      # e.g. an Intel Mac build on an Apple-silicon runner: fetch that uv
        ver = subprocess.run([uv(), "--version"], capture_output=True, text=True, check=True).stdout.split()[1]
        triple = {"macos": "apple-darwin", "windows": "pc-windows-msvc"}[target]
        url = f"https://github.com/astral-sh/uv/releases/download/{ver}/uv-{want_arch}-{triple}.tar.gz"
        with tempfile.TemporaryDirectory() as t:
            tgz = Path(t) / "uv.tgz"
            urllib.request.urlretrieve(url, tgz)                 # noqa: S310  a fixed https release address
            with tarfile.open(tgz) as tf:
                member = next(m for m in tf.getmembers() if m.name.endswith("/" + uv_name) and m.isfile())
                (dest / "runtime" / uv_name).write_bytes(tf.extractfile(member).read())   # type: ignore[union-attr]
        (dest / "runtime" / uv_name).chmod(0o755)
    say(f"runtime: Python {PY} ({arch}) and uv")


def icon(dest: Path, kind: str) -> Path | None:
    """studio.ico (Windows) or applet.icns (macOS), drawn by scripts/make_icon.py; None if Pillow is missing."""
    with tempfile.TemporaryDirectory() as t:
        r = subprocess.run([sys.executable, str(ROOT / "scripts" / "make_icon.py"), t], capture_output=True, text=True, check=False)
        png, icns = Path(t) / "icon_1024.png", Path(t) / "icon.icns"
        if kind == "ico" and png.is_file():
            try:
                from PIL import Image
            except ImportError:
                return None
            out = dest / "studio.ico"
            Image.open(png).save(out, sizes=[(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
            return out
        if kind == "icns" and icns.is_file():
            out = dest / "applet.icns"
            shutil.copy2(icns, out)
            return out
        say("no icon made: " + (r.stderr.strip()[-200:] or "Pillow missing"))
    return None


def iscc() -> str:
    for c in (shutil.which("iscc"), r"C:\Program Files (x86)\Inno Setup 6\ISCC.exe", r"C:\Program Files\Inno Setup 6\ISCC.exe"):
        if c and Path(c).is_file():
            return c
    sys.exit("Inno Setup 6 is needed (choco install innosetup, or https://jrsoftware.org/isdl.php)")


def build_windows(out: Path, arch: str) -> Path:
    with tempfile.TemporaryDirectory(prefix="studio-win-") as t:
        stage = Path(t) / "stage"
        stage_app(stage)
        stage_runtime(stage, "windows", arch)
        icon(stage, "ico")
        argv = [iscc(), f"/DAppVersion={version()}", f"/DStage={stage}", f"/DOutDir={out}", str(ROOT / "installer" / "windows" / "studio.iss")]
        if os.environ.get("WIN_SIGN_CMD"):
            argv[1:1] = [f"/Sstudiosign={os.environ['WIN_SIGN_CMD']}", "/DSIGN"]
        subprocess.run(argv, check=True)
    exe = out / f"PistachiosStudio-{version()}-Setup.exe"
    say(f"built {exe}")
    return exe


LAUNCHER = """#!/bin/sh
# Pistachio's Studio: install or update into the person's own folder (the progress page opens in the browser), then start the Studio.
RES="$(cd "$(dirname "$0")/../Resources" && pwd)"
DATA="$HOME/Library/Application Support/Pistachios Studio"
mkdir -p "$DATA/logs"
exec "$RES/app/runtime/python/bin/python3" "$RES/app/scripts/install_studio.py" --launch --payload "$RES/app" --home "$DATA" >>"$DATA/logs/launcher.log" 2>&1
"""


def build_app(dest: Path, arch: str) -> Path:
    app = dest / f"{APP}.app"
    res = app / "Contents" / "Resources"
    stage_app(res / "app")
    stage_runtime(res / "app", "macos", arch)
    (app / "Contents" / "MacOS").mkdir(parents=True)
    exe = app / "Contents" / "MacOS" / "studio"
    exe.write_text(LAUNCHER, encoding="utf-8")
    exe.chmod(0o755)
    has_icon = icon(res, "icns") is not None
    plist = {"CFBundleName": APP, "CFBundleDisplayName": APP, "CFBundleIdentifier": "com.pistachiosstudio.app", "CFBundleExecutable": "studio",
             "CFBundlePackageType": "APPL", "CFBundleShortVersionString": version(), "CFBundleVersion": version(), "LSUIElement": True,
             "LSMinimumSystemVersion": "11.0", **({"CFBundleIconFile": "applet"} if has_icon else {})}
    import plistlib
    with open(app / "Contents" / "Info.plist", "wb") as fh:
        plistlib.dump(plist, fh)
    sign = os.environ.get("MAC_SIGN_ID", "")                   # empty: a local (ad-hoc) signature; a Developer ID also gets the hardened runtime
    extra = ["--options", "runtime", "--timestamp"] if sign else []
    subprocess.run(["codesign", "--force", "--deep", *extra, "--sign", sign or "-", str(app)], check=False)
    return app


def build_macos(out: Path, arch: str) -> Path:
    with tempfile.TemporaryDirectory(prefix="studio-mac-") as t:
        vol = Path(t) / "vol"
        vol.mkdir()
        build_app(vol, arch)
        (vol / "Applications").symlink_to("/Applications")
        dmg = out / f"PistachiosStudio-{version()}-{arch}.dmg"
        dmg.unlink(missing_ok=True)
        subprocess.run(["hdiutil", "create", "-volname", APP, "-srcfolder", str(vol), "-ov", "-format", "UDZO", str(dmg)], check=True)
    if os.environ.get("MAC_SIGN_ID") and os.environ.get("MAC_NOTARY_PROFILE"):
        subprocess.run(["codesign", "--sign", os.environ["MAC_SIGN_ID"], str(dmg)], check=True)
        subprocess.run(["xcrun", "notarytool", "submit", str(dmg), "--keychain-profile", os.environ["MAC_NOTARY_PROFILE"], "--wait"], check=True)
        subprocess.run(["xcrun", "stapler", "staple", str(dmg)], check=True)
    say(f"built {dmg}")
    return dmg


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("target", choices=["windows", "macos", "stage"])
    ap.add_argument("--arch", default="")
    ap.add_argument("--out", type=Path, default=ROOT / "dist")
    a = ap.parse_args(argv)
    a.out = a.out.resolve()
    a.out.mkdir(parents=True, exist_ok=True)
    arch = a.arch or ("x86_64" if a.target == "windows" else ("arm64" if platform.machine() == "arm64" else "x86_64"))
    if a.target == "windows":
        build_windows(a.out, arch)
    elif a.target == "macos":
        build_macos(a.out, arch)
    else:
        stage_app(a.out / "app")                               # just the files (for checking what goes in)
    return 0


if __name__ == "__main__":
    sys.exit(main())
