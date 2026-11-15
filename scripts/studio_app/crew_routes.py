"""The crew, the project rules and the format recipe of a book, for the page.

GET  /api/crew?project=            {roles: [{key, title}], log: [last crew-log lines]}
GET  /api/recipes?project=         {recipes: [{name, title, about, aspect, target_minutes, products, series}], chosen: name | ""}
POST /api/recipe {project, name}   choose the book's recipe ("" = none: the Studio's normal film path)
GET  /api/project_rules?project=   {body, rev, updated}
POST /api/project_rules {project, body, rev}   save; 409 when the rules changed since `rev` was read (the page shows both versions)
"""
from pathlib import Path

import crew
from bookkit import SLUG_RE
from layout import project_dir as pdir

from .api import Request, route
from .common import PlanError


def _book(slug: str) -> Path:
    d = pdir(slug) if SLUG_RE.match(slug or "") else None
    if not d or not d.is_dir():
        raise PlanError("pick a book first")
    return d


@route("GET", "/api/crew")
def _crew(r: Request):
    out: dict = {"roles": [{"key": k, "title": crew.role_title(k)} for k in crew.roles()]}
    if r.q("project"):
        out["log"] = crew.log_tail(_book(r.q("project")))
    return out


@route("GET", "/api/recipes")
def _recipes(r: Request):
    keep = ("name", "title", "about", "aspect", "target_minutes", "products", "series")
    out: dict = {"recipes": [{k: d.get(k) for k in keep} for d in crew.recipes()]}
    if r.q("project"):
        out["chosen"] = crew.project_recipe(_book(r.q("project")))
    return out


@route("POST", "/api/recipe")
def _recipe(r: Request):
    name = str(r.body.get("name") or "")
    try:
        return crew.set_recipe(_book(str(r.body.get("project", ""))), name)
    except ValueError as e:
        raise PlanError(str(e)) from None


@route("GET", "/api/project_rules")
def _rules(r: Request):
    return crew.read_rules(_book(r.q("project")))


@route("POST", "/api/project_rules")
def _rules_save(r: Request):
    d = _book(str(r.body.get("project", "")))
    try:
        rev = int(r.body.get("rev", -1))
    except (TypeError, ValueError):
        raise PlanError("rev must be a number") from None
    try:
        return crew.write_rules(d, r.body.get("body", ""), rev)
    except crew.RevConflict as e:
        return 409, {"error": str(e), "current": crew.read_rules(d)}      # the page offers: keep mine / keep theirs
    except ValueError as e:
        raise PlanError(str(e)) from None
