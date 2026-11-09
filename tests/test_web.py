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


def test_escape_html_escapes_quotes():
    js = (WEB / "static" / "js" / "studio.js").read_text()
    body = js[js.index("function escapeHtml"):][:400]
    assert "&quot;" in body and "&#39;" in body


def test_static_files_served_with_types(server):
    status, hdrs, body = server.request("GET", "/static/js/studio.js")
    assert status == 200 and hdrs["Content-Type"].startswith("text/javascript") or hdrs["Content-Type"].startswith("application/javascript")
    assert b"TOKEN" in body and TOKEN.encode() not in body          # the token is never in a static file
    status, hdrs, _ = server.request("GET", "/static/css/studio.css")
    assert status == 200 and hdrs["Content-Type"].startswith("text/css")
    assert server.request("GET", "/static/nope.js")[0] == 404
