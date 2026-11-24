"""MCP Integration API Routes for Pistachio's Studio."""
from pathlib import Path

from .api import HttpError, Request, route
from .log import get_logger

log = get_logger("mcp_routes")

# Import MCP client
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "sw"))
from mcp_client import (
    get_firecrawl, get_premiere, get_blender, get_playwright, get_postgres,
    MCPClient, FirecrawlMCP, PremiereMCP, BlenderMCP, PlaywrightMCP, PostgresMCP
)

# Lazy initialization
_firecrawl = None
_premiere = None
_blender = None
_playwright = None
_postgres = None

def get_fc() -> FirecrawlMCP:
    global _firecrawl
    if _firecrawl is None:
        _firecrawl = get_firecrawl()
    return _firecrawl

def get_pm() -> PremiereMCP:
    global _premiere
    if _premiere is None:
        _premiere = get_premiere()
    return _premiere

def get_bm() -> BlenderMCP:
    global _blender
    if _blender is None:
        _blender = get_blender()
    return _blender

def get_pw() -> PlaywrightMCP:
    global _playwright
    if _playwright is None:
        _playwright = get_playwright()
    return _playwright

def get_pg() -> PostgresMCP:
    global _postgres
    if _postgres is None:
        _postgres = get_postgres()
    return _postgres

def get_client() -> MCPClient:
    return MCPClient()


# =============================================================================
# Health Check - Check which MCP servers are available
# =============================================================================

@route("GET", "/api/mcp/status")
def mcp_status(r: Request):
    """Check which MCP servers are available."""
    client = get_client()
    servers = {
        "firecrawl": client.check_server("firecrawl"),
        "premiere": client.check_server("premiere"),
        "blender": client.check_server("blender"),
        "playwright": client.check_server("playwright"),
        "postgres": client.check_server("postgres"),
    }
    return {"servers": servers}


# =============================================================================
# Firecrawl Routes - Web Research
# =============================================================================

@route("POST", "/api/mcp/firecrawl/scrape")
def mcp_firecrawl_scrape(r: Request):
    """Scrape a single URL for research."""
    url = r.body.get("url", "").strip()
    if not url:
        raise HttpError(400, "url is required")
    formats = r.body.get("formats")
    result = get_fc().scrape(url, formats)
    return result


@route("POST", "/api/mcp/firecrawl/search")
def mcp_firecrawl_search(r: Request):
    """Search the web for research."""
    query = r.body.get("query", "").strip()
    if not query:
        raise HttpError(400, "query is required")
    limit = int(r.body.get("limit", 10))
    result = get_fc().search(query, limit)
    return result


@route("POST", "/api/mcp/firecrawl/research_comparables")
def mcp_firecrawl_research_comparables(r: Request):
    """Research comparable films for a genre."""
    genre = r.body.get("genre", "").strip()
    if not genre:
        raise HttpError(400, "genre is required")
    year = r.body.get("year")
    result = get_fc().research_film_comparables(genre, year)
    return result


@route("POST", "/api/mcp/firecrawl/research_screenplay")
def mcp_firecrawl_research_screenplay(r: Request):
    """Research screenplay structure for a film."""
    title = r.body.get("title", "").strip()
    if not title:
        raise HttpError(400, "title is required")
    result = get_fc().research_screenplay_structure(title)
    return result


# =============================================================================
# Premiere Pro Routes - Round-trip Integration
# =============================================================================

@route("POST", "/api/mcp/premiere/connect")
def mcp_premiere_connect(r: Request):
    """Connect to Premiere Pro."""
    result = get_pm().connect()
    return result


@route("POST", "/api/mcp/premiere/import_fdx")
def mcp_premiere_import_fdx(r: Request):
    """Import FDX file into Premiere Pro and create sequence."""
    project = r.body.get("project", "").strip()
    if not project:
        raise HttpError(400, "project is required")

    # Find the FDX file in the project's exports
    from layout import project_dir as pdir
    book_dir = pdir(project)
    exports_dir = book_dir / "exports"
    fdx_files = list(exports_dir.glob("*.fdx"))

    if not fdx_files:
        raise HttpError(404, "No .fdx file found in project exports. Export screenplay first.")

    # Use the most recent FDX
    fdx_path = max(fdx_files, key=lambda f: f.stat().st_mtime)
    project_name = r.body.get("project_name", project)

    result = get_pm().import_fdx(str(fdx_path), project_name)
    return result


@route("POST", "/api/mcp/premiere/create_sequence")
def mcp_premiere_create_sequence(r: Request):
    """Create a new sequence in Premiere Pro."""
    name = r.body.get("name", "").strip()
    if not name:
        raise HttpError(400, "name is required")
    settings = r.body.get("settings")
    result = get_pm().create_sequence(name, settings)
    return result


@route("POST", "/api/mcp/premiere/add_markers")
def mcp_premiere_add_markers(r: Request):
    """Add scene markers to Premiere Pro sequence."""
    sequence = r.body.get("sequence", "").strip()
    markers = r.body.get("markers", [])
    if not sequence:
        raise HttpError(400, "sequence is required")
    if not markers:
        raise HttpError(400, "markers array is required")
    result = get_pm().add_markers(sequence, markers)
    return result


# =============================================================================
# Blender Routes - Previs Generation
# =============================================================================

@route("POST", "/api/mcp/blender/create_scene")
def mcp_blender_create_scene(r: Request):
    """Create a Blender scene from prompt."""
    prompt = r.body.get("prompt", "").strip()
    if not prompt:
        raise HttpError(400, "prompt is required")
    output_format = r.body.get("output_format", "glb")
    result = get_bm().create_scene(prompt, output_format)
    return result


@route("POST", "/api/mcp/blender/generate_previs")
def mcp_blender_generate_previs(r: Request):
    """Generate previs for a screenplay scene."""
    project = r.body.get("project", "").strip()
    scene_id = r.body.get("scene_id", "").strip()

    if not project or not scene_id:
        raise HttpError(400, "project and scene_id are required")

    # Load the scene data
    from layout import project_dir as pdir
    import screenplay
    import adaptation as ad

    book_dir = pdir(project)
    plan = ad.load(book_dir)
    if not plan:
        raise HttpError(404, "No adaptation plan found")

    scene_data = screenplay.load_scene(book_dir, scene_id)
    if not scene_data:
        raise HttpError(404, f"Scene {scene_id} not found")

    # Build previs prompt from scene
    elements = scene_data.get("elements", [])
    action_text = " ".join([e["text"] for e in elements if e["type"] == "action"])
    characters = list({e["character"] for e in elements if e["type"] == "dialogue" and e.get("character")})

    previs_data = {
        "heading": scene_data.get("heading", ""),
        "action_summary": action_text[:500],
        "characters": characters,
        "mood": "cinematic",
        "lighting": "natural",
    }

    result = get_bm().generate_previs(previs_data)
    return result


@route("POST", "/api/mcp/blender/export_gltf")
def mcp_blender_export_gltf(r: Request):
    """Export Blender scene as GLTF."""
    scene_name = r.body.get("scene_name", "").strip()
    output_path = r.body.get("output_path", "").strip()
    if not scene_name or not output_path:
        raise HttpError(400, "scene_name and output_path are required")
    result = get_bm().export_gltf(scene_name, output_path)
    return result


# =============================================================================
# Playwright Routes - Final Draft Web Automation
# =============================================================================

@route("POST", "/api/mcp/playwright/run_script")
def mcp_playwright_run_script(r: Request):
    """Run a custom Playwright script."""
    script = r.body.get("script", "").strip()
    if not script:
        raise HttpError(400, "script is required")
    args = r.body.get("args")
    result = get_pw().run_script(script, args)
    return result


@route("POST", "/api/mcp/playwright/finaldraft_import")
def mcp_playwright_finaldraft_import(r: Request):
    """Automate FDX import into Final Draft Web."""
    project = r.body.get("project", "").strip()
    if not project:
        raise HttpError(400, "project is required")

    # Find the FDX file
    from layout import project_dir as pdir
    book_dir = pdir(project)
    exports_dir = book_dir / "exports"
    fdx_files = list(exports_dir.glob("*.fdx"))

    if not fdx_files:
        raise HttpError(404, "No .fdx file found in project exports. Export screenplay first.")

    fdx_path = max(fdx_files, key=lambda f: f.stat().st_mtime)
    project_title = r.body.get("project_title", project)

    result = get_pw().automate_finaldraft_import(str(fdx_path), project_title)
    return result


@route("POST", "/api/mcp/playwright/finaldraft_export")
def mcp_playwright_finaldraft_export(r: Request):
    """Automate export from Final Draft Web."""
    output_path = r.body.get("output_path", "").strip()
    format = r.body.get("format", "fdx")
    if not output_path:
        raise HttpError(400, "output_path is required")
    result = get_pw().automate_finaldraft_export(output_path, format)
    return result


# =============================================================================
# PostgreSQL Routes - Database Operations
# =============================================================================

@route("POST", "/api/mcp/postgres/init")
def mcp_postgres_init(r: Request):
    """Initialize Studio database schema."""
    connection_string = r.body.get("connection_string")
    result = get_pg().connect(connection_string) if connection_string else get_pg().connect()
    if "error" not in result:
        result = get_pg().init_studio_schema()
    return result


@route("POST", "/api/mcp/postgres/save_screenplay")
def mcp_postgres_save_screenplay(r: Request):
    """Save screenplay to database."""
    screenplay_id = r.body.get("screenplay_id", "").strip()
    title = r.body.get("title", "").strip()
    fdx = r.body.get("fdx", "")
    fountain = r.body.get("fountain", "")
    metadata = r.body.get("metadata", {})

    if not screenplay_id or not title:
        raise HttpError(400, "screenplay_id and title are required")

    result = get_pg().save_screenplay(screenplay_id, title, fdx, fountain, metadata)
    return result


@route("POST", "/api/mcp/postgres/load_screenplay")
def mcp_postgres_load_screenplay(r: Request):
    """Load screenplay from database."""
    screenplay_id = r.body.get("screenplay_id", "").strip()
    if not screenplay_id:
        raise HttpError(400, "screenplay_id is required")
    result = get_pg().load_screenplay(screenplay_id)
    return result


@route("POST", "/api/mcp/postgres/query")
def mcp_postgres_query(r: Request):
    """Execute a custom query."""
    sql = r.body.get("sql", "").strip()
    if not sql:
        raise HttpError(400, "sql is required")
    params = r.body.get("params", [])
    result = get_pg().query(sql, params)
    return result
