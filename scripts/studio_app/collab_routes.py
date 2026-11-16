"""The Producer chat, notes on anything, and history and branches, for the page (milestone M12; Sections 3.4, 3.5, 6c).

GET  /api/producer?project=                       {messages, working: {running, step, crew: the last crew member at work}, stopped}
POST /api/producer {project, text, engine, claude_model}   the Producer's plan (a simple request is done at once)
POST /api/producer_decide {project, id, accept}   accept (do it) or dismiss a plan
POST /api/producer_stop {project}                 STOP the running job (remembered, to continue later)
POST /api/producer_add {project, text}            ADD INFORMATION: a note every crew role reads
POST /api/producer_continue {project}             CONTINUE the stopped job from the step it was on
GET  /api/notes?project=&status=                  POST /api/note_add {project, kind, ref, text, role?}
POST /api/note_reply {project, id, text}          POST /api/note_role {project, id, role}   POST /api/note_status {project, id, status}
GET  /api/history?project=                        POST /api/moment {project, label}
POST /api/moment_back {project, id}               POST /api/branch {project, id, name}      GET /api/branch_compare?a=&b=
"""
from __future__ import annotations

import json
from pathlib import Path

import crew
import history
import notes
import pictures
import producer
import production
from layout import project_dir

from .api import Request, route
from .common import PlanError
from .jobs import JOB
from .steps import engine_args


def _book(slug) -> Path:
    try:
        d = project_dir(str(slug or ""), "book")
    except ValueError as e:
        raise PlanError(str(e)) from e
    if not d.is_dir():
        raise PlanError("pick a book first")
    return d


def _stopped_file(d: Path) -> Path:
    return d / "chat" / "stopped.json"


def _chat_view(d: Path) -> dict:
    log = crew.log_tail(d, 1)
    stopped = None
    try:
        stopped = json.loads(_stopped_file(d).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        pass
    return {"messages": producer.load(d)[-200:], "working": {"running": JOB.running, "step": JOB.current, "crew": log[-1] if log else None},
            "stopped": {"label": stopped.get("label", ""), "steps": len(stopped.get("steps", []))} if stopped else None}


@route("GET", "/api/producer")
def _chat(r: Request):
    try:
        return _chat_view(_book(r.q("project")))
    except PlanError:
        return {"messages": [], "working": {"running": JOB.running, "step": JOB.current, "crew": None}, "stopped": None}


def _runner(d: Path, body: dict):
    def run_steps(names: list[str]) -> None:
        engine = str(body.get("engine") or "claude")
        steps = [{"label": producer.STEPS[n][1], "argv": ["python3", producer.STEPS[n][0], d.name]
                  + (["--engine", "fake"] if engine == "fake" else engine_args(body)) + (["--force"] if n in ("read_it_in", "shot_list") else []), "env": {}}
                 for n in names]
        JOB.start(steps, {"project": d.name}, queue=True)

    def regenerate(style: str, row: int) -> None:
        pictures.prepare_regenerate(d, style or production.load(d)["master"], row)
    return run_steps, regenerate


@route("POST", "/api/producer")
def _ask(r: Request):
    d = _book(r.body.get("project"))
    engine = str(r.body.get("engine") or "claude")
    if engine == "fake":
        ask = producer.fake_ask()
    else:
        import bookkit
        model = str(r.body.get("claude_model") or "") or None

        def ask(prompt, roles, step, validate):
            return bookkit.llm_json(prompt, crew.system(roles, d, step), model=model, engine=engine, validate=validate)
    try:
        m = producer.ask_producer(d, str(r.body.get("text", "")), ask)
        if m["plan"].get("simple"):
            producer.decide(d, m["id"], True, *_runner(d, r.body))
            producer.say(d, "Done.")
    except (producer.ChatError, pictures.PictureError, ValueError, RuntimeError) as e:
        raise PlanError(str(e)) from e
    return _chat_view(d)


@route("POST", "/api/producer_decide")
def _decide(r: Request):
    d = _book(r.body.get("project"))
    try:
        producer.decide(d, str(r.body.get("id", "")), bool(r.body.get("accept")), *_runner(d, r.body))
    except (producer.ChatError, pictures.PictureError, ValueError) as e:
        raise PlanError(str(e)) from e
    return _chat_view(d)


@route("POST", "/api/producer_stop")
def _stop(r: Request):
    d = _book(r.body.get("project"))
    if not JOB.running:
        raise PlanError("no job is running")
    state = dict(getattr(JOB, "state", {}) or {})
    state["label"] = JOB.current
    _stopped_file(d).parent.mkdir(parents=True, exist_ok=True)
    _stopped_file(d).write_text(json.dumps(state, ensure_ascii=False, default=str), encoding="utf-8")
    JOB.stop()
    producer.say(d, f"Stopped: {JOB.current or 'the job'}. Add information if you like, then press Continue.")
    return _chat_view(d)


@route("POST", "/api/producer_add")
def _add(r: Request):
    d = _book(r.body.get("project"))
    try:
        producer.add_information(d, str(r.body.get("text", "")))
    except notes.NoteError as e:
        raise PlanError(str(e)) from e
    return _chat_view(d)


@route("POST", "/api/producer_continue")
def _continue(r: Request):
    d = _book(r.body.get("project"))
    try:
        state = json.loads(_stopped_file(d).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        raise PlanError("nothing was stopped from the chat") from None
    if not state.get("steps"):
        raise PlanError("the stopped job has no steps to carry on")
    JOB.resume(state, redo_step=True)
    _stopped_file(d).unlink(missing_ok=True)
    producer.say(d, "Carrying on from where it stopped.")
    return _chat_view(d)


# ---------------------------------------------------------------------------------------------- notes
@route("GET", "/api/notes")
def _notes(r: Request):
    try:
        d = _book(r.q("project"))
    except PlanError:
        return {"notes": [], "kinds": notes.KINDS, "roles": crew.roles()}
    st = r.q("status")
    return {"notes": [n for n in notes.load(d) if not st or n["status"] == st], "kinds": notes.KINDS, "roles": crew.roles()}


def _note_op(r: Request, fn) -> dict:
    d = _book(r.body.get("project"))
    try:
        fn(d)
    except notes.NoteError as e:
        raise PlanError(str(e)) from e
    return {"notes": notes.load(d), "kinds": notes.KINDS, "roles": crew.roles()}


@route("POST", "/api/note_add")
def _note_add(r: Request):
    return _note_op(r, lambda d: notes.add(d, str(r.body.get("kind", "")), str(r.body.get("ref", "")), str(r.body.get("text", "")), str(r.body.get("role") or "")))


@route("POST", "/api/note_reply")
def _note_reply(r: Request):
    return _note_op(r, lambda d: notes.reply(d, str(r.body.get("id", "")), str(r.body.get("text", ""))))


@route("POST", "/api/note_role")
def _note_role(r: Request):
    return _note_op(r, lambda d: notes.set_role(d, str(r.body.get("id", "")), str(r.body.get("role", ""))))


@route("POST", "/api/note_status")
def _note_status(r: Request):
    return _note_op(r, lambda d: notes.set_status(d, str(r.body.get("id", "")), str(r.body.get("status", ""))))


# ---------------------------------------------------------------------------------------------- history and branches
def _moments(d: Path) -> dict:
    ms = history.moments(d)
    try:
        br = json.loads((d / "branch.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        br = None
    return {"moments": [{k: m[k] for k in ("id", "at", "label", "kind")} | {"records": len(m["files"]), "pictures": len(m["media"])} for m in reversed(ms)],
            "branch_of": br}


@route("GET", "/api/history")
def _history(r: Request):
    try:
        return _moments(_book(r.q("project")))
    except PlanError:
        return {"moments": [], "branch_of": None}


@route("POST", "/api/moment")
def _moment(r: Request):
    d = _book(r.body.get("project"))
    history.create(d, str(r.body.get("label") or "saved by hand"), "manual")
    return _moments(d)


@route("POST", "/api/moment_back")
def _back(r: Request):
    d = _book(r.body.get("project"))
    if JOB.running:
        raise PlanError("a job is running: wait for it to finish (or stop it) first")
    try:
        out = history.back_to(d, str(r.body.get("id", "")))
    except (history.HistoryError, FileNotFoundError) as e:
        raise PlanError(str(e)) from e
    return {**_moments(d), **out}


@route("POST", "/api/branch")
def _branch(r: Request):
    d = _book(r.body.get("project"))
    try:
        new = history.branch(d, str(r.body.get("id", "")), str(r.body.get("name", "")))
    except (history.HistoryError, FileNotFoundError) as e:
        raise PlanError(str(e)) from e
    return {**_moments(d), "branch": new.name}


@route("GET", "/api/branch_compare")
def _compare(r: Request):
    return history.compare(_book(r.q("a")), _book(r.q("b")))
