"""Work left running by an earlier session of the Studio: a job it started (logs/jobs/current.json), Studio programs still running on this
computer, and Kaggle notebooks those jobs pushed. The page shows them as a warning when it opens, and offers to follow, carry on or stop.

GET  /api/sessions[?kernels=1]      {job: {...} | null, following: bool, processes: [...], kernels: [...]}
POST /api/sessions {action}         continue | redo | discard | stop (pid) | follow
"""
import os
import re
import time
from pathlib import Path

from .common import PlanError
from .config import ROOT
from . import procs
from .jobs import JOB, exit_code, kill_group, pid_alive, read_state, write_state
from .log import get_logger

log = get_logger("resume")
# Studio programs that use a GPU or an AI model (and the few others a job runs), as they appear in `ps`
PROGRAMS = re.compile(r"(run_kaggle_model\.(?:sh|py)|run_colab_model\.(?:sh|py)|run_hf_space\.(?:sh|py)|fetch_kaggle_run\.(?:sh|py)|run_local_model\.py|make_video\.py|make_audio\.py|make_keyframes\w*\.py|"
                      r"local_audio\.py|face_check\.py|book_adapt\.py|book_screenplay\.py|read_it_in\.py|continuity_book\.py|shot_list\.py|book_continuity\.py|book_write\.py|book_ingest\.py|book_build\.py|"
                      r"mix_film\.py|export_film\.py|regress_kaggle\.py)")
AI = ("book_adapt", "book_screenplay", "read_it_in", "continuity_book", "shot_list", "book_continuity", "book_write")
GPU = ("run_kaggle_model", "run_colab_model", "run_hf_space", "run_local_model", "make_video", "make_audio", "make_keyframes", "local_audio", "face_check", "regress_kaggle")
KERNEL = re.compile(r"(?:pushing kernel|kernel pushed: https://www\.kaggle\.com/code/)\s*([A-Za-z0-9_-]+/[A-Za-z0-9_.-]+)")
TAIL = 25


def kind_of(command: str) -> str:
    """'GPU', 'AI' or 'other', for the warning's wording."""
    if any(k in command for k in GPU):
        return "GPU"
    if any(k in command for k in AI):
        return "AI"
    return "other"


def _ps() -> list[tuple[int, int, str, str]]:
    """(pid, process group, running time, command) of every process of this user."""
    return procs.processes()


def _cwd(pid: int) -> str:
    return procs.cwd_of(pid)


def studio_processes(exclude_groups: set[int] | None = None) -> list[dict]:
    """Studio programs running on this computer, one per process group (a step and what it started): those whose folder is the Studio's."""
    root, exclude_groups = str(ROOT.resolve()), exclude_groups or set()
    groups: dict[int, dict] = {}
    for pid, pgid, etime, cmd in _ps():
        if pgid in exclude_groups or not PROGRAMS.search(cmd):
            continue
        if str(ROOT) not in cmd and not _cwd(pid).startswith(root):
            continue
        g = groups.get(pgid)
        if g is None or len(cmd) > len(g["command"]):          # the most telling command of the group
            groups[pgid] = {"pid": pid, "group": pgid, "running_for": etime, "command": cmd[:300], "kind": kind_of(cmd)}
    return sorted(groups.values(), key=lambda g: g["pid"])


def _tail(path: str, n: int = TAIL) -> list[str]:
    try:
        return Path(path).read_text(errors="replace").splitlines()[-n:]
    except OSError:
        return []


def kernels_of(state: dict) -> list[str]:
    """Kaggle notebooks the job's steps pushed (from their logs), newest last."""
    refs: list[str] = []
    d = Path(state.get("dir") or "")
    for f in sorted(d.glob("step-*.log")) if d.is_dir() else []:
        for m in KERNEL.finditer(f.read_text(errors="replace")):
            if m.group(1) not in refs:
                refs.append(m.group(1))
    return refs


def earlier_job() -> dict | None:
    """The job of an earlier session that did not finish, described for the page, or None."""
    st = read_state()
    if not st or st.get("status") != "running" or JOB.running and JOB.state.get("id") == st.get("id"):
        return None
    pid = st.get("step_pid")
    alive = pid_alive(pid)
    done_code = exit_code(st.get("exit", "")) if st.get("exit") else None
    steps = st.get("steps") or []
    idx = int(st.get("index", 0))
    return {"id": st.get("id"), "project": st.get("project", ""), "started": st.get("started", ""), "label": st.get("label", ""),
            "step": idx + 1, "steps": len(steps), "still_running": alive, "step_exit": done_code,
            "left": [s.get("label", "") for s in steps[idx + 1:]], "kind": kind_of(" ".join(" ".join(s.get("argv", [])) for s in steps[idx:idx + 1])),
            "log": _tail(st.get("log", "")), "kernels": kernels_of(st)}


def on_startup() -> None:
    """When the Studio starts: if the last session's job is still running a step, follow it (and carry on with the rest of the job)."""
    st = read_state()
    if st.get("status") == "running" and pid_alive(st.get("step_pid")) and st.get("log") and st.get("exit"):
        if JOB.attach(st):
            log.info("following a step left running by the last session (pid %s)", st.get("step_pid"))


def sessions_data(with_kernels: bool = False) -> dict:
    following = bool(JOB.running and JOB.attached_pid)
    mine = {JOB.attached_pid} if JOB.attached_pid else set()
    if JOB.proc is not None and JOB.proc.poll() is None:
        mine.add(JOB.proc.pid)
    job = earlier_job()
    if job and job["still_running"] and JOB.state.get("step_pid"):
        mine.add(JOB.state["step_pid"])
    procs = studio_processes({p for p in mine if p})
    kernels = []
    refs = (job or {}).get("kernels", []) or (kernels_of(JOB.state) if following else [])
    if with_kernels and refs:
        from .kaggle_runs import kernel_status
        for ref in refs[-3:]:
            try:
                kernels.append(kernel_status(ref))
            except PlanError as e:
                kernels.append({"ref": ref, "status": "UNKNOWN", "raw": str(e)})
    else:
        kernels = [{"ref": r, "status": None} for r in refs[-3:]]
    return {"job": job, "following": following, "following_label": JOB.current if following else "", "processes": procs, "kernels": kernels,
            "checked": time.strftime("%H:%M:%S")}


def sessions_action(b: dict) -> dict:
    action = b.get("action")
    st = read_state()
    if action in ("continue", "redo"):
        job = earlier_job()
        if not job:
            raise PlanError("there is no earlier job to carry on with")
        if job["still_running"]:
            if not JOB.attach(st):
                raise PlanError("a job is already running")
        else:
            JOB.resume(st, redo_step=action == "redo" or job["step_exit"] != 0)      # a step that failed or was cut off runs again
    elif action == "discard":
        if st.get("status") == "running":
            st["status"] = "discarded"
            write_state(st)
    elif action == "stop":
        pid = b.get("pid")
        known = {p["pid"] for p in studio_processes()} | ({st.get("step_pid")} if st.get("status") == "running" else set())
        if not isinstance(pid, int) or pid not in known:
            raise PlanError("that is not a Studio program that is running")
        kill_group(pid)
        if st.get("step_pid") == pid and st.get("status") == "running":
            st["status"] = "stopped"
            write_state(st)
    else:
        raise PlanError("unknown action")
    return sessions_data()


def busy_elsewhere() -> str:
    """A reason not to start a new job: a GPU or AI program from an earlier session still runs on this computer ('' when there is none)."""
    if JOB.running or os.environ.get("STUDIO_NO_BUSY_CHECK"):
        return ""
    others = [p for p in studio_processes() if p["kind"] in ("GPU", "AI")]
    if not others:
        return ""
    p = others[0]
    return (f"Another run from an earlier session is still working on this computer ({p['kind']}, process {p['pid']}, running for {p['running_for']}). "
            "Wait for it, or stop it from the warning at the top of the page, before starting a new one.")
