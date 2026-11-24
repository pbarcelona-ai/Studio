"""A small route table for the JSON API: `@route("GET", "/api/x")` registers a function that gets a Request and returns the JSON
answer (a dict/list, or `(status, dict)`). The HTTP handler (handler.py) only does transport, authentication and error mapping."""
import re
import subprocess
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import unquote

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
    params: dict[str, str] = field(default_factory=dict)
    path: str = ""

    def q(self, name: str, default: str = "") -> str:
        """One query-string value (the first), or the default."""
        return self.query.get(name, [default])[0]

    def p(self, name: str, default: str = "") -> str:
        """One captured URL path parameter, or the default."""
        return self.params.get(name, default)


Route = Callable[[Request], Any]
ROUTES: dict[str, dict[str, Route]] = {"GET": {}, "POST": {}}
PATTERN_ROUTES: dict[str, list[tuple[str, re.Pattern[str], Route]]] = {"GET": [], "POST": []}
_PARAM_RE = re.compile(r"<([A-Za-z_][A-Za-z0-9_]*)>")
_BAD_ENCODED_SEG_RE = re.compile(r"%(?:2f|5c|00)", re.IGNORECASE)


def _normalize_path(path: str) -> str | None:
    if not path.startswith("/"):
        return None
    decoded_segments: list[str] = []
    for seg in path.split("/"):
        if _BAD_ENCODED_SEG_RE.search(seg):
            return None
        decoded = unquote(seg)
        if "/" in decoded or "\\" in decoded or "\x00" in decoded or decoded in (".", ".."):
            return None
        decoded_segments.append(decoded)
    return "/".join(decoded_segments)


def _compile_pattern(path: str) -> tuple[str, re.Pattern[str]]:
    parts: list[str] = []
    norm_parts: list[str] = []
    seen: set[str] = set()
    pos = 0
    for m in _PARAM_RE.finditer(path):
        name = m.group(1)
        if name in seen:
            raise RuntimeError(f"duplicate route parameter {name!r} in {path}")
        seen.add(name)
        lit = path[pos:m.start()]
        parts.append(re.escape(lit))
        norm_parts.append(lit)
        parts.append(f"(?P<{name}>[^/]+)")
        norm_parts.append("<>")
        pos = m.end()
    tail = path[pos:]
    parts.append(re.escape(tail))
    norm_parts.append(tail)
    return "".join(norm_parts), re.compile("^" + "".join(parts) + "$")


def route(method: str, path: str) -> Callable[[Route], Route]:
    def deco(fn: Route) -> Route:
        if method not in ROUTES:
            raise ValueError(f"unsupported HTTP method: {method}")
        if _PARAM_RE.search(path):
            norm, compiled = _compile_pattern(path)
            if any(existing_norm == norm for existing_norm, _, _ in PATTERN_ROUTES[method]):
                raise RuntimeError(f"route registered twice: {method} {path}")
            PATTERN_ROUTES[method].append((norm, compiled, fn))
        else:
            if path in ROUTES[method]:
                raise RuntimeError(f"route registered twice: {method} {path}")
            ROUTES[method][path] = fn
        return fn
    return deco


def resolve(method: str, path: str) -> tuple[Route | None, dict[str, str]]:
    """Resolve an exact or parameterized route for (method, path)."""
    norm = _normalize_path(path)
    if norm is None:
        return None, {}
    fn = ROUTES.get(method, {}).get(norm)
    if fn is not None:
        return fn, {}
    for _, pattern, pfn in PATTERN_ROUTES.get(method, ()):
        m = pattern.fullmatch(norm)
        if m is not None:
            return pfn, m.groupdict()
    return None, {}


def has_route(method: str, path: str) -> bool:
    """Return True if an exact or parameterized route matches (method, path)."""
    return resolve(method, path)[0] is not None


def dispatch(method: str, path: str, req: Request) -> tuple[int, Any]:
    """Run the route for (method, path). Returns (status, json-able). Never raises."""
    fn, params = resolve(method, path)
    if fn is None:
        return 404, {"error": "not found"}
    req.path = path
    req.params = params
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
