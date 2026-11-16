"""The style system for the page (milestone M5): style cards, translations, prompt preview, look development and its review gate.

GET  /api/styles?project=                                   {styles: [{id, name, about, master, card, translations, lookdev}], gate}
POST /api/styles_write {project, style?, engine, claude_model}   write the cards + translations + look-development prompts (a job: styles.py)
POST /api/style_card_edit {project, style, fields}
POST /api/style_translation_edit {project, style, kind, name, text}
GET  /api/prompt_preview?project=&style=&scene=&shot=       the assembled prompt of one shot in one style, part by part (Section 7.3)
POST /api/lookdev_render {project, style, service, gpu, kaggle_user, image_model}   render the look-development pictures (a job)
POST /api/lookdev_pick {project, style, key, row}            the best of the 4
POST /api/lookdev_approve {project}
"""
from __future__ import annotations

import re
from pathlib import Path

import continuity_book
import gates
import shot_list
import styles
from layout import project_dir

from .api import Request, route
from .common import PlanError
from .config import GPUS, IMAGE_MODELS
from .gpus import check_models, gpu_blocker
from .jobs import JOB
from .steps import engine_args, make_runner


def _book(slug) -> Path:
    try:
        d = project_dir(str(slug or ""), "book")
    except ValueError as e:
        raise PlanError(str(e)) from e
    if not d.is_dir():
        raise PlanError("pick a book first")
    return d


def _wrap(fn):
    try:
        return fn()
    except (styles.StyleError, ValueError) as e:
        raise PlanError(str(e)) from e


@route("GET", "/api/styles")
def _get(r: Request):
    try:
        d = _book(r.q("project"))
    except PlanError:
        return {"styles": [], "gate": {"approved": False, "approved_at": "", "changed_since": False}}
    return styles.summary(d)


@route("POST", "/api/styles_write")
def _write(r: Request):
    d = _book(r.body.get("project"))
    book = continuity_book.load(d)
    if not gates.approved(d, "continuity", [book.get("characters", []), book.get("locations", []), book.get("props", [])]):
        raise PlanError("approve the continuity book first: every style translates it")
    sid = str(r.body.get("style") or "")
    if sid:
        _wrap(lambda: styles.style_of(d, sid))
    engine = str(r.body.get("engine") or "claude")
    argv = ["python3", "styles.py", d.name] + (["--style", sid] if sid else []) + (["--engine", "fake"] if engine == "fake" else engine_args(r.body))
    ahead = JOB.start([{"label": "Write the style cards and translations", "argv": argv, "env": {}}], r.body, queue=bool(r.body.get("queue")))
    return {"started": ahead == 0, "ahead": ahead}


@route("POST", "/api/style_card_edit")
def _card_edit(r: Request):
    d = _book(r.body.get("project"))
    fields = r.body.get("fields")
    if not isinstance(fields, dict):
        raise PlanError("fields must be an object")
    _wrap(lambda: styles.edit_card(d, str(r.body.get("style", "")), fields))
    return styles.summary(d)


@route("POST", "/api/style_translation_edit")
def _tr_edit(r: Request):
    d = _book(r.body.get("project"))
    _wrap(lambda: styles.edit_translation(d, str(r.body.get("style", "")), str(r.body.get("kind", "")), str(r.body.get("name", "")), str(r.body.get("text", ""))))
    return styles.summary(d)


@route("GET", "/api/prompt_preview")
def _preview(r: Request):
    d = _book(r.q("project"))
    sid, scene = r.q("style"), r.q("scene")
    try:
        n = int(r.q("shot", "1"))
    except ValueError as e:
        raise PlanError("shot is a number") from e
    sl = shot_list.load(d)
    sc = next((s for s in sl.get("scenes", []) if s["id"] == scene), None)
    if sc is None or not 1 <= n <= len(sc["shots"]):
        raise PlanError("no such scene or shot in the shot list")
    loc = re.sub(r"^(?:INT|EXT|I/E)[\./\s]+", "", sc["heading"]).split(" - ")[0]
    return _wrap(lambda: styles.assemble(sc["shots"][n - 1], loc, styles.card_of(d, sid), styles.translations_of(d, sid), continuity_book.load(d)))


@route("POST", "/api/lookdev_render")
def _render(r: Request):
    d = _book(r.body.get("project"))
    sid = str(r.body.get("style", ""))
    st = _wrap(lambda: styles.lookdev_status(d, sid))
    if not st["rows"]:
        raise PlanError("write the style card and translations first (they make the look-development prompts)")
    service, gpu, model = r.body.get("service"), r.body.get("gpu"), str(r.body.get("image_model", ""))
    if service not in GPUS or gpu not in [g for g, _ in GPUS[service]]:
        raise PlanError("choose where the models run, and the GPU")
    if gpu_blocker(service, gpu):
        raise PlanError(gpu_blocker(service, gpu))
    if model not in IMAGE_MODELS:
        raise PlanError("choose the image model")
    check_models(service, gpu, [model])
    user = str(r.body.get("kaggle_user") or "").strip()
    if service == "kaggle" and not re.fullmatch(r"[A-Za-z0-9_-]{2,40}", user):
        raise PlanError("enter your Kaggle username (letters, digits, - and _)")
    argv, env = make_runner(service, gpu, user, st["set"])(f"image_{model}", 1, st["rows"], "all_images.csv")
    ahead = JOB.start([{"label": f"Render the {sid} look development ({st['rows']} pictures)", "argv": argv, "env": env}], r.body, queue=bool(r.body.get("queue")))
    return {"started": ahead == 0, "ahead": ahead, "set": st["set"]}


@route("POST", "/api/lookdev_pick")
def _pick(r: Request):
    d = _book(r.body.get("project"))
    try:
        row = int(r.body.get("row", 0))
    except (TypeError, ValueError) as e:
        raise PlanError("row is a number") from e
    _wrap(lambda: styles.pick(d, str(r.body.get("style", "")), str(r.body.get("key", "")), row))
    return styles.summary(d)


@route("POST", "/api/lookdev_approve")
def _approve(r: Request):
    d = _book(r.body.get("project"))
    s = styles.summary(d)
    missing = [x["name"] for x in s["styles"] if not x["card"] or not x["translations"]]
    if missing:
        raise PlanError(f"these styles have no card or translations yet: {', '.join(missing)}")
    unpicked = [f"{x['name']}: {i['name']} {i['view']}" for x in s["styles"] for i in x["lookdev"]["items"] if i["pick"] is None]
    if unpicked:
        raise PlanError(f"pick the best picture for every sheet first ({len(unpicked)} left, e.g. {unpicked[0]})")
    gates.approve(d, "lookdev", styles.gate_data(d))
    return styles.summary(d)
