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
    """Check which MCP servers are configured and available (plus local fallback readiness)."""
    client = get_client()
    names = ("firecrawl", "premiere", "blender", "playwright", "postgres")
    servers = {name: client.check_server(name) for name in names}
    details = {name: client.server_status(name) for name in names}
    return {
        "servers": servers,
        "details": details,
        "local_fallbacks": {"premiere": True, "blender": True, "playwright": True},
    }


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


def _ensure_fdx_export(book_dir: Path) -> Path:
    """Ensure a fresh screenplay.fdx exists in `<book_dir>/exports/` (auto-exporting if needed)."""
    import screenplay_export

    exports_dir = book_dir / "exports"
    exports_dir.mkdir(parents=True, exist_ok=True)
    try:
        screenplay_export.export(book_dir, ("fdx",))
    except Exception as e:
        log.debug("Auto FDX export skipped or failed: %s", e)
    fdx_files = list(exports_dir.glob("*.fdx"))
    if not fdx_files:
        raise HttpError(404, "No screenplay found to export as .fdx. Generate or import a screenplay in Step 06 first.")
    return max(fdx_files, key=lambda f: f.stat().st_mtime)


def _write_premiere_xml(book_dir: Path, project: str) -> Path:
    """Build a valid Final Cut Pro 7 / Adobe Premiere Pro XML sequence with scene markers for direct Import."""
    import json
    from xml.sax.saxutils import escape
    import adaptation as ad
    import screenplay

    exports_dir = book_dir / "exports"
    exports_dir.mkdir(parents=True, exist_ok=True)
    xml_path = exports_dir / f"{project}_premiere.xml"

    fps = 24
    scenes_meta: list[tuple[str, str, int, str]] = []
    plan = ad.load(book_dir) or {}
    for idx, sc in enumerate(plan.get("scenes") or [], start=1):
        sid = str(sc.get("id") or f"S{idx:03d}")
        sp = screenplay.load_scene(book_dir, sid) or {}
        heading = str(sp.get("heading") or sc.get("title") or sid)
        secs = max(4, int(round(float(sc.get("seconds") or 12))))
        summary = str(sc.get("summary") or "")[:240]
        scenes_meta.append((sid, heading, secs, summary))

    if not scenes_meta:
        rd_sp = book_dir / "readin" / "screenplay.json"
        if rd_sp.is_file():
            try:
                raw = json.loads(rd_sp.read_text(encoding="utf-8")) or {}
                for idx, sc in enumerate(raw.get("scenes") or [], start=1):
                    heading = str(sc.get("heading") or f"Scene {idx}")
                    secs = max(4, int(round(float((sc.get("block") or {}).get("seconds") or 12))))
                    scenes_meta.append((f"S{idx:03d}", heading, secs, ""))
            except (OSError, ValueError):
                pass

    cursor = 0
    marker_xml: list[str] = []
    for sid, heading, secs, summary in scenes_meta:
        dur_frames = secs * fps
        marker_xml.append(
            f"      <marker>\n"
            f"        <name>{escape(f'{sid}: {heading}')}</name>\n"
            f"        <comment>{escape(summary or heading)}</comment>\n"
            f"        <in>{cursor}</in>\n"
            f"        <out>{cursor + dur_frames}</out>\n"
            f"      </marker>"
        )
        cursor += dur_frames
    total_frames = max(fps * 10, cursor)

    xml_doc = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<!DOCTYPE xmeml>\n'
        '<xmeml version="4">\n'
        '  <sequence id="pistachio-sequence-1">\n'
        f'    <name>{escape(project)} — Screenplay Breakdown</name>\n'
        f'    <duration>{total_frames}</duration>\n'
        '    <rate><timebase>24</timebase><ntsc>FALSE</ntsc></rate>\n'
        '    <media>\n'
        '      <video>\n'
        '        <format><samplecharacteristics><width>1920</width><height>1080</height></samplecharacteristics></format>\n'
        '        <track />\n'
        '      </video>\n'
        '      <audio><track /></audio>\n'
        '    </media>\n'
        + ("\n".join(marker_xml) + "\n" if marker_xml else "")
        + '  </sequence>\n'
        '</xmeml>\n'
    )
    xml_path.write_text(xml_doc, encoding="utf-8")
    return xml_path


def _write_blender_previs_script(book_dir: Path, scene_id: str, previs_data: dict) -> Path:
    """Generate a self-contained runnable Blender Python (.py) 3D previs blockout script for the scene."""
    import json

    exports_dir = book_dir / "exports"
    exports_dir.mkdir(parents=True, exist_ok=True)
    safe_sid = "".join(c for c in scene_id if c.isalnum() or c in "_-") or "scene"
    py_path = exports_dir / f"previs_{safe_sid}.py"

    heading = str(previs_data.get("heading") or scene_id)
    summary = str(previs_data.get("action_summary") or "")
    chars = [str(c) for c in (previs_data.get("characters") or []) if str(c).strip()]

    script_src = f'''"""Pistachio's Studio — 3D Previs Blockout Script for {heading}

Run directly inside Blender:
  blender --python {py_path.name}
"""
import math
import bpy

SCENE_META = {json.dumps(previs_data, indent=2, ensure_ascii=False)}

# Reset default scene
bpy.ops.wm.read_factory_settings(use_empty=True)
scene = bpy.context.scene
scene.render.resolution_x = 1920
scene.render.resolution_y = 1080
scene.render.fps = 24

# Ground plane (set floor)
bpy.ops.mesh.primitive_plane_add(size=16.0, location=(0.0, 0.0, 0.0))
floor = bpy.context.active_object
floor.name = "Set_Floor"

# Back & side architectural blockout walls
for name, loc, scale in (
    ("Back_Wall", (0.0, 4.5, 2.0), (8.0, 0.15, 2.0)),
    ("Left_Wall", (-6.0, 0.0, 2.0), (0.15, 5.0, 2.0)),
):
    bpy.ops.mesh.primitive_cube_add(size=2.0, location=loc)
    wall = bpy.context.active_object
    wall.name = name
    wall.scale = scale

# Character stand-in markers for blocking
characters = {json.dumps(chars, ensure_ascii=False)} or ["Subject_A"]
for idx, cname in enumerate(characters):
    x_pos = (idx - (len(characters) - 1) / 2.0) * 1.4
    bpy.ops.mesh.primitive_cylinder_add(radius=0.28, depth=1.65, location=(x_pos, 0.5, 0.825))
    actor = bpy.context.active_object
    actor.name = f"Actor_{{cname}}"

# Key & Fill lighting rig
bpy.ops.object.light_add(type="AREA", location=(-3.0, -3.5, 3.8))
key_light = bpy.context.active_object
key_light.name = "Key_Light"
key_light.data.energy = 350.0
key_light.rotation_euler = (math.radians(52), 0.0, math.radians(-35))

bpy.ops.object.light_add(type="AREA", location=(3.5, -2.5, 2.6))
fill_light = bpy.context.active_object
fill_light.name = "Fill_Light"
fill_light.data.energy = 120.0
fill_light.rotation_euler = (math.radians(65), 0.0, math.radians(40))

# Main 35mm cinema camera aimed at center stage
bpy.ops.object.camera_add(location=(0.0, -5.8, 1.55), rotation=(math.radians(85), 0.0, 0.0))
cam = bpy.context.active_object
cam.name = "Previs_Camera_35mm"
cam.data.lens = 35.0
scene.camera = cam

print("Loaded Pistachio's Studio Previs:", {json.dumps(heading)})
print("Action:", {json.dumps(summary[:300])})
'''
    py_path.write_text(script_src, encoding="utf-8")
    return py_path


@route("POST", "/api/mcp/premiere/import_fdx")
def mcp_premiere_import_fdx(r: Request):
    """Auto-export FDX + Premiere XML and send to Premiere Pro MCP (or return local import package if MCP is not configured)."""
    project = r.body.get("project", "").strip()
    if not project:
        raise HttpError(400, "project is required")

    from layout import project_dir as pdir

    book_dir = pdir(project, "book")
    fdx_path = _ensure_fdx_export(book_dir)
    xml_path = _write_premiere_xml(book_dir, project)
    project_name = r.body.get("project_name", project)

    pm = get_pm()
    if pm.is_configured():
        result = pm.import_fdx(str(fdx_path), project_name)
        if isinstance(result, dict) and not result.get("error"):
            return {
                **result,
                "status": "ok",
                "mode": "mcp",
                "mcp_configured": True,
                "fdx_url": f"/download/{project}/exports/{fdx_path.name}",
                "xml_url": f"/download/{project}/exports/{xml_path.name}",
                "message": f"Sent {fdx_path.name} to Premiere Pro via live MCP.",
            }
        # Fall through cleanly with the generated package + diagnostic note
        return {
            "status": "ok",
            "mode": "local_package",
            "mcp_configured": True,
            "mcp_error": str(result.get("error") or ""),
            "fdx_path": str(fdx_path),
            "xml_path": str(xml_path),
            "fdx_url": f"/download/{project}/exports/{fdx_path.name}",
            "xml_url": f"/download/{project}/exports/{xml_path.name}",
            "message": f"Premiere MCP returned an error ({result.get('error')}); generated {xml_path.name} & {fdx_path.name} for direct File → Import in Premiere Pro.",
        }

    return {
        "status": "ok",
        "mode": "local_package",
        "mcp_configured": False,
        "fdx_path": str(fdx_path),
        "xml_path": str(xml_path),
        "fdx_url": f"/download/{project}/exports/{fdx_path.name}",
        "xml_url": f"/download/{project}/exports/{xml_path.name}",
        "message": f"Exported Premiere Pro XML ({xml_path.name}) + {fdx_path.name} — ready for File → Import in Premiere Pro (configure a 'premiere' server in .mcp.json for direct MCP control).",
    }


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
    """Generate 3D previs via Blender MCP (or export a runnable Blender Python previs blockout script if MCP is not configured)."""
    import json
    import re
    from layout import project_dir as pdir
    import screenplay

    project = r.body.get("project", "").strip()
    scene_id = r.body.get("scene_id", "").strip()

    if not project or not scene_id:
        raise HttpError(400, "project and scene_id are required")

    book_dir = pdir(project, "book")
    scene_data = screenplay.load_scene(book_dir, scene_id)
    if not scene_data:
        rd_sp = book_dir / "readin" / "screenplay.json"
        if rd_sp.is_file():
            try:
                raw = json.loads(rd_sp.read_text(encoding="utf-8")) or {}
                m = re.search(r"(\d+)", scene_id)
                idx0 = (int(m.group(1)) - 1) if m else 0
                sc_list = raw.get("scenes") or []
                if 0 <= idx0 < len(sc_list):
                    scene_data = sc_list[idx0]
            except (OSError, ValueError):
                scene_data = None
    if not scene_data:
        raise HttpError(404, f"Scene {scene_id} not found")

    elements = scene_data.get("elements", [])
    action_text = " ".join(str(e.get("text") or "") for e in elements if isinstance(e, dict) and e.get("type") == "action")
    characters = sorted({str(e.get("character") or "").strip() for e in elements if isinstance(e, dict) and e.get("type") == "dialogue" and e.get("character")})

    previs_data = {
        "scene_id": scene_id,
        "heading": scene_data.get("heading", ""),
        "action_summary": action_text[:500],
        "characters": characters,
        "mood": "cinematic",
        "lighting": "natural",
    }

    script_path = _write_blender_previs_script(book_dir, scene_id, previs_data)
    script_url = f"/download/{project}/exports/{script_path.name}"

    # 1. If standalone portable Blender is installed inside Neon/.local_ai/blender, render real 3D previs PNGs, .blend & .glb right away!
    from local_runners import blender_runner

    if blender_runner.find_blender_executable() is not None and bool(r.body.get("render_headless", True)):
        try:
            rendered = blender_runner.render_scene_previs(
                book_dir,
                project,
                scene_id,
                render_animatic=bool(r.body.get("render_animatic", False)),
            )
            return {
                **rendered,
                "status": "ok",
                "mode": "blender_headless",
                "mcp_configured": get_bm().is_configured(),
                "script_path": str(script_path),
                "script_url": script_url,
                "message": (
                    f"Rendered {rendered.get('shots_rendered', 0)} 3D previs frame(s) + .blend/.glb for {scene_id} "
                    f"using standalone {rendered.get('blender_version') or 'Blender'}."
                ),
            }
        except Exception as e:
            log.warning("Headless Blender previs render failed (%s), falling back to script export", e)

    bm = get_bm()
    if bm.is_configured():
        result = bm.generate_previs(previs_data)
        if isinstance(result, dict) and not result.get("error"):
            return {
                **result,
                "status": "ok",
                "mode": "mcp",
                "mcp_configured": True,
                "script_url": script_url,
                "message": f"Generated 3D previs for {scene_id} via live Blender MCP.",
            }
        return {
            "status": "ok",
            "mode": "local_script",
            "mcp_configured": True,
            "mcp_error": str(result.get("error") or ""),
            "script_path": str(script_path),
            "script_url": script_url,
            "message": f"Blender MCP returned an error ({result.get('error')}); generated runnable Blender previs script {script_path.name} instead.",
        }

    return {
        "status": "ok",
        "mode": "local_script",
        "mcp_configured": False,
        "script_path": str(script_path),
        "script_url": script_url,
        "message": f"Generated runnable Blender 3D previs script ({script_path.name}) for {scene_id} — open in Blender (`blender --python {script_path.name}`) or add a 'blender' server in .mcp.json for live MCP.",
    }


@route("GET", "/api/v2_blender_status")
def _v2_blender_status(r: Request):
    """Return standalone portable Blender 5.4 installation & live MCP bridge status."""
    from local_runners import blender_runner

    st = blender_runner.blender_status()
    return {"status": "ok", **st, "mcp_configured": get_bm().is_configured()}


@route("POST", "/api/mcp/blender/launch_live")
def _mcp_blender_launch_live(r: Request):
    """Launch standalone portable Blender GUI with the Studio live MCP bridge addon pre-loaded."""
    from layout import project_dir as pdir
    from local_runners import blender_runner

    project = str(r.body.get("project") or "").strip()
    scene_id = str(r.body.get("scene_id") or "").strip()
    blend_path: Path | None = None
    if project and scene_id:
        pd = pdir(project, "book")
        safe_sid = "".join(c for c in scene_id.lower() if c.isalnum() or c in "_-") or "scene"
        cand = pd / "exports" / f"previs_{safe_sid}.blend"
        if cand.is_file():
            blend_path = cand
    try:
        res = blender_runner.launch_blender_live(blend_path)
    except RuntimeError as e:
        raise HttpError(400, str(e)) from e
    return {"status": "ok", **res, "message": f"Launched standalone Blender GUI (PID {res['pid']}) with Live MCP Bridge on 127.0.0.1:{res['port']}."}


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


@route("POST", "/api/mcp/trelby/open")
def mcp_trelby_open(r: Request):
    """Auto-export .fdx + .fountain and open local Trelby (substituting for Final Draft)."""
    import external_tools
    import screenplay_export
    from layout import project_dir as pdir

    project = str(r.body.get("project") or "").strip()
    if not project:
        raise HttpError(400, "project is required")

    book_dir = pdir(project, "book")
    exports_dir = book_dir / "exports"
    exports_dir.mkdir(parents=True, exist_ok=True)
    try:
        screenplay_export.export(book_dir, ("fdx", "fountain"))
    except Exception as e:
        log.debug("Auto Trelby screenplay export skipped or failed: %s", e)

    fdx_path = _ensure_fdx_export(book_dir)
    fountain_files = list(exports_dir.glob("*.fountain"))
    fountain_path = max(fountain_files, key=lambda f: f.stat().st_mtime) if fountain_files else None

    fdx_url = f"/download/{project}/exports/{fdx_path.name}"
    fountain_url = f"/download/{project}/exports/{fountain_path.name}" if fountain_path else ""

    should_launch = bool(r.body.get("launch", True))
    trelby_exe = external_tools.find_trelby_executable()
    launch_res: dict[str, object] = {"launched": False, "installed": trelby_exe is not None, "executable": str(trelby_exe or "")}
    if should_launch and trelby_exe is not None:
        try:
            launch_res = external_tools.launch_trelby(fountain_path or fdx_path)
        except OSError as e:
            launch_res = {"launched": False, "installed": True, "executable": str(trelby_exe), "error": str(e)}

    if launch_res.get("launched"):
        msg = f"Exported {fdx_path.name}" + (f" & {fountain_path.name}" if fountain_path else "") + " and opened Trelby — use File → Import in Trelby to edit, then re-import .fdx/.fountain into Studio."
        mode = "trelby_local"
    elif trelby_exe is not None:
        msg = f"Exported {fdx_path.name}" + (f" & {fountain_path.name}" if fountain_path else "") + " ready for Trelby."
        mode = "trelby_ready"
    else:
        msg = f"Exported {fdx_path.name}" + (f" & {fountain_path.name}" if fountain_path else "") + " — install Trelby (trelby.org) to launch directly from Studio."
        mode = "local_handoff"

    return {
        "status": "ok",
        "mode": mode,
        "trelby_installed": trelby_exe is not None,
        "trelby_path": str(trelby_exe or ""),
        "launched": bool(launch_res.get("launched")),
        "pid": launch_res.get("pid"),
        "fdx_path": str(fdx_path),
        "fdx_url": fdx_url,
        "fountain_path": str(fountain_path) if fountain_path else "",
        "fountain_url": fountain_url,
        "message": msg,
    }


@route("GET", "/api/external_tools")
def api_external_tools(r: Request):
    """Return detection status for all installed open-source external creative & AI tools."""
    import external_tools

    return {"status": "ok", **external_tools.detect_all_tools()}


@route("POST", "/api/external_tools/launch")
def api_external_tools_launch(r: Request):
    """Launch an allow-listed installed external GUI application."""
    import external_tools

    tool_id = str(r.body.get("tool") or "").strip().lower()
    if not tool_id:
        raise HttpError(400, "tool is required")
    try:
        res = external_tools.launch_external_tool(tool_id)
    except ValueError as e:
        raise HttpError(400, str(e)) from e
    if not res.get("launched"):
        raise HttpError(400, str(res.get("error") or f"Could not launch {tool_id}"))
    return {"status": "ok", **res}


@route("GET", "/api/github_updates")
def api_github_updates(r: Request):
    """Check installed GitHub-sourced repos & tools for updates."""
    import github_updates

    force = str(r.q("force") or "").strip().lower() in ("1", "true", "yes")
    return {"status": "ok", **github_updates.check_updates(force=force)}


@route("POST", "/api/github_updates/prefs")
def api_github_updates_prefs(r: Request):
    """Toggle GitHub update notifications ON/OFF or dismiss a version."""
    import github_updates

    notif = r.body.get("notifications_enabled")
    notif_bool = bool(notif) if notif is not None else None
    dismiss_id = str(r.body.get("dismiss_id") or "").strip() or None
    dismiss_ver = str(r.body.get("dismiss_version") or "").strip() or None
    clear_id = str(r.body.get("clear_dismiss_id") or "").strip() or None
    prefs = github_updates.set_preferences(
        notifications_enabled=notif_bool,
        dismiss_id=dismiss_id,
        dismiss_version=dismiss_ver,
        clear_dismiss_id=clear_id,
    )
    return {
        "status": "ok",
        "notifications_enabled": prefs["notifications_enabled"],
        "dismissed_versions": prefs["dismissed_versions"],
    }


@route("POST", "/api/github_updates/apply")
def api_github_updates_apply(r: Request):
    """Apply an update for a discovered installed GitHub repository or tool."""
    import github_updates

    item_id = str(r.body.get("id") or "").strip()
    if not item_id:
        raise HttpError(400, "id is required")
    try:
        res = github_updates.apply_update(item_id)
    except ValueError as e:
        raise HttpError(400, str(e)) from e
    return {"status": "ok" if res.get("ok") else "manual", **res}


@route("POST", "/api/mcp/playwright/finaldraft_import")
def mcp_playwright_finaldraft_import(r: Request):
    """Auto-export FDX and open/import via Playwright MCP (or return one-click FDX download + Final Draft handoff)."""
    project = r.body.get("project", "").strip()
    if not project:
        raise HttpError(400, "project is required")

    from layout import project_dir as pdir

    book_dir = pdir(project, "book")
    fdx_path = _ensure_fdx_export(book_dir)
    fdx_url = f"/download/{project}/exports/{fdx_path.name}"
    project_title = r.body.get("project_title", project)

    pw = get_pw()
    if pw.is_configured():
        result = pw.automate_finaldraft_import(str(fdx_path), project_title)
        if isinstance(result, dict) and not result.get("error"):
            return {
                **result,
                "status": "ok",
                "mode": "mcp",
                "mcp_configured": True,
                "fdx_url": fdx_url,
                "message": f"Opened {fdx_path.name} in Final Draft Web via live Playwright MCP.",
            }
        return {
            "status": "ok",
            "mode": "local_handoff",
            "mcp_configured": True,
            "mcp_error": str(result.get("error") or ""),
            "fdx_path": str(fdx_path),
            "fdx_url": fdx_url,
            "open_url": "https://www.finaldraft.com/",
            "message": f"Playwright MCP returned an error ({result.get('error')}); exported {fdx_path.name} ready to open in Final Draft.",
        }

    return {
        "status": "ok",
        "mode": "local_handoff",
        "mcp_configured": False,
        "fdx_path": str(fdx_path),
        "fdx_url": fdx_url,
        "open_url": "https://www.finaldraft.com/",
        "message": f"Exported {fdx_path.name} ready to import into Final Draft (add a 'playwright' server in .mcp.json for automated browser import).",
    }


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
