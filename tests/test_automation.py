"""M15: the automation API (/api/v1), the event stream, the book2screen command line and the MCP server."""
import json
import subprocess
import sys
from pathlib import Path

import book2screen
import layout
import mcp_server
from test_read_it_in import STORY

ROOT = Path(__file__).resolve().parent.parent


class TestApi:
    def test_create_status_exports_and_errors(self, server, fake_root):
        st, j = server.api("POST", "/api/v1/projects", {"name": "sea_tale", "sources": [{"kind": "idea", "text": STORY}], "rights": True,
                                                         "recipe": "short_film", "products": ["screenplay", "storyboard"], "styles": ["anime", "noir"]})
        assert st == 200 and j == {"project": "sea_tale", "sources": 1, "autopilot": False}
        st, j = server.api("GET", "/api/v1/project?project=sea_tale")
        assert st == 200 and j["steps"]["read_it_in"] == "to do" and j["settings"]["recipe"] == "short_film" and j["steps"]["pictures_noir"] == "not approved"
        assert j["cost"]["estimate"]["gpu_hours"] >= 0
        st, j = server.api("POST", "/api/v1/projects", {"name": "sea_tale", "rights": True})
        assert st == 400 and "already" in j["error"]
        st, j = server.api("POST", "/api/v1/projects", {"name": "x2", "sources": [{"kind": "idea", "text": "y"}]})
        assert st == 400 and "right" in j["error"]
        st, j = server.api("POST", "/api/v1/sources", {"project": "sea_tale", "kind": "idea", "text": "A new ending.", "rights": True})
        assert st == 200 and j["sources"] == 2
        st, j = server.api("POST", "/api/v1/run", {"project": "sea_tale", "stop_at": ["lunch"]})
        assert st == 400
        st, j = server.api("GET", "/api/v1/exports?project=sea_tale")
        assert st == 200 and j["exports"] == []
        st, j = server.api("POST", "/api/v1/stop", {"project": "sea_tale"})
        assert st == 400

    def test_events_stream(self, server):
        status, hdrs, body = server.request("GET", "/api/v1/events?since=0&seconds=0.6", headers={"X-Studio-Token": "t" * 32})
        assert status == 200 and hdrs["Content-Type"].startswith("text/event-stream") and body.startswith(b"retry: 3000") and b"event: status" in body


class TestCli:
    def test_make_with_the_fake_crew_and_status(self, fake_root, capsys):
        assert book2screen.name_for("A lighthouse keeper finds a door") == "a_lighthouse_keeper_finds_a_door" and book2screen.name_for("https://www.x.org/a") == "x_org"
        rc = book2screen.main(["make", STORY, "--name", "door_cli", "--product", "screenplay", "--minutes", "1", "--engine", "fake", "--stop-at", "continuity"])
        out = capsys.readouterr().out
        assert rc == 0 and "door_cli: source s001 (idea" in out and "Waiting for your review at the continuity book" in out
        d = layout.find_dir("door_cli")
        assert (d / "readin" / "summary.json").is_file()
        assert book2screen.main(["status", "door_cli"]) == 0 and '"project": "door_cli"' in capsys.readouterr().out
        assert book2screen.main(["status", "nope_x"]) == 1


class TestMcp:
    def test_protocol(self):
        assert mcp_server.handle({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}}, "", "")["result"]["protocolVersion"] == mcp_server.PROTOCOL
        assert mcp_server.handle({"jsonrpc": "2.0", "method": "notifications/initialized"}, "", "") is None
        tools = mcp_server.handle({"jsonrpc": "2.0", "id": 2, "method": "tools/list"}, "", "")["result"]["tools"]
        assert {t["name"] for t in tools} >= {"create_project", "run_autopilot", "project_status", "list_exports"} and tools[0]["inputSchema"]["type"] == "object"
        r = mcp_server.handle({"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "project_status", "arguments": {}}}, "", "")
        assert r["result"]["isError"] and "missing: project" in r["result"]["content"][0]["text"]
        assert mcp_server.handle({"jsonrpc": "2.0", "id": 4, "method": "tools/call", "params": {"name": "rm", "arguments": {}}}, "", "")["error"]["code"] == -32602
        assert mcp_server.handle({"jsonrpc": "2.0", "id": 5, "method": "nope"}, "", "")["error"]["code"] == -32601

    def test_against_the_running_studio(self, server, fake_root):
        base = f"http://127.0.0.1:{server.port}"
        r = mcp_server.handle({"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": "create_project", "arguments":
                              {"name": "mcp_book", "sources": [{"kind": "idea", "text": STORY}], "rights": True}}}, base, "t" * 32)
        assert not r["result"].get("isError") and r["result"]["structuredContent"]["project"] == "mcp_book"
        r = mcp_server.handle({"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"name": "project_status", "arguments": {"project": "mcp_book"}}}, base, "wrong")
        assert r["result"]["isError"] and "403" in r["result"]["content"][0]["text"]               # the same token as the page

    def test_stdio(self):
        msgs = [{"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}}, {"jsonrpc": "2.0", "method": "notifications/initialized"},
                {"jsonrpc": "2.0", "id": 2, "method": "tools/list"}]
        p = subprocess.run([sys.executable, str(ROOT / "scripts" / "mcp_server.py")], input="\n".join(json.dumps(m) for m in msgs) + "\nnot json\n",
                           capture_output=True, text=True, timeout=30)
        lines = [json.loads(x) for x in p.stdout.strip().split("\n")]
        assert [x.get("id") for x in lines] == [1, 2, None] and lines[2]["error"]["code"] == -32700
