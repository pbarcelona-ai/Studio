"""The page must stay compatible with its Content-Security-Policy (no inline script, no inline event handlers)."""
import re
from pathlib import Path

from conftest import TOKEN

WEB = Path(__file__).resolve().parent.parent / "web"
HANDLER = re.compile(r"""\son(click|change|input|submit|load|error|focus|blur|keydown|keyup|mouse\w+)\s*=""", re.I)


def test_index_has_no_inline_script_or_handlers():
    html = (WEB / "index.html").read_text()
    for m in re.finditer(r"<script\b([^>]*)>", html):
        assert "src=" in m.group(1), "inline <script> would be blocked by the CSP"
    assert not HANDLER.search(html)
    assert "javascript:" not in html.lower()
    assert 'name="studio-token"' in html and "__TOKEN__" in html


def test_static_js_has_no_inline_handlers():
    for f in (WEB / "static" / "js").glob("*.js"):
        assert not HANDLER.search(f.read_text()), f"{f.name} builds markup with an inline event handler"


def all_js():
    return "\n".join(f.read_text() for f in sorted((WEB / "static" / "js").glob("*.js")))


def test_escape_html_escapes_quotes():
    js = all_js()
    body = js[js.index("function escapeHtml"):][:400]
    assert "&quot;" in body and "&#39;" in body


def script_order():
    return re.findall(r'<script src="/static/js/(\w+)\.js" defer>', (WEB / "index.html").read_text())


def test_every_js_file_is_loaded_exactly_once():
    on_disk = {f.stem for f in (WEB / "static" / "js").glob("*.js")}
    order = script_order()
    assert sorted(order) == sorted(on_disk) and len(order) == len(set(order))


def test_no_load_time_use_of_functions_defined_in_later_files():
    """Classic scripts hoist functions only within their own file: a top-level statement that uses a function from a LATER file would fail on load."""
    order = script_order()
    src = {n: (WEB / "static" / "js" / f"{n}.js").read_text().split("\n") for n in order}
    defined = {}
    for i, n in enumerate(order):
        for line in src[n]:
            m = re.match(r"(?:async\s+)?function\s+([A-Za-z_$][\w$]*)", line)
            if m:
                defined[m.group(1)] = i
    bad = []
    for i, n in enumerate(order):
        depth = 0
        for ln, line in enumerate(src[n], 1):
            if depth == 0 and line and not line.startswith(("function", "async function", "//", "}", "/*", " *")):
                for name, where in defined.items():
                    if where > i and re.search(r"(?<![\w$.\"'])" + re.escape(name) + r"(?![\w$])", line):
                        # fine when the use is inside an arrow function body on that line (it runs later)
                        pos = re.search(r"(?<![\w$.\"'])" + re.escape(name) + r"(?![\w$])", line).start()
                        if "=>" not in line[:pos] and "function" not in line[:pos]:
                            bad.append(f"{n}.js:{ln}: {name}")
            depth += sum(line.count(c) for c in "{([") - sum(line.count(c) for c in "})]")
    assert bad == []


def test_static_files_served_with_types(server):
    status, hdrs, body = server.request("GET", "/static/js/core.js")
    assert status == 200 and hdrs["Content-Type"].split(";")[0] in ("text/javascript", "application/javascript")
    assert b"TOKEN" in body and TOKEN.encode() not in body          # the token is never in a static file
    status, hdrs, _ = server.request("GET", "/static/css/studio.css")
    assert status == 200 and hdrs["Content-Type"].startswith("text/css")
    assert server.request("GET", "/static/nope.js")[0] == 404
