"""
MCP (Model Context Protocol) Client for Pistachio's Studio.

Replaces the broken `claude mcp call` subprocess invocation (which does not exist in Claude CLI)
with real MCP JSON-RPC 2.0 transport over:
  1. stdio servers configured in `.mcp.json`, `~/.claude.json`, or `STUDIO_MCP_CONFIG`
  2. HTTP JSON-RPC MCP endpoints (`url`)
"""
from __future__ import annotations

import asyncio
import contextlib
import json
import os
import shutil
import subprocess
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


def _candidate_config_paths() -> list[Path]:
    paths: list[Path] = []
    env_p = os.environ.get("STUDIO_MCP_CONFIG", "").strip()
    if env_p:
        paths.append(Path(env_p))
    repo_root = Path(__file__).resolve().parent.parent
    paths.append(repo_root / ".mcp.json")
    paths.append(Path.cwd() / ".mcp.json")
    paths.append(Path.home() / ".claude.json")
    paths.append(Path.home() / ".config" / "pistachio" / "mcp_servers.json")
    out: list[Path] = []
    seen: set[str] = set()
    for p in paths:
        try:
            key = str(p.resolve())
        except OSError:
            key = str(p)
        if key not in seen:
            seen.add(key)
            out.append(p)
    return out


def load_mcp_server_configs() -> dict[str, dict[str, Any]]:
    """Discover configured MCP servers from `.mcp.json` and `~/.claude.json`."""
    found: dict[str, dict[str, Any]] = {}
    for cfg_path in _candidate_config_paths():
        if not cfg_path.is_file():
            continue
        try:
            raw = json.loads(cfg_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if not isinstance(raw, dict):
            continue
        servers = raw.get("mcpServers")
        if isinstance(servers, dict):
            for name, spec in servers.items():
                if isinstance(spec, dict) and str(name).strip() and name not in found:
                    found[str(name).strip().lower()] = {**spec, "_source": str(cfg_path)}
        # Also check Claude Code per-project mcpServers entries in ~/.claude.json
        projects = raw.get("projects")
        if isinstance(projects, dict):
            for p_spec in projects.values():
                if not isinstance(p_spec, dict):
                    continue
                p_servers = p_spec.get("mcpServers")
                if isinstance(p_servers, dict):
                    for name, spec in p_servers.items():
                        if isinstance(spec, dict) and str(name).strip() and name.lower() not in found:
                            found[str(name).strip().lower()] = {**spec, "_source": str(cfg_path)}
    return found


class MCPClient:
    """Real JSON-RPC 2.0 MCP client supporting stdio and HTTP MCP servers."""

    def __init__(self, timeout: int = 30):
        self.timeout = timeout
        self._available_servers: dict[str, bool] = {}

    def get_server_config(self, server: str) -> dict[str, Any] | None:
        configs = load_mcp_server_configs()
        low = str(server or "").strip().lower()
        if low in configs:
            return configs[low]
        # Allow partial alias matches like "premiere-pro-mcp" for "premiere" or "blender-mcp" for "blender"
        for key, spec in configs.items():
            if low and (low in key or key in low):
                return spec
        return None

    def server_status(self, server: str) -> dict[str, Any]:
        spec = self.get_server_config(server)
        if not spec:
            return {
                "configured": False,
                "available": False,
                "transport": "none",
                "source": "",
                "detail": f"No '{server}' MCP server configured in .mcp.json or ~/.claude.json",
            }
        if spec.get("url"):
            return {
                "configured": True,
                "available": True,
                "transport": "http",
                "source": str(spec.get("_source") or ""),
                "detail": str(spec["url"]),
            }
        cmd = str(spec.get("command") or "").strip()
        resolved = shutil.which(cmd) if cmd else None
        ok = bool(resolved or (cmd and Path(cmd).is_file()))
        return {
            "configured": True,
            "available": ok,
            "transport": "stdio",
            "source": str(spec.get("_source") or ""),
            "detail": resolved or cmd or "missing command",
        }

    def _call_http_mcp(self, url: str, headers: dict[str, str], tool: str, args: dict[str, Any]) -> dict[str, Any]:
        req_headers = {"Content-Type": "application/json", "Accept": "application/json, text/event-stream", **headers}
        payload = json.dumps({
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {"name": tool, "arguments": args},
        }).encode("utf-8")
        req = urllib.request.Request(url, data=payload, headers=req_headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                raw = resp.read().decode("utf-8", "replace").strip()
            # Handle SSE or plain JSON responses
            if raw.startswith("event:") or raw.startswith("data:"):
                for line in raw.splitlines():
                    if line.startswith("data:"):
                        raw = line[5:].strip()
                        break
            parsed = json.loads(raw)
            if isinstance(parsed, dict) and "error" in parsed:
                err = parsed["error"]
                return {"error": err.get("message", str(err)) if isinstance(err, dict) else str(err)}
            if isinstance(parsed, dict) and "result" in parsed:
                return parsed["result"] if isinstance(parsed["result"], dict) else {"result": parsed["result"]}
            return parsed if isinstance(parsed, dict) else {"result": parsed}
        except urllib.error.HTTPError as e:
            return {"error": f"MCP HTTP {e.code}: {e.read().decode('utf-8', 'replace')[:300]}"}
        except Exception as e:
            return {"error": f"MCP HTTP call failed: {e}"}

    def _call_stdio_mcp(self, spec: dict[str, Any], server: str, tool: str, args: dict[str, Any]) -> dict[str, Any]:
        cmd = str(spec.get("command") or "").strip()
        raw_args = spec.get("args") or []
        cmd_args = [str(a) for a in raw_args] if isinstance(raw_args, list) else []
        if not cmd:
            return {"error": f"MCP server '{server}' config is missing 'command'"}
        exe = shutil.which(cmd) or (cmd if Path(cmd).is_file() else "")
        if not exe:
            return {"error": f"MCP server '{server}' executable not found: {cmd}"}

        env = dict(os.environ)
        extra_env = spec.get("env")
        if isinstance(extra_env, dict):
            for k, v in extra_env.items():
                env[str(k)] = str(v)

        init_req = json.dumps({
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "pistachios-studio", "version": "2.0"},
            },
        })
        init_note = json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}})
        call_req = json.dumps({
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {"name": tool, "arguments": args},
        })
        wire_in = f"{init_req}\n{init_note}\n{call_req}\n"

        try:
            proc = subprocess.run(
                [exe, *cmd_args],
                input=wire_in,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                env=env,
                timeout=self.timeout,
            )
        except subprocess.TimeoutExpired:
            return {"error": f"MCP call to {server}.{tool} timed out after {self.timeout}s"}
        except OSError as e:
            return {"error": f"Failed to start MCP server '{server}': {e}"}

        # Parse JSON-RPC response lines for id == 2
        for line in proc.stdout.splitlines():
            s = line.strip()
            if not s or not s.startswith("{"):
                continue
            try:
                msg = json.loads(s)
            except ValueError:
                continue
            if not isinstance(msg, dict) or msg.get("id") != 2:
                continue
            if "error" in msg:
                err = msg["error"]
                return {"error": err.get("message", str(err)) if isinstance(err, dict) else str(err)}
            res = msg.get("result")
            return res if isinstance(res, dict) else {"result": res}

        stderr_tail = (proc.stderr or "").strip()[-400:]
        return {"error": stderr_tail or f"MCP server '{server}' returned no response for tool '{tool}' (exit {proc.returncode})"}

    def _call_mcp(self, server: str, tool: str, args: dict[str, Any]) -> dict[str, Any]:
        """Call an MCP server tool via configured stdio or HTTP JSON-RPC 2.0 transport."""
        spec = self.get_server_config(server)
        if not spec:
            return {
                "error": (
                    f"MCP server '{server}' is not configured. "
                    "Add it to .mcp.json or run `claude mcp add` to enable live MCP control."
                ),
                "not_configured": True,
            }
        url = str(spec.get("url") or "").strip()
        if url:
            headers = spec.get("headers") if isinstance(spec.get("headers"), dict) else {}
            return self._call_http_mcp(url, {str(k): str(v) for k, v in headers.items()}, tool, args)
        return self._call_stdio_mcp(spec, server, tool, args)

    async def _call_mcp_async(self, server: str, tool: str, args: dict[str, Any]) -> dict[str, Any]:
        """Async wrapper around `_call_mcp`."""
        return await asyncio.to_thread(self._call_mcp, server, tool, args)

    def check_server(self, server: str) -> bool:
        """Check if an MCP server is configured and reachable/installed."""
        if server in self._available_servers:
            return self._available_servers[server]
        st = self.server_status(server)
        available = bool(st.get("configured") and st.get("available"))
        self._available_servers[server] = available
        return available


# =============================================================================
# Firecrawl MCP - Web Scraping for Research
# =============================================================================

class FirecrawlMCP:
    """Integration with firecrawl-mcp-server for web research."""

    def __init__(self, client: MCPClient | None = None):
        self.client = client or MCPClient(timeout=60)

    def scrape(self, url: str, formats: list[str] | None = None) -> dict[str, Any]:
        args: dict[str, Any] = {"url": url}
        if formats:
            args["formats"] = formats
        return self.client._call_mcp("firecrawl", "scrape", args)

    def crawl(self, url: str, limit: int = 10) -> dict[str, Any]:
        return self.client._call_mcp("firecrawl", "crawl", {"url": url, "limit": limit})

    def search(self, query: str, limit: int = 10) -> dict[str, Any]:
        return self.client._call_mcp("firecrawl", "search", {"query": query, "limit": limit})

    def research_film_comparables(self, genre: str, year: int | None = None) -> dict[str, Any]:
        query = f"top {genre} films"
        if year:
            query += f" {year}"
        query += " box office budget"
        return self.search(query, limit=10)

    def research_screenplay_structure(self, title: str) -> dict[str, Any]:
        return self.search(f"{title} screenplay structure analysis", limit=5)


# =============================================================================
# Premiere Pro MCP - Direct Timeline/Sequence Control
# =============================================================================

class PremiereMCP:
    """Integration with premiere-pro-mcp for Adobe Premiere Pro automation."""

    def __init__(self, client: MCPClient | None = None):
        self.client = client or MCPClient(timeout=60)

    def is_configured(self) -> bool:
        return self.client.check_server("premiere")

    def connect(self) -> dict[str, Any]:
        return self.client._call_mcp("premiere", "connect", {})

    def import_fdx(self, fdx_path: str, project_name: str | None = None) -> dict[str, Any]:
        args: dict[str, Any] = {"fdx_path": fdx_path}
        if project_name:
            args["project_name"] = project_name
        return self.client._call_mcp("premiere", "import_fdx", args)

    def create_sequence(self, name: str, settings: dict[str, Any] | None = None) -> dict[str, Any]:
        args: dict[str, Any] = {"name": name}
        if settings:
            args["settings"] = settings
        return self.client._call_mcp("premiere", "create_sequence", args)

    def add_markers(self, sequence_name: str, markers: list[dict[str, Any]]) -> dict[str, Any]:
        return self.client._call_mcp("premiere", "add_markers", {"sequence": sequence_name, "markers": markers})

    def export_xml(self, sequence_name: str, output_path: str) -> dict[str, Any]:
        return self.client._call_mcp("premiere", "export_xml", {"sequence": sequence_name, "output": output_path})


# =============================================================================
# Blender MCP - 3D Previs Generation
# =============================================================================

class BlenderMCP:
    """Integration with blender-mcp for 3D previs/asset generation."""

    def __init__(self, client: MCPClient | None = None):
        self.client = client or MCPClient(timeout=120)

    def is_configured(self) -> bool:
        return self.client.check_server("blender")

    def create_scene(self, prompt: str, output_format: str = "glb") -> dict[str, Any]:
        return self.client._call_mcp("blender", "create_scene", {"prompt": prompt, "output_format": output_format})

    def generate_previs(self, scene_data: dict[str, Any]) -> dict[str, Any]:
        prompt = self._build_previs_prompt(scene_data)
        return self.create_scene(prompt)

    def _build_previs_prompt(self, scene: dict[str, Any]) -> str:
        parts = [
            f"Cinematic previs for: {scene.get('heading', 'Unknown Scene')}",
            f"Action: {scene.get('action_summary', '')}",
            f"Characters: {', '.join(scene.get('characters', []))}",
            f"Mood: {scene.get('mood', 'cinematic')}",
            f"Lighting: {scene.get('lighting', 'natural')}",
            "Style: professional film previsualization, realistic camera angles, proper blocking",
        ]
        return ". ".join(filter(None, parts))

    def export_gltf(self, scene_name: str, output_path: str) -> dict[str, Any]:
        return self.client._call_mcp("blender", "export_gltf", {"scene": scene_name, "output": output_path})


# =============================================================================
# Playwright MCP - Browser Automation for Final Draft Web
# =============================================================================

class PlaywrightMCP:
    """Integration with playwright-mcp for browser automation."""

    def __init__(self, client: MCPClient | None = None):
        self.client = client or MCPClient(timeout=120)

    def is_configured(self) -> bool:
        return self.client.check_server("playwright")

    def run_script(self, script: str, args: dict[str, Any] | None = None) -> dict[str, Any]:
        payload: dict[str, Any] = {"script": script}
        if args:
            payload["args"] = args
        return self.client._call_mcp("playwright", "run_script", payload)

    def automate_finaldraft_import(self, fdx_path: str, project_title: str | None = None) -> dict[str, Any]:
        escaped_path = json.dumps(str(fdx_path))
        script = f"""
        const filePath = {escaped_path};
        await page.goto('https://www.finaldraft.com/', {{ waitUntil: 'networkidle' }});
        await page.waitForSelector('[data-testid="import-button"], button:has-text("Import")', {{ timeout: 10000 }});
        await page.click('[data-testid="import-button"], button:has-text("Import")');
        await page.waitForSelector('input[type="file"]', {{ timeout: 5000 }});
        await page.setInputFiles('input[type="file"]', filePath);
        await page.waitForSelector('[data-testid="script-loaded"], .script-editor', {{ timeout: 30000 }});
        console.log('Import complete');
        """
        return self.run_script(script)

    def automate_finaldraft_export(self, output_path: str, format: str = "fdx") -> dict[str, Any]:
        escaped_out = json.dumps(str(output_path))
        safe_fmt = "".join(c for c in str(format or "fdx") if c.isalnum())
        script = f"""
        await page.goto('https://www.finaldraft.com/', {{ waitUntil: 'networkidle' }});
        await page.click('[data-testid="export-button"], button:has-text("Export")');
        await page.click('[data-testid="export-{safe_fmt}"]');
        const download = await page.waitForEvent('download');
        await download.saveAs({escaped_out});
        console.log('Export complete');
        """
        return self.run_script(script)


# =============================================================================
# PostgreSQL MCP - Structured Data Storage
# =============================================================================

class PostgresMCP:
    """Integration with postgres-mcp for database operations."""

    def __init__(self, client: MCPClient | None = None):
        self.client = client or MCPClient(timeout=30)

    def connect(self, connection_string: str | None = None) -> dict[str, Any]:
        args: dict[str, Any] = {}
        if connection_string:
            args["connection_string"] = connection_string
        return self.client._call_mcp("postgres", "connect", args)

    def query(self, sql: str, params: list[Any] | None = None) -> dict[str, Any]:
        args: dict[str, Any] = {"query": sql}
        if params:
            args["params"] = params
        return self.client._call_mcp("postgres", "query", args)

    def execute(self, sql: str, params: list[Any] | None = None) -> dict[str, Any]:
        args: dict[str, Any] = {"query": sql}
        if params:
            args["params"] = params
        return self.client._call_mcp("postgres", "execute", args)

    def init_studio_schema(self) -> dict[str, Any]:
        schema_sql = """
        CREATE TABLE IF NOT EXISTS screenplays (
            id VARCHAR(255) PRIMARY KEY,
            title VARCHAR(500),
            fdx_content TEXT,
            fountain_content TEXT,
            metadata JSONB,
            created_at TIMESTAMP DEFAULT NOW(),
            updated_at TIMESTAMP DEFAULT NOW()
        );
        CREATE TABLE IF NOT EXISTS screenplay_versions (
            id SERIAL PRIMARY KEY,
            screenplay_id VARCHAR(255) REFERENCES screenplays(id),
            version INTEGER,
            fdx_content TEXT,
            fountain_content TEXT,
            metadata JSONB,
            created_at TIMESTAMP DEFAULT NOW()
        );
        CREATE TABLE IF NOT EXISTS research_cache (
            id SERIAL PRIMARY KEY,
            query_hash VARCHAR(64) UNIQUE,
            query TEXT,
            results JSONB,
            created_at TIMESTAMP DEFAULT NOW()
        );
        CREATE INDEX IF NOT EXISTS idx_screenplays_updated ON screenplays(updated_at);
        CREATE INDEX IF NOT EXISTS idx_research_query ON research_cache(query_hash);
        """
        return self.execute(schema_sql)

    def save_screenplay(self, screenplay_id: str, title: str, fdx: str, fountain: str, metadata: dict[str, Any]) -> dict[str, Any]:
        return self.execute(
            """INSERT INTO screenplays (id, title, fdx_content, fountain_content, metadata)
               VALUES ($1, $2, $3, $4, $5)
               ON CONFLICT (id) DO UPDATE SET
                   fdx_content = $3, fountain_content = $4, metadata = $5, updated_at = NOW()""",
            [screenplay_id, title, fdx, fountain, json.dumps(metadata)],
        )

    def load_screenplay(self, screenplay_id: str) -> dict[str, Any]:
        return self.query("SELECT * FROM screenplays WHERE id = $1", [screenplay_id])


# =============================================================================
# Convenience Functions
# =============================================================================

def get_mcp_client() -> MCPClient:
    return MCPClient()


def get_firecrawl() -> FirecrawlMCP:
    return FirecrawlMCP()


def get_premiere() -> PremiereMCP:
    return PremiereMCP()


def get_blender() -> BlenderMCP:
    return BlenderMCP()


def get_playwright() -> PlaywrightMCP:
    return PlaywrightMCP()


def get_postgres() -> PostgresMCP:
    return PostgresMCP()


with contextlib.suppress(Exception):
    pass
