"""A small route table for the JSON API: `@route("GET", "/api/x")` registers a function that gets a Request and returns the JSON
answer (a dict/list, or `(status, dict)`). The HTTP handler (handler.py) only does transport, authentication and error mapping."""
import subprocess
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from .common import PlanError
from .log import get_logger

log = get_logger("api")


class HttpError(Exception):
    """Raise from a route to answer with this status and {"error": message}."""

    def __init__(self, code: int, message: str):
        super().__init__(message)
        self.code, self.message = code, message


@dataclass
class Request:
    query: dict[str, list[str]] = field(default_factory=dict)
    body: dict[str, Any] = field(default_factory=dict)

    def q(self, name: str, default: str = "") -> str:
        """One query-string value (the first), or the default."""
        return self.query.get(name, [default])[0]


Route = Callable[[Request], Any]
ROUTES: dict[str, dict[str, Route]] = {"GET": {}, "POST": {}}


def route(method: str, path: str) -> Callable[[Route], Route]:
    def deco(fn: Route) -> Route:
        if path in ROUTES[method]:
            raise RuntimeError(f"route registered twice: {method} {path}")
        ROUTES[method][path] = fn
        return fn
    return deco


def dispatch(method: str, path: str, req: Request) -> tuple[int, Any]:
    """Run the route for (method, path). Returns (status, json-able). Never raises."""
    fn = ROUTES.get(method, {}).get(path)
    if fn is None:
        return 404, {"error": "not found"}
    try:
        out = fn(req)
    except HttpError as e:
        return e.code, {"error": e.message}
    except PlanError as e:
        return 400, {"error": str(e)}
    except subprocess.TimeoutExpired:
        return 400, {"error": "Kaggle did not answer in time; try again"}
    except (ValueError, KeyError, TypeError) as e:
        return 400, {"error": f"bad request: {e}"}
    except Exception:                                           # a bug: log it with its traceback, tell the page nothing internal
        log.exception("unhandled error in %s %s", method, path)
        return 500, {"error": "internal error (see studio.log)"}
    if isinstance(out, tuple) and len(out) == 2 and isinstance(out[0], int):
        return out
    return 200, out
