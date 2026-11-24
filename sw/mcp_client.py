"""
MCP (Model Context Protocol) Client for Pistachio's Studio.
Provides integration with various MCP servers via subprocess calls to `claude mcp call`.
"""
from __future__ import annotations

import json
import subprocess
import asyncio


class MCPClient:
    """Client for calling MCP servers through Claude Code's MCP integration."""

    def __init__(self, timeout: int = 30):
        self.timeout = timeout
        self._available_servers: dict[str, bool] = {}

    def _call_mcp(self, server: str, tool: str, args: dict) -> dict:
        """Call an MCP server tool via claude mcp call."""
        try:
            result = subprocess.run(
                ["claude", "mcp", "call", server, tool, json.dumps(args)],
                capture_output=True,
                text=True,
                timeout=self.timeout,
            )
            if result.returncode != 0:
                return {"error": result.stderr.strip() or f"MCP call failed with code {result.returncode}"}
            return json.loads(result.stdout)
        except subprocess.TimeoutExpired:
            return {"error": f"MCP call to {server}.{tool} timed out after {self.timeout}s"}
        except json.JSONDecodeError:
            return {"error": "Invalid JSON response from MCP server"}
        except FileNotFoundError:
            return {"error": "claude command not found. Is Claude Code installed?"}
        except Exception as e:
            return {"error": f"MCP call failed: {e}"}

    async def _call_mcp_async(self, server: str, tool: str, args: dict) -> dict:
        """Async version of _call_mcp."""
        try:
            proc = await asyncio.create_subprocess_exec(
                "claude", "mcp", "call", server, tool, json.dumps(args),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=self.timeout)
            if proc.returncode != 0:
                return {"error": stderr.decode().strip() or f"MCP call failed with code {proc.returncode}"}
            return json.loads(stdout.decode())
        except TimeoutError:
            return {"error": f"MCP call to {server}.{tool} timed out after {self.timeout}s"}
        except json.JSONDecodeError:
            return {"error": "Invalid JSON response from MCP server"}
        except FileNotFoundError:
            return {"error": "claude command not found. Is Claude Code installed?"}
        except Exception as e:
            return {"error": f"MCP call failed: {e}"}

    def check_server(self, server: str) -> bool:
        """Check if an MCP server is available."""
        if server in self._available_servers:
            return self._available_servers[server]
        result = self._call_mcp(server, "ping", {}) if server != "firecrawl" else self._call_mcp(server, "scrape", {"url": "https://example.com"})
        # For firecrawl, we use scrape as a health check
        available = "error" not in result
        self._available_servers[server] = available
        return available


# =============================================================================
# Firecrawl MCP - Web Scraping for Research
# =============================================================================

class FirecrawlMCP:
    """Integration with firecrawl-mcp-server for web research."""

    def __init__(self, client: MCPClient | None = None):
        self.client = client or MCPClient(timeout=60)

    def scrape(self, url: str, formats: list[str] = None) -> dict:
        """Scrape a single URL."""
        args = {"url": url}
        if formats:
            args["formats"] = formats
        return self.client._call_mcp("firecrawl", "scrape", args)

    def crawl(self, url: str, limit: int = 10) -> dict:
        """Crawl a website starting from a URL."""
        return self.client._call_mcp("firecrawl", "crawl", {"url": url, "limit": limit})

    def search(self, query: str, limit: int = 10) -> dict:
        """Search the web."""
        return self.client._call_mcp("firecrawl", "search", {"query": query, "limit": limit})

    def research_film_comparables(self, genre: str, year: int = None) -> dict:
        """Research comparable films for a genre/year."""
        query = f"top {genre} films"
        if year:
            query += f" {year}"
        query += " box office budget"
        return self.search(query, limit=10)

    def research_screenplay_structure(self, title: str) -> dict:
        """Research screenplay structure for a specific film."""
        return self.search(f"{title} screenplay structure analysis", limit=5)


# =============================================================================
# Premiere Pro MCP - Direct Timeline/Sequence Control
# =============================================================================

class PremiereMCP:
    """Integration with premiere-pro-mcp for Adobe Premiere Pro automation."""

    def __init__(self, client: MCPClient | None = None):
        self.client = client or MCPClient(timeout=60)

    def connect(self) -> dict:
        """Connect to Premiere Pro."""
        return self.client._call_mcp("premiere", "connect", {})

    def import_fdx(self, fdx_path: str, project_name: str = None) -> dict:
        """Import FDX file and create a sequence."""
        args = {"fdx_path": fdx_path}
        if project_name:
            args["project_name"] = project_name
        return self.client._call_mcp("premiere", "import_fdx", args)

    def create_sequence(self, name: str, settings: dict = None) -> dict:
        """Create a new sequence."""
        args = {"name": name}
        if settings:
            args["settings"] = settings
        return self.client._call_mcp("premiere", "create_sequence", args)

    def add_markers(self, sequence_name: str, markers: list[dict]) -> dict:
        """Add markers to a sequence (e.g., scene boundaries)."""
        return self.client._call_mcp("premiere", "add_markers", {
            "sequence": sequence_name,
            "markers": markers
        })

    def export_xml(self, sequence_name: str, output_path: str) -> dict:
        """Export sequence as Final Cut Pro XML."""
        return self.client._call_mcp("premiere", "export_xml", {
            "sequence": sequence_name,
            "output": output_path
        })


# =============================================================================
# Blender MCP - 3D Previs Generation
# =============================================================================

class BlenderMCP:
    """Integration with blender-mcp for 3D previs/asset generation."""

    def __init__(self, client: MCPClient | None = None):
        self.client = client or MCPClient(timeout=120)

    def create_scene(self, prompt: str, output_format: str = "glb") -> dict:
        """Create a Blender scene from a text prompt."""
        return self.client._call_mcp("blender", "create_scene", {
            "prompt": prompt,
            "output_format": output_format
        })

    def generate_previs(self, scene_data: dict) -> dict:
        """Generate previs for a screenplay scene."""
        prompt = self._build_previs_prompt(scene_data)
        return self.create_scene(prompt)

    def _build_previs_prompt(self, scene: dict) -> str:
        """Build a detailed prompt for previs generation."""
        parts = [
            f"Cinematic previs for: {scene.get('heading', 'Unknown Scene')}",
            f"Action: {scene.get('action_summary', '')}",
            f"Characters: {', '.join(scene.get('characters', []))}",
            f"Mood: {scene.get('mood', 'cinematic')}",
            f"Lighting: {scene.get('lighting', 'natural')}",
            "Style: professional film previsualization, realistic camera angles, proper blocking",
        ]
        return ". ".join(filter(None, parts))

    def export_gltf(self, scene_name: str, output_path: str) -> dict:
        """Export a Blender scene as GLTF/GLB."""
        return self.client._call_mcp("blender", "export_gltf", {
            "scene": scene_name,
            "output": output_path
        })


# =============================================================================
# Playwright MCP - Browser Automation for Final Draft Web
# =============================================================================

class PlaywrightMCP:
    """Integration with playwright-mcp for browser automation."""

    def __init__(self, client: MCPClient | None = None):
        self.client = client or MCPClient(timeout=120)

    def run_script(self, script: str, args: dict = None) -> dict:
        """Run a Playwright script."""
        payload = {"script": script}
        if args:
            payload["args"] = args
        return self.client._call_mcp("playwright", "run_script", payload)

    def automate_finaldraft_import(self, fdx_path: str, project_title: str = None) -> dict:
        """Automate importing FDX into Final Draft Web."""
        script = f"""
        const fs = require('fs');
        const path = '{fdx_path}';

        await page.goto('https://finaldraft.com/web/', {{ waitUntil: 'networkidle' }});

        // Click import button
        await page.waitForSelector('[data-testid="import-button"], button:has-text("Import")', {{ timeout: 10000 }});
        await page.click('[data-testid="import-button"], button:has-text("Import")');

        // Set file input
        await page.waitForSelector('input[type="file"]', {{ timeout: 5000 }});
        await page.setInputFiles('input[type="file"]', path);

        // Wait for import to complete
        await page.waitForSelector('[data-testid="script-loaded"], .script-editor', {{ timeout: 30000 }});

        console.log('Import complete');
        """
        return self.run_script(script)

    def automate_finaldraft_export(self, output_path: str, format: str = "fdx") -> dict:
        """Automate exporting from Final Draft Web."""
        script = f"""
        await page.goto('https://finaldraft.com/web/', {{ waitUntil: 'networkidle' }});

        // Click export menu
        await page.click('[data-testid="export-button"], button:has-text("Export")');

        // Select format
        await page.click('[data-testid="export-{format}"]');

        // Wait for download
        const download = await page.waitForEvent('download');
        await download.saveAs('{output_path}');

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

    def connect(self, connection_string: str = None) -> dict:
        """Connect to PostgreSQL."""
        args = {}
        if connection_string:
            args["connection_string"] = connection_string
        return self.client._call_mcp("postgres", "connect", args)

    def query(self, sql: str, params: list = None) -> dict:
        """Execute a query."""
        args = {"query": sql}
        if params:
            args["params"] = params
        return self.client._call_mcp("postgres", "query", args)

    def execute(self, sql: str, params: list = None) -> dict:
        """Execute a non-query statement."""
        args = {"query": sql}
        if params:
            args["params"] = params
        return self.client._call_mcp("postgres", "execute", args)

    def init_studio_schema(self) -> dict:
        """Initialize the Studio database schema."""
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

    def save_screenplay(self, screenplay_id: str, title: str, fdx: str, fountain: str, metadata: dict) -> dict:
        """Save or update a screenplay."""
        import json
        return self.execute(
            """INSERT INTO screenplays (id, title, fdx_content, fountain_content, metadata)
               VALUES ($1, $2, $3, $4, $5)
               ON CONFLICT (id) DO UPDATE SET
                   fdx_content = $3, fountain_content = $4, metadata = $5, updated_at = NOW()""",
            [screenplay_id, title, fdx, fountain, json.dumps(metadata)]
        )

    def load_screenplay(self, screenplay_id: str) -> dict:
        """Load a screenplay."""
        return self.query("SELECT * FROM screenplays WHERE id = $1", [screenplay_id])


# =============================================================================
# Convenience Functions
# =============================================================================

def get_mcp_client() -> MCPClient:
    """Get a default MCP client instance."""
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
