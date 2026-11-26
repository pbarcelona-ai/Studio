"""Process control that works the same on macOS, Linux and Windows: start a step in its own group, stop that group, check a process is alive,
list this user's processes, open a folder in the file manager.

  POSIX    a step starts in its own session (start_new_session); stopping it is SIGTERM to the group, then SIGKILL.
  Windows  a step starts in its own process group (CREATE_NEW_PROCESS_GROUP); stopping it is `taskkill /T` (the step and what it started),
           then `taskkill /T /F`. os.kill(pid, 0) would END the process on Windows, so pid_alive asks the system instead.
"""
from __future__ import annotations

import json
import os
import shutil
import signal
import subprocess
import sys
from pathlib import Path

IS_WIN = sys.platform == "win32"          # mypy checks each branch for the system it is told (sys.platform guards)


def group_kwargs() -> dict:
    """Popen keyword arguments that put a new process in its own group, so it and everything it starts can be stopped together."""
    if sys.platform == "win32":
        return {"creationflags": getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0x200)}
    return {"start_new_session": True}


def pid_alive(pid) -> bool:
    if not isinstance(pid, int) or isinstance(pid, bool) or pid <= 1:
        return False
    if sys.platform == "win32":
        return _win_alive(pid)
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False
    return True


def _win_alive(pid: int) -> bool:
    if sys.platform != "win32":
        return False
    import ctypes                                         # Windows only; kept here so POSIX never loads it
    k32 = ctypes.windll.kernel32
    h = k32.OpenProcess(0x1000, False, pid)               # PROCESS_QUERY_LIMITED_INFORMATION
    if not h:
        return False
    try:
        code = ctypes.c_ulong()
        return bool(k32.GetExitCodeProcess(h, ctypes.byref(code))) and code.value == 259     # STILL_ACTIVE
    finally:
        k32.CloseHandle(h)


def process_start_id(pid: int) -> str:
    """Stable process start-time token for `pid` to prevent PID-reuse false attachment/termination."""
    if not isinstance(pid, int) or isinstance(pid, bool) or pid <= 1:
        return ""
    if sys.platform == "win32":
        import ctypes

        class _FILETIME(ctypes.Structure):
            _fields_ = [("dwLowDateTime", ctypes.c_uint32), ("dwHighDateTime", ctypes.c_uint32)]

        k32 = ctypes.windll.kernel32
        h = k32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
        if not h:
            return ""
        try:
            ct, et, kt, ut = _FILETIME(), _FILETIME(), _FILETIME(), _FILETIME()
            if k32.GetProcessTimes(h, ctypes.byref(ct), ctypes.byref(et), ctypes.byref(kt), ctypes.byref(ut)):
                return f"win:{ct.dwHighDateTime}:{ct.dwLowDateTime}"
        finally:
            k32.CloseHandle(h)
        return ""
    proc_stat = Path(f"/proc/{pid}/stat")
    if proc_stat.is_file():
        try:
            raw = proc_stat.read_text(encoding="utf-8", errors="replace")
            after_comm = raw.rsplit(")", 1)[-1].split()
            if len(after_comm) > 19:
                return f"linux:{after_comm[19]}"
        except OSError:
            return ""
    try:
        out = subprocess.run(["ps", "-o", "lstart=", "-p", str(pid)], capture_output=True, text=True, timeout=5).stdout.strip()
        return f"ps:{out}" if out else ""
    except (OSError, subprocess.SubprocessError):
        return ""


def pid_matches(pid, expected_start_id: str = "") -> bool:
    """True when `pid` is alive AND (when `expected_start_id` is recorded) still has the exact same start identity."""
    if not pid_alive(pid):
        return False
    exp = str(expected_start_id or "").strip()
    if not exp:
        return True
    cur = process_start_id(int(pid))
    return bool(cur) and cur == exp


def group_of(pid: int) -> int:
    """The process group to stop for pid (on Windows the pid itself: taskkill /T follows its children)."""
    if sys.platform == "win32":
        return pid
    return os.getpgid(pid)


def stop_group(pid: int, hard: bool = False) -> bool:
    """Ask the group of pid to stop (hard: make it stop). False when there was nothing to stop."""
    if sys.platform == "win32":
        argv = ["taskkill", "/PID", str(pid), "/T"] + (["/F"] if hard else [])
        try:
            return subprocess.run(argv, capture_output=True, timeout=30).returncode == 0
        except (OSError, subprocess.SubprocessError):
            return False
    try:
        os.killpg(os.getpgid(pid), signal.SIGKILL if hard else signal.SIGTERM)
        return True
    except (ProcessLookupError, PermissionError, OSError):
        return False


def stop_known_group(pgid: int, hard: bool = False) -> None:
    """Like stop_group, for a group found earlier (POSIX: the group id; Windows: the leading pid)."""
    if sys.platform == "win32":
        stop_group(pgid, hard)
        return
    try:
        os.killpg(pgid, signal.SIGKILL if hard else signal.SIGTERM)
    except (ProcessLookupError, PermissionError, OSError):
        pass


def processes() -> list[tuple[int, int, str, str]]:
    """(pid, group, running time, command line) of this user's processes. Empty when the system will not say."""
    if sys.platform == "win32":
        return _win_processes()
    try:
        out = subprocess.run(["ps", "-ww", "-x", "-o", "pid=,pgid=,etime=,command="], capture_output=True, text=True, timeout=10).stdout
    except (OSError, subprocess.SubprocessError):
        return []
    rows = []
    for line in out.splitlines():
        parts = line.split(None, 3)
        if len(parts) == 4 and parts[0].isdigit() and parts[1].isdigit():
            rows.append((int(parts[0]), int(parts[1]), parts[2], parts[3]))
    return rows


def _win_processes() -> list[tuple[int, int, str, str]]:
    ps = shutil.which("powershell") or shutil.which("pwsh")
    if not ps:
        return []
    cmd = "Get-CimInstance Win32_Process | Select-Object ProcessId,CommandLine | ConvertTo-Json -Compress"
    try:
        out = subprocess.run([ps, "-NoProfile", "-NonInteractive", "-Command", cmd], capture_output=True, text=True, timeout=30).stdout
        data = json.loads(out or "[]")
    except (OSError, subprocess.SubprocessError, ValueError):
        return []
    rows = []
    for d in data if isinstance(data, list) else [data]:
        pid, line = d.get("ProcessId"), d.get("CommandLine") or ""
        if isinstance(pid, int) and line:
            rows.append((pid, pid, "", line))
    return rows


def cwd_of(pid: int) -> str:
    """The working folder of pid, or '' when it cannot be found (always '' on Windows: the command line names the Studio's folder)."""
    if sys.platform == "win32":
        return ""
    proc_cwd = Path(f"/proc/{pid}/cwd")                    # Linux: no lsof needed
    if proc_cwd.exists():
        try:
            return str(proc_cwd.readlink())
        except OSError:
            return ""
    if not shutil.which("lsof"):
        return ""
    try:
        out = subprocess.run(["lsof", "-a", "-p", str(pid), "-d", "cwd", "-Fn"], capture_output=True, text=True, timeout=10).stdout
    except (OSError, subprocess.SubprocessError):
        return ""
    return next((ln[1:] for ln in out.splitlines() if ln.startswith("n")), "")


def open_folder(folder: Path) -> bool:
    """Show a folder in Finder, Explorer or the file manager. False when this computer has no way to."""
    if sys.platform == "win32":
        os.startfile(str(folder))                         # noqa: S606  (Windows: the folder only, no shell)
        return True
    opener = "open" if sys.platform == "darwin" else "xdg-open"
    if not shutil.which(opener):
        return False
    subprocess.run([opener, str(folder)], check=True, timeout=10)
    return True


def venv_bin(root: Path) -> Path:
    """Where a virtual environment keeps its programs: .venv/bin, or .venv\\Scripts on Windows."""
    return root / ".venv" / ("Scripts" if IS_WIN else "bin")
