#!/usr/bin/env python3
"""The Studio as an MCP server (BOOK_TO_SCREEN_BUILD.md Section 11, milestone M15): the automation API's actions as MCP tools, so an AI
assistant can drive the Studio. It speaks MCP over stdio (JSON-RPC 2.0, one message per line) and calls the running Studio's API with the
SAME token and the same checks as the page:

  STUDIO_URL=http://127.0.0.1:8765  STUDIO_TOKEN=<the token in the Studio's link>  python scripts/mcp_server.py

Tools: create_project, add_source, run_autopilot, stop, chat, project_status, list_exports, add_style, branch, queue.
Standard library only; works on Windows and macOS.
"""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from typing import Any

PROTOCOL = "2025-06-18"
TOOLS: dict[str, dict[str, Any]] = {
    "create_project": {"description": "Create a book from sources (ideas or web addresses), with a format recipe, products, styles and settings; "
                                      "mode 'autopilot' also starts making it.",
                       "method": "POST", "path": "/api/v1/projects",
                       "properties": {"name": {"type": "string"}, "sources": {"type": "array", "items": {"type": "object"}}, "recipe": {"type": "string"},
                                      "products": {"type": "array", "items": {"type": "string"}}, "styles": {"type": "array", "items": {"type": "string"}},
                                      "settings": {"type": "object"}, "mode": {"type": "string", "enum": ["autopilot", "review"]},
                                      "stop_at": {"type": "array", "items": {"type": "string"}}, "rights": {"type": "boolean"}}, "required": ["name", "rights"]},
    "add_source": {"description": "Add an idea (text) or a web page (url) to a book.", "method": "POST", "path": "/api/v1/sources",
                   "properties": {"project": {"type": "string"}, "kind": {"type": "string", "enum": ["idea", "url"]}, "text": {"type": "string"},
                                  "url": {"type": "string"}, "rights": {"type": "boolean"}}, "required": ["project", "kind", "rights"]},
    "run_autopilot": {"description": "Start or continue Autopilot on a book (it stops at the review gates in stop_at).", "method": "POST", "path": "/api/v1/run",
                      "properties": {"project": {"type": "string"}, "stop_at": {"type": "array", "items": {"type": "string"}}, "service": {"type": "string"},
                                     "gpu": {"type": "string"}, "kaggle_user": {"type": "string"}, "engine": {"type": "string"}}, "required": ["project"]},
    "stop": {"description": "Stop the running job.", "method": "POST", "path": "/api/v1/stop", "properties": {"project": {"type": "string"}}, "required": ["project"]},
    "chat": {"description": "Send a message to the Producer (it answers with a plan to accept).", "method": "POST", "path": "/api/v1/chat",
             "properties": {"project": {"type": "string"}, "text": {"type": "string"}, "engine": {"type": "string"}}, "required": ["project", "text"]},
    "project_status": {"description": "Every step's state, the job, and the cost (estimate vs. actual).", "method": "GET", "path": "/api/v1/project",
                       "properties": {"project": {"type": "string"}}, "required": ["project"]},
    "list_exports": {"description": "The finished downloads of a book.", "method": "GET", "path": "/api/v1/exports",
                     "properties": {"project": {"type": "string"}}, "required": ["project"]},
    "add_style": {"description": "Add a style (a preset id, or a custom style with text) and write its style card.", "method": "POST", "path": "/api/v1/styles",
                  "properties": {"project": {"type": "string"}, "style": {"type": "string"}, "name": {"type": "string"}, "text": {"type": "string"}},
                  "required": ["project", "style"]},
    "branch": {"description": "Copy a book at a history moment into a new book.", "method": "POST", "path": "/api/v1/branch",
               "properties": {"project": {"type": "string"}, "moment": {"type": "string"}, "name": {"type": "string"}}, "required": ["project", "moment", "name"]},
    "queue": {"description": "Queue Autopilot runs for several books, one after another.", "method": "POST", "path": "/api/v1/queue",
              "properties": {"projects": {"type": "array", "items": {"type": "string"}}}, "required": ["projects"]},
}


def call_api(tool: str, args: dict, base: str, token: str) -> Any:
    spec = TOOLS[tool]
    url = base.rstrip("/") + spec["path"]
    data = None
    if spec["method"] == "GET":
        from urllib.parse import urlencode
        url += "?" + urlencode({k: v for k, v in args.items() if isinstance(v, (str, int, float))})
    else:
        data = json.dumps(args).encode()
    req = urllib.request.Request(url, data=data, method=spec["method"], headers={"X-Studio-Token": token, "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=120) as r:  # noqa: S310  the local Studio's own address
            return json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        body = e.read().decode(errors="replace")
        try:
            msg = json.loads(body).get("error", body)
        except ValueError:
            msg = body
        raise RuntimeError(f"the Studio answered {e.code}: {msg}") from None
    except urllib.error.URLError as e:
        raise RuntimeError(f"the Studio is not reachable at {base} ({e.reason}); start it first") from None


def handle(msg: dict, base: str, token: str) -> dict | None:
    """One JSON-RPC request -> its response (None for a notification)."""
    mid, method, params = msg.get("id"), msg.get("method", ""), msg.get("params") or {}
    if mid is None:
        return None                                           # notifications (initialized, cancelled ...) need no answer
    if method == "initialize":
        result: Any = {"protocolVersion": PROTOCOL, "capabilities": {"tools": {"listChanged": False}},
                       "serverInfo": {"name": "pistachios-studio", "version": "1.0"},
                       "instructions": "Drive Pistachio's Studio: create a book from sources, run Autopilot, follow its status, get the downloads."}
    elif method == "ping":
        result = {}
    elif method == "tools/list":
        result = {"tools": [{"name": n, "description": t["description"],
                             "inputSchema": {"type": "object", "properties": t["properties"], "required": t.get("required", [])}} for n, t in TOOLS.items()]}
    elif method == "tools/call":
        name, args = params.get("name"), params.get("arguments") or {}
        if name not in TOOLS:
            return {"jsonrpc": "2.0", "id": mid, "error": {"code": -32602, "message": f"unknown tool {name!r}"}}
        missing = [k for k in TOOLS[name].get("required", []) if k not in args]
        if missing:
            return {"jsonrpc": "2.0", "id": mid, "result": {"content": [{"type": "text", "text": f"missing: {', '.join(missing)}"}], "isError": True}}
        try:
            out = call_api(name, args, base, token)
            result = {"content": [{"type": "text", "text": json.dumps(out, ensure_ascii=False)}], "structuredContent": out if isinstance(out, dict) else {"value": out}}
        except RuntimeError as e:
            result = {"content": [{"type": "text", "text": str(e)}], "isError": True}
    else:
        return {"jsonrpc": "2.0", "id": mid, "error": {"code": -32601, "message": f"no method {method}"}}
    return {"jsonrpc": "2.0", "id": mid, "result": result}


def main() -> int:
    base = os.environ.get("STUDIO_URL", "http://127.0.0.1:8765")
    token = os.environ.get("STUDIO_TOKEN", "")
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except ValueError:
            out: dict | None = {"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "parse error"}}
        else:
            out = handle(msg, base, token) if isinstance(msg, dict) else {"jsonrpc": "2.0", "id": None, "error": {"code": -32600, "message": "invalid request"}}
        if out is not None:
            sys.stdout.write(json.dumps(out) + "\n")
            sys.stdout.flush()
    return 0


if __name__ == "__main__":
    sys.exit(main())
