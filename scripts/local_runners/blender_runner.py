"""Standalone headless Blender 5.4 runner for Pistachio's Studio (100% contained inside Neon/.local_ai/blender).

Provides 4 GPU/headless production pipelines:
  1. Step 06 & Step 12 3D Previs PNGs, camera-move MP4 animatics, .blend, and .glb exports
  2. Step 17 true-scale 3D Blocking & Normalized Depth Guides (locking real-world adult/child/dog/prop scale)
  3. Step 11 multi-angle consistent 3D Set Plates (Wide, Reverse, Corner, OTS, Top-Down from one 3D room)
  4. Step 18/20 3D animated extruded Title Cards & Credits (PNG + MP4)
"""
from __future__ import annotations

import contextlib
import json
import logging
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

log = logging.getLogger("studio.blender_runner")

REPO_ROOT = Path(__file__).resolve().parents[2]
STANDALONE_BLENDER_DIR = REPO_ROOT / ".local_ai" / "blender"

_DOG_WORDS = ("dog", "labrador", "puppy", "hound", "retriever", "terrier", "poodle", "beagle", "canine")
_CHILD_WORDS = ("boy", "girl", "child", "kid", "toddler", "5-year-old", "4-year-old", "3-year-old", "waist-high")
_TOY_WORDS = ("action figure", "rag doll", "stuffed", "plush", "toy", "foot-tall", "doll")


def find_blender_executable() -> Path | None:
    """Locate portable Blender inside Neon/.local_ai/blender first, then BLENDER_BIN, then PATH."""
    candidates: list[Path] = []
    if sys.platform == "win32":
        candidates.append(STANDALONE_BLENDER_DIR / "blender.exe")
    else:
        candidates.append(STANDALONE_BLENDER_DIR / "blender")
    env_bin = os.environ.get("BLENDER_BIN", "").strip()
    if env_bin:
        candidates.append(Path(env_bin))
    for p in candidates:
        if p.is_file():
            return p
    found = shutil.which("blender")
    return Path(found) if found else None


def find_ffmpeg_executable() -> str | None:
    """Locate FFmpeg from PATH or bundled imageio-ffmpeg inside Neon's venv."""
    exe = shutil.which("ffmpeg")
    if exe:
        return exe
    with contextlib.suppress(Exception):
        import imageio_ffmpeg

        p = imageio_ffmpeg.get_ffmpeg_exe()
        if p and Path(p).is_file():
            return str(p)
    return None


def blender_status() -> dict[str, Any]:
    exe = find_blender_executable()
    version = ""
    if exe is not None:
        try:
            r = subprocess.run([str(exe), "--version"], stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=10)
            if r.returncode == 0:
                version = (r.stdout.splitlines()[0] if r.stdout else "").strip()
        except (OSError, subprocess.SubprocessError):
            version = ""
    return {
        "installed": exe is not None,
        "executable": str(exe) if exe else "",
        "standalone_dir": str(STANDALONE_BLENDER_DIR),
        "is_standalone": bool(exe and STANDALONE_BLENDER_DIR.resolve() in exe.resolve().parents),
        "version": version,
    }


def _safe_slug(name: str, fallback: str = "item") -> str:
    s = re.sub(r"[^a-zA-Z0-9_-]+", "_", str(name or "").strip().lower()).strip("_")
    return s[:64] or fallback


def _classify_character_spec(name: str, token: str) -> dict[str, Any]:
    """Map Continuity Book token to realistic metric height, silhouette kind, and wardrobe tint."""
    low = f"{name} {token}".lower()
    if any(w in low for w in _TOY_WORDS):
        kind, height_m = "toy", 0.30
    elif any(w in low for w in _DOG_WORDS):
        kind, height_m = "dog", 0.62
    elif any(w in low for w in _CHILD_WORDS):
        kind, height_m = "child", 1.07
    else:
        kind, height_m = "adult", 1.68

    # Pick a clean readable wardrobe tint for the blocking figure
    color = (0.35, 0.50, 0.72)
    if kind == "dog":
        color = (0.84, 0.70, 0.42) if any(w in low for w in ("yellow", "golden", "cream", "tan")) else (0.45, 0.32, 0.22)
    elif "red" in low or "crimson" in low:
        color = (0.78, 0.20, 0.18)
    elif "blue" in low or "navy" in low or "denim" in low:
        color = (0.18, 0.36, 0.72)
    elif "green" in low or "olive" in low:
        color = (0.20, 0.56, 0.30)
    elif "yellow" in low or "gold" in low:
        color = (0.85, 0.70, 0.18)
    elif "purple" in low or "violet" in low:
        color = (0.54, 0.28, 0.68)
    elif "brown" in low or "tan" in low:
        color = (0.50, 0.34, 0.22)
    elif "pink" in low or "coral" in low:
        color = (0.82, 0.42, 0.52)
    return {"name": name, "kind": kind, "height_m": height_m, "color": color}


def _infer_room_features(heading: str, set_description: str, props: list[str]) -> dict[str, Any]:
    blob = f"{heading} {set_description} {' '.join(props)}".lower()
    has_coffee_table = ("coffee table" in blob) and not bool(
        re.search(r"\b(?:no|without|missing|absent)\s+(?:a\s+)?coffee\s+table\b", blob)
    )
    return {
        "is_exterior": heading.strip().upper().startswith("EXT."),
        "is_space": any(w in blob for w in ("saturn", "titan", "moon", "space", "cockpit", "spaceship", "rocket", "orbit")),
        "has_sofa": any(w in blob for w in ("sofa", "couch", "living room")),
        "has_dining_table": any(w in blob for w in ("dining table", "round wooden table", "round table", "kitchen table", "table")) and not has_coffee_table,
        "has_coffee_table": has_coffee_table,
        "has_tv": any(w in blob for w in ("tv", "television", "console", "entertainment")),
        "has_window": any(w in blob for w in ("window", "pane", "daylight", "outside")) and "no window" not in blob,
        "has_doorway": any(w in blob for w in ("door", "doorway", "hallway", "kitchen", "threshold", "entry")),
        "has_bed": "bedroom" in blob or " bed" in blob,
        "has_box": "box" in blob or "cardboard" in blob,
        "has_mug": any(w in blob for w in ("mug", "cup", "tea")),
        "has_bowl": any(w in blob for w in ("dog bowl", "food bowl", "water bowl", "bowl")),
    }


def _load_project_scene_context(pd: Path, scene_id: str) -> dict[str, Any]:
    """Load screenplay scene, Step 12 shots, Step 07 characters, and Step 11 locked set description."""
    import continuity_book
    import screenplay
    import shot_list

    book = continuity_book.load(pd) or {}
    sl = shot_list.load(pd) or {}
    sc_sl = next((s for s in (sl.get("scenes") or []) if str(s.get("id") or "").upper() == scene_id.upper()), None)
    sc_sp = screenplay.load_scene(pd, scene_id)

    if sc_sp is None and (pd / "readin" / "screenplay.json").is_file():
        with contextlib.suppress(OSError, ValueError):
            raw = json.loads((pd / "readin" / "screenplay.json").read_text(encoding="utf-8")) or {}
            m = re.search(r"(\d+)", scene_id)
            idx0 = (int(m.group(1)) - 1) if m else 0
            sc_list = raw.get("scenes") or []
            if 0 <= idx0 < len(sc_list):
                sc_sp = sc_list[idx0]

    heading = str((sc_sl or {}).get("heading") or (sc_sp or {}).get("heading") or f"INT. {scene_id} - DAY")
    shots: list[dict[str, Any]] = list((sc_sl or {}).get("shots") or [])
    if not shots:
        els = (sc_sp or {}).get("elements") or []
        action_txt = " ".join(str(e.get("text") or "") for e in els if isinstance(e, dict) and e.get("type") == "action")
        chars_sp = sorted({str(e.get("character") or "").strip() for e in els if isinstance(e, dict) and e.get("type") == "dialogue" and e.get("character")})
        shots = [{
            "n": 1,
            "type": "WS",
            "lens_mm": 35,
            "height": "eye",
            "angle": "straight",
            "movement": "static",
            "composition": action_txt[:240] or heading,
            "action": action_txt[:240] or heading,
            "characters": chars_sp,
            "props": [],
            "seconds": 4.0,
        }]

    # Match Step 11 sets_custom.json or Step 07 location description
    set_desc = str((sc_sl or {}).get("set_visual_description") or "")
    set_light = str((sc_sl or {}).get("set_lighting") or "")
    if not set_desc and (pd / "sets_custom.json").is_file():
        with contextlib.suppress(OSError, ValueError):
            sc_custom = json.loads((pd / "sets_custom.json").read_text(encoding="utf-8")) or {}
            if isinstance(sc_custom, dict):
                h_low = heading.lower()
                for sk, sv in sc_custom.items():
                    if isinstance(sv, dict) and sk and sk.lower() in h_low:
                        set_desc = str(sv.get("description") or "")
                        set_light = str(sv.get("lighting") or set_light)
                        break
    if not set_desc:
        for loc in book.get("locations") or []:
            if isinstance(loc, dict) and str(loc.get("name") or "").lower() in heading.lower():
                set_desc = str(loc.get("token") or "")
                break

    char_tokens: dict[str, str] = {}
    for ch in book.get("characters") or []:
        if isinstance(ch, dict) and ch.get("name"):
            char_tokens[str(ch["name"]).strip().lower()] = str(ch.get("token") or "")

    return {
        "scene_id": scene_id,
        "heading": heading,
        "shots": shots,
        "set_description": set_desc,
        "set_lighting": set_light,
        "char_tokens": char_tokens,
    }


def _run_blender_python(script_src: str, *, work_dir: Path, timeout: float = 240.0) -> subprocess.CompletedProcess[str]:
    exe = find_blender_executable()
    if exe is None:
        raise RuntimeError(
            f"Portable Blender executable not found in {STANDALONE_BLENDER_DIR}. "
            "Place Blender inside .local_ai/blender/ or set BLENDER_BIN."
        )
    work_dir.mkdir(parents=True, exist_ok=True)
    tmp_py: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=work_dir,
            prefix="_blender_job_",
            suffix=".py",
            delete=False,
        ) as fh:
            tmp_py = Path(fh.name)
            fh.write(script_src)
        proc = subprocess.run(
            [str(exe), "--background", "--factory-startup", "--python-exit-code", "1", "--python", str(tmp_py)],
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            cwd=str(REPO_ROOT),
        )
        if proc.returncode != 0:
            tail = ((proc.stderr or "") + "\n" + (proc.stdout or "")).strip()[-800:]
            raise RuntimeError(f"Blender exited with code {proc.returncode}: {tail}")
        return proc
    finally:
        if tmp_py is not None:
            tmp_py.unlink(missing_ok=True)


# Shared Blender 5.4 bpy helper snippet injected into generated scripts
_BPY_COMMON_HELPERS = r'''
import math
import bpy
from mathutils import Vector

def _configure_render(scene, width, height, samples=16):
    scene.render.engine = "BLENDER_EEVEE"
    scene.render.resolution_x = int(width)
    scene.render.resolution_y = int(height)
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGBA"
    if hasattr(scene, "eevee"):
        if hasattr(scene.eevee, "taa_render_samples"):
            scene.eevee.taa_render_samples = int(samples)
    scene.view_settings.view_transform = "Standard"

def _make_mat(name, rgba, roughness=0.65, metallic=0.0, emission=0.0):
    mat = bpy.data.materials.new(name=name)
    mat.use_nodes = True
    nt = mat.node_tree
    bsdf = next((n for n in nt.nodes if n.type == "BSDF_PRINCIPLED"), None)
    if bsdf:
        bsdf.inputs["Base Color"].default_value = (rgba[0], rgba[1], rgba[2], 1.0)
        if "Roughness" in bsdf.inputs:
            bsdf.inputs["Roughness"].default_value = float(roughness)
        if "Metallic" in bsdf.inputs:
            bsdf.inputs["Metallic"].default_value = float(metallic)
        if emission > 0 and "Emission Strength" in bsdf.inputs:
            bsdf.inputs["Emission Color"].default_value = (rgba[0], rgba[1], rgba[2], 1.0)
            bsdf.inputs["Emission Strength"].default_value = float(emission)
    return mat

def _make_depth_override_mat(near_m=0.6, far_m=12.0):
    mat = bpy.data.materials.new(name="Studio_Depth_Override")
    mat.use_nodes = True
    nt = mat.node_tree
    nt.nodes.clear()
    cam_data = nt.nodes.new("ShaderNodeCameraData")
    map_r = nt.nodes.new("ShaderNodeMapRange")
    map_r.clamp = True
    map_r.inputs["From Min"].default_value = float(near_m)
    map_r.inputs["From Max"].default_value = float(far_m)
    map_r.inputs["To Min"].default_value = 1.0   # near = bright white
    map_r.inputs["To Max"].default_value = 0.05  # far = dark grey
    emit = nt.nodes.new("ShaderNodeEmission")
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    nt.links.new(cam_data.outputs["View Z Depth"], map_r.inputs["Value"])
    nt.links.new(map_r.outputs["Result"], emit.inputs["Color"])
    nt.links.new(emit.outputs["Emission"], out.inputs["Surface"])
    return mat

def _assign_mat(obj, mat):
    if obj.data.materials:
        obj.data.materials[0] = mat
    else:
        obj.data.materials.append(mat)

def _add_box(name, loc, size_xyz, mat):
    bpy.ops.mesh.primitive_cube_add(size=1.0, location=loc)
    obj = bpy.context.active_object
    obj.name = name
    obj.scale = (size_xyz[0], size_xyz[1], size_xyz[2])
    _assign_mat(obj, mat)
    return obj

def _add_cyl(name, loc, radius, depth, mat, rot=(0.0, 0.0, 0.0)):
    bpy.ops.mesh.primitive_cylinder_add(vertices=24, radius=radius, depth=depth, location=loc, rotation=rot)
    obj = bpy.context.active_object
    obj.name = name
    _assign_mat(obj, mat)
    return obj

def _add_sphere(name, loc, radius, mat):
    bpy.ops.mesh.primitive_uv_sphere_add(segments=20, ring_count=12, radius=radius, location=loc)
    obj = bpy.context.active_object
    obj.name = name
    _assign_mat(obj, mat)
    return obj

def _build_room(features):
    m_floor = _make_mat("Floor", (0.42, 0.31, 0.21), roughness=0.75)
    m_rug = _make_mat("Rug", (0.58, 0.54, 0.48), roughness=0.92)
    m_wall = _make_mat("Wall", (0.76, 0.72, 0.65), roughness=0.85)
    m_wood = _make_mat("Wood", (0.36, 0.23, 0.14), roughness=0.55)
    m_sofa = _make_mat("Sofa", (0.28, 0.19, 0.14), roughness=0.88)
    m_tv = _make_mat("TV", (0.04, 0.05, 0.07), roughness=0.25)
    m_glass = _make_mat("Window", (0.55, 0.68, 0.80), roughness=0.1, emission=0.6)

    if features.get("is_space"):
        m_space_floor = _make_mat("LunarFloor", (0.32, 0.34, 0.40), roughness=0.9)
        _add_box("Ground_Surface", (0.0, 0.0, -0.05), (24.0, 24.0, 0.1), m_space_floor)
        # Orbiting ringed planet in the distance
        m_planet = _make_mat("Saturn", (0.82, 0.72, 0.52), roughness=0.5, emission=0.25)
        _add_sphere("Saturn_Body", (4.5, 16.0, 6.0), 2.4, m_planet)
        bpy.ops.mesh.primitive_torus_add(major_radius=4.0, minor_radius=0.18, location=(4.5, 16.0, 6.0), rotation=(math.radians(72), math.radians(18), 0.0))
        ring = bpy.context.active_object
        ring.name = "Saturn_Rings"
        ring.scale = (1.0, 1.0, 0.08)
        _assign_mat(ring, _make_mat("RingMat", (0.88, 0.80, 0.64), roughness=0.4, emission=0.2))
        return

    # Standard interior room: 7m wide x 6m deep x 2.75m ceiling
    _add_box("Room_Floor", (0.0, 0.0, -0.05), (7.6, 6.8, 0.10), m_floor)
    if not features.get("is_exterior"):
        _add_box("Room_Rug", (0.0, 0.2, 0.01), (3.4, 2.5, 0.02), m_rug)
        _add_box("Back_Wall", (0.0, 3.3, 1.4), (7.6, 0.15, 2.8), m_wall)
        _add_box("Left_Wall", (-3.7, 0.0, 1.4), (0.15, 6.8, 2.8), m_wall)
        _add_box("Right_Wall", (3.7, 0.0, 1.4), (0.15, 6.8, 2.8), m_wall)
        _add_box("Ceiling", (0.0, 0.0, 2.82), (7.6, 6.8, 0.12), m_wall)

    if features.get("has_window"):
        _add_box("Window_Frame", (-3.6, 0.6, 1.55), (0.12, 1.8, 1.35), m_glass)
    if features.get("has_doorway"):
        _add_box("Kitchen_Doorway_Arch", (2.6, 3.22, 1.15), (1.15, 0.12, 2.3), _make_mat("DoorOpening", (0.20, 0.18, 0.16)))
    if features.get("has_sofa"):
        _add_box("Sofa_Base", (-1.1, 2.25, 0.24), (2.2, 0.90, 0.48), m_sofa)
        _add_box("Sofa_Back", (-1.1, 2.62, 0.62), (2.2, 0.22, 0.56), m_sofa)
    if features.get("has_tv"):
        _add_box("TV_Console", (-2.9, -0.4, 0.35), (0.50, 1.55, 0.70), m_wood)
        _add_box("Wall_TV", (-3.58, -0.4, 1.45), (0.08, 1.35, 0.78), m_tv)
    if features.get("has_dining_table"):
        _add_cyl("Dining_Table_Top", (2.05, -0.75, 0.74), 0.62, 0.05, m_wood)
        _add_cyl("Dining_Table_Pedestal", (2.05, -0.75, 0.37), 0.11, 0.74, m_wood)
    if features.get("has_coffee_table"):
        _add_box("Coffee_Table", (-1.0, 0.85, 0.22), (1.1, 0.60, 0.44), m_wood)
    if features.get("has_bed"):
        _add_box("Bed_Frame", (-1.2, 1.6, 0.28), (1.9, 2.1, 0.56), _make_mat("Bed", (0.45, 0.52, 0.68)))
    if features.get("has_mug"):
        mug_loc = (1.88, -0.62, 0.82) if features.get("has_dining_table") else ((-0.8, 0.85, 0.49) if features.get("has_coffee_table") else (0.6, 0.4, 0.06))
        _add_cyl("Prop_Tea_Mug", mug_loc, 0.045, 0.10, _make_mat("Mug", (0.94, 0.93, 0.90), roughness=0.2))
    if features.get("has_bowl"):
        _add_cyl("Prop_Dog_Bowl", (2.55, 2.75, 0.045), 0.11, 0.08, _make_mat("SteelBowl", (0.75, 0.77, 0.80), roughness=0.25, metallic=0.85))
    if features.get("has_box"):
        _add_box("Prop_Cardboard_Box", (-0.15, 0.35, 0.24), (0.55, 0.45, 0.48), _make_mat("Cardboard", (0.64, 0.49, 0.31), roughness=0.9))

def _build_character(spec, loc_xy):
    name = spec["name"]
    kind = spec["kind"]
    h = float(spec["height_m"])
    col = spec["color"]
    m_body = _make_mat(f"Mat_{name}", col, roughness=0.6)
    m_skin = _make_mat(f"Skin_{name}", (0.86, 0.72, 0.60) if kind != "dog" else col, roughness=0.6)
    x, y = float(loc_xy[0]), float(loc_xy[1])

    if kind == "dog":
        # Quadruped dog silhouette: shoulder height ~0.62m
        _add_box(f"{name}_Torso", (x, y, h * 0.62), (0.30, 0.72, 0.28), m_body)
        _add_sphere(f"{name}_Head", (x, y - 0.40, h * 0.88), 0.13, m_body)
        for lx, ly in ((-0.10, -0.24), (0.10, -0.24), (-0.10, 0.24), (0.10, 0.24)):
            _add_cyl(f"{name}_Leg", (x + lx, y + ly, h * 0.28), 0.04, h * 0.56, m_body)
        return Vector((x, y, h * 0.70))

    # Bipedal humanoid figure (adult 1.68m, child 1.07m, toy 0.30m)
    leg_h = h * 0.46
    torso_h = h * 0.34
    head_r = h * 0.085
    w_scale = max(0.12, h * 0.14)
    _add_cyl(f"{name}_LegL", (x - w_scale * 0.45, y, leg_h * 0.5), w_scale * 0.32, leg_h, _make_mat(f"Pants_{name}", (0.18, 0.24, 0.38)))
    _add_cyl(f"{name}_LegR", (x + w_scale * 0.45, y, leg_h * 0.5), w_scale * 0.32, leg_h, _make_mat(f"Pants_{name}_R", (0.18, 0.24, 0.38)))
    _add_box(f"{name}_Torso", (x, y, leg_h + torso_h * 0.5), (w_scale * 1.9, w_scale * 0.95, torso_h), m_body)
    _add_sphere(f"{name}_Head", (x, y, leg_h + torso_h + head_r * 1.1), head_r, m_skin)
    return Vector((x, y, leg_h + torso_h * 0.8))

def _setup_lighting(is_space=False):
    world = bpy.context.scene.world
    if world is None:
        world = bpy.data.worlds.new("World")
        bpy.context.scene.world = world
    world.use_nodes = True
    bg = next((n for n in world.node_tree.nodes if n.type == "BACKGROUND"), None)
    if bg:
        bg.inputs["Color"].default_value = (0.02, 0.03, 0.06, 1.0) if is_space else (0.16, 0.18, 0.22, 1.0)
        bg.inputs["Strength"].default_value = 0.45 if is_space else 0.75

    bpy.ops.object.light_add(type="AREA", location=(-2.2, -2.6, 2.4))
    key = bpy.context.active_object
    key.name = "Key_Light"
    key.data.energy = 260.0 if not is_space else 420.0
    key.data.size = 2.0
    key.rotation_euler = (math.radians(52), 0.0, math.radians(-30))

    bpy.ops.object.light_add(type="AREA", location=(2.6, -1.8, 2.2))
    fill = bpy.context.active_object
    fill.name = "Fill_Light"
    fill.data.energy = 110.0
    fill.data.size = 2.5
    fill.rotation_euler = (math.radians(60), 0.0, math.radians(38))

def _aim_camera(cam, cam_pos, target_pos, lens_mm=35.0):
    cam.location = Vector(cam_pos)
    cam.data.lens = float(lens_mm)
    direction = Vector(target_pos) - Vector(cam_pos)
    rot_quat = direction.to_track_quat("-Z", "Y")
    cam.rotation_euler = rot_quat.to_euler()
'''


def _camera_height_m(height_str: str) -> float:
    h = str(height_str or "eye").strip().lower()
    return {
        "ground": 0.28,
        "low": 0.75,
        "eye": 1.38,
        "shoulder": 1.48,
        "high": 2.15,
        "overhead": 2.60,
    }.get(h, 1.38)


def _camera_dist_m(shot_type: str) -> float:
    t = str(shot_type or "MS").strip().upper()
    return {
        "ELS": 5.2,
        "WS": 4.2,
        "LS": 3.8,
        "MLS": 3.1,
        "MS": 2.5,
        "TWO SHOT": 2.7,
        "GROUP": 3.5,
        "MCU": 1.75,
        "CU": 1.25,
        "ECU": 0.85,
        "INSERT": 1.1,
        "OTS": 2.2,
        "POV": 1.6,
    }.get(t, 2.6)


# ==============================================================================
# 1. HEADLESS 3D PREVIS PNGs, .BLEND, .GLB & CAMERA-MOVE MP4 ANIMATIC
# ==============================================================================
def render_scene_previs(
    pd: Path,
    slug: str,
    scene_id: str,
    *,
    render_animatic: bool = False,
    width: int = 960,
    height: int = 540,
    max_shots: int = 12,
) -> dict[str, Any]:
    """Render headless Blender 3D previs stills, .blend, .glb, and optional camera-move MP4 animatic for a scene."""
    ctx = _load_project_scene_context(pd, scene_id)
    shots = ctx["shots"][:max_shots]
    all_props = [str(p) for s in shots for p in (s.get("props") or [])]
    features = _infer_room_features(ctx["heading"], ctx["set_description"], all_props)

    # Unique characters appearing in scene
    seen_chars: dict[str, dict[str, Any]] = {}
    for s in shots:
        for ch in s.get("characters") or []:
            cn = str(ch).strip()
            if cn and cn.lower() not in seen_chars:
                seen_chars[cn.lower()] = _classify_character_spec(cn, ctx["char_tokens"].get(cn.lower(), ""))
    char_specs = list(seen_chars.values())

    safe_sid = _safe_slug(scene_id, "scene")
    previs_dir = pd / "assets" / "previs"
    exports_dir = pd / "exports"
    previs_dir.mkdir(parents=True, exist_ok=True)
    exports_dir.mkdir(parents=True, exist_ok=True)

    overview_png = exports_dir / f"previs_{safe_sid}.png"
    blend_path = exports_dir / f"previs_{safe_sid}.blend"
    glb_path = exports_dir / f"previs_{safe_sid}.glb"
    anim_frames_dir = previs_dir / f"_anim_{safe_sid}"

    shot_specs: list[dict[str, Any]] = []
    for idx, s in enumerate(shots, start=1):
        n = int(s.get("n") or idx)
        out_png = previs_dir / f"{safe_sid}_sh{n:02d}_previs.png"
        shot_specs.append({
            "n": n,
            "type": str(s.get("type") or "MS"),
            "lens_mm": int(s.get("lens_mm") or 35),
            "height_m": _camera_height_m(str(s.get("height") or "eye")),
            "dist_m": _camera_dist_m(str(s.get("type") or "MS")),
            "movement": str(s.get("movement") or "static").lower(),
            "seconds": max(1.5, min(6.0, float(s.get("seconds") or 3.0))),
            "characters": [str(c).strip() for c in (s.get("characters") or []) if str(c).strip()],
            "out_png": str(out_png),
        })

    script_src = (
        _BPY_COMMON_HELPERS
        + f"""
FEATURES = {repr(features)}
CHAR_SPECS = {repr(char_specs)}
SHOT_SPECS = {repr(shot_specs)}
OVERVIEW_PNG = {repr(str(overview_png))}
BLEND_PATH = {repr(str(blend_path))}
GLB_PATH = {repr(str(glb_path))}
RENDER_ANIMATIC = {repr(bool(render_animatic))}
ANIM_DIR = {repr(str(anim_frames_dir))}

bpy.ops.wm.read_factory_settings(use_empty=True)
scene = bpy.context.scene
_configure_render(scene, {int(width)}, {int(height)}, samples=12)
_build_room(FEATURES)
_setup_lighting(is_space=bool(FEATURES.get("is_space")))

char_targets = {{}}
n_chars = len(CHAR_SPECS)
for idx, spec in enumerate(CHAR_SPECS):
    x_pos = (idx - (n_chars - 1) / 2.0) * 1.15
    y_pos = 0.55 if spec["kind"] != "dog" else 0.05
    char_targets[spec["name"].lower()] = _build_character(spec, (x_pos, y_pos))

bpy.ops.object.camera_add(location=(0.0, -3.4, 1.45))
cam = bpy.context.active_object
cam.name = "Previs_Camera"
scene.camera = cam

# Save interactive .blend and .glb first
bpy.ops.wm.save_as_mainfile(filepath=BLEND_PATH)
try:
    bpy.ops.export_scene.gltf(filepath=GLB_PATH, export_format="GLB")
except Exception as _ge:
    print("GLB export skipped:", _ge)

import os
frame_counter = 1
if RENDER_ANIMATIC:
    os.makedirs(ANIM_DIR, exist_ok=True)

for idx, sh in enumerate(SHOT_SPECS):
    names = [c.lower() for c in sh["characters"] if c.lower() in char_targets]
    if names:
        tgt = sum((char_targets[c] for c in names), Vector((0.0, 0.0, 0.0))) / float(len(names))
    else:
        tgt = Vector((0.0, 0.5, 1.05))
    angle_rad = ((idx % 5) - 2) * 0.24
    dist = float(sh["dist_m"])
    cam_x = tgt.x + math.sin(angle_rad) * dist
    cam_y = max(-3.1, tgt.y - math.cos(angle_rad) * dist)
    cam_z = min(2.55, max(0.28, float(sh["height_m"])))
    _aim_camera(cam, (cam_x, cam_y, cam_z), tgt, lens_mm=sh["lens_mm"])
    scene.render.filepath = sh["out_png"]
    bpy.ops.render.render(write_still=True)
    if idx == 0:
        scene.render.filepath = OVERVIEW_PNG
        bpy.ops.render.render(write_still=True)

    if RENDER_ANIMATIC:
        # Render 8 smooth camera-motion keyframes per shot (encoded at 8 fps -> smooth animatic)
        steps = 8
        mv = sh["movement"]
        for st_i in range(steps):
            t = st_i / max(1, steps - 1)
            dx, dy, dz = 0.0, 0.0, 0.0
            tx_off, tz_off = 0.0, 0.0
            if "push" in mv or "dolly in" in mv:
                dy = 0.65 * t
            elif "pull" in mv or "dolly out" in mv:
                dy = -0.65 * t
            elif "pan" in mv:
                tx_off = -0.45 + 0.90 * t
            elif "tilt" in mv:
                tz_off = -0.25 + 0.50 * t
            elif "truck" in mv or "track" in mv:
                dx = -0.45 + 0.90 * t
            elif "crane" in mv:
                dz = 0.55 * t
            _aim_camera(
                cam,
                (cam_x + dx, max(-3.1, cam_y + dy), min(2.6, max(0.25, cam_z + dz))),
                (tgt.x + tx_off, tgt.y, tgt.z + tz_off),
                lens_mm=sh["lens_mm"],
            )
            scene.render.filepath = os.path.join(ANIM_DIR, f"f_{{frame_counter:05d}}.png")
            bpy.ops.render.render(write_still=True)
            frame_counter += 1
"""
    )

    _run_blender_python(script_src, work_dir=previs_dir, timeout=240.0)

    rendered_shots: list[dict[str, Any]] = []
    for sh in shot_specs:
        p = Path(sh["out_png"])
        if p.is_file():
            rendered_shots.append({
                "n": sh["n"],
                "shot_id": f"{scene_id}-{sh['n']:02d}",
                "image_url": f"/file/{slug}/assets/previs/{p.name}",
                "path": str(p),
            })

    animatic_url = ""
    animatic_path = exports_dir / f"previs_{safe_sid}_animatic.mp4"
    if render_animatic and anim_frames_dir.is_dir():
        ffmpeg = find_ffmpeg_executable()
        if ffmpeg and any(anim_frames_dir.glob("f_*.png")):
            try:
                subprocess.run(
                    [
                        ffmpeg,
                        "-y",
                        "-framerate",
                        "4",
                        "-i",
                        str(anim_frames_dir / "f_%05d.png"),
                        "-c:v",
                        "libx264",
                        "-pix_fmt",
                        "yuv420p",
                        "-r",
                        "24",
                        str(animatic_path),
                    ],
                    stdin=subprocess.DEVNULL,
                    capture_output=True,
                    check=True,
                    timeout=90,
                )
                if animatic_path.is_file():
                    animatic_url = f"/download/{slug}/exports/{animatic_path.name}"
            except (OSError, subprocess.SubprocessError) as e:
                log.warning("Animatic FFmpeg encode failed: %s", e)
        shutil.rmtree(anim_frames_dir, ignore_errors=True)

    return {
        "ok": True,
        "scene_id": scene_id,
        "heading": ctx["heading"],
        "shots_rendered": len(rendered_shots),
        "shots": rendered_shots,
        "overview_url": f"/file/{slug}/assets/previs/{Path(shot_specs[0]['out_png']).name}" if rendered_shots else "",
        "overview_download_url": f"/download/{slug}/exports/{overview_png.name}" if overview_png.is_file() else "",
        "blend_url": f"/download/{slug}/exports/{blend_path.name}" if blend_path.is_file() else "",
        "glb_url": f"/download/{slug}/exports/{glb_path.name}" if glb_path.is_file() else "",
        "animatic_url": animatic_url,
        "animatic_file_url": f"/file/{slug}/exports/{animatic_path.name}" if animatic_url else "",
        "blender_version": blender_status().get("version", ""),
    }


# ==============================================================================
# 2. TRUE-SCALE DEPTH & SPATIAL BLOCKING GUIDES (STEP 17 KEYFRAMES)
# ==============================================================================
def render_shot_depth_guide(
    pd: Path,
    slug: str,
    shot_id: str,
    *,
    width: int = 1024,
    height: int = 576,
) -> dict[str, Any]:
    """Render true-scale 3D Blocking PNG + Normalized Linear Depth Map PNG for a Step 17 keyframe."""
    parts = shot_id.split("-")
    scene_id = parts[0] if parts else "S001"
    shot_n = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 1

    ctx = _load_project_scene_context(pd, scene_id)
    shot = next((s for s in ctx["shots"] if int(s.get("n") or 0) == shot_n), None)
    if shot is None:
        shot = ctx["shots"][0]

    props = [str(p) for p in (shot.get("props") or [])]
    features = _infer_room_features(ctx["heading"], f"{ctx['set_description']} {shot.get('composition', '')}", props)
    char_specs = [
        _classify_character_spec(str(c).strip(), ctx["char_tokens"].get(str(c).strip().lower(), ""))
        for c in (shot.get("characters") or [])
        if str(c).strip()
    ]

    guides_dir = pd / "assets" / "previs" / "guides"
    guides_dir.mkdir(parents=True, exist_ok=True)
    safe_sid = _safe_slug(shot_id, "shot")
    blocking_png = guides_dir / f"{safe_sid}_blocking.png"
    depth_png = guides_dir / f"{safe_sid}_depth.png"

    lens_mm = int(shot.get("lens_mm") or 35)
    cam_h = _camera_height_m(str(shot.get("height") or "eye"))
    dist = _camera_dist_m(str(shot.get("type") or "MS"))

    script_src = (
        _BPY_COMMON_HELPERS
        + f"""
FEATURES = {repr(features)}
CHAR_SPECS = {repr(char_specs)}
BLOCKING_PNG = {repr(str(blocking_png))}
DEPTH_PNG = {repr(str(depth_png))}

bpy.ops.wm.read_factory_settings(use_empty=True)
scene = bpy.context.scene
_configure_render(scene, {int(width)}, {int(height)}, samples=16)
_build_room(FEATURES)
_setup_lighting(is_space=bool(FEATURES.get("is_space")))

targets = []
n_chars = len(CHAR_SPECS)
for idx, spec in enumerate(CHAR_SPECS):
    x_pos = (idx - (n_chars - 1) / 2.0) * 1.15
    y_pos = 0.55 if spec["kind"] != "dog" else 0.05
    targets.append(_build_character(spec, (x_pos, y_pos)))

tgt = sum(targets, Vector((0.0, 0.0, 0.0))) / float(len(targets)) if targets else Vector((0.0, 0.5, 1.05))
cam_pos = (tgt.x, max(-3.1, tgt.y - {dist:.2f}), min(2.55, max(0.28, {cam_h:.2f})))

bpy.ops.object.camera_add(location=cam_pos)
cam = bpy.context.active_object
cam.name = "Guide_Camera"
scene.camera = cam
_aim_camera(cam, cam_pos, tgt, lens_mm={lens_mm})

# 1. Color-coded true-scale blocking guide
scene.render.filepath = BLOCKING_PNG
bpy.ops.render.render(write_still=True)

# 2. Normalized linear depth map via material_override (Blender 4.x/5.x/6.0 safe)
depth_mat = _make_depth_override_mat(near_m=0.5, far_m=10.5)
scene.view_layers[0].material_override = depth_mat
if scene.world and scene.world.use_nodes:
    bg = next((n for n in scene.world.node_tree.nodes if n.type == "BACKGROUND"), None)
    if bg:
        bg.inputs["Color"].default_value = (0.0, 0.0, 0.0, 1.0)
        bg.inputs["Strength"].default_value = 0.0
scene.render.filepath = DEPTH_PNG
bpy.ops.render.render(write_still=True)
"""
    )

    _run_blender_python(script_src, work_dir=guides_dir, timeout=120.0)
    if not blocking_png.is_file() or not depth_png.is_file():
        raise RuntimeError(f"Blender failed to write blocking/depth guide PNGs for {shot_id}")

    return {
        "ok": True,
        "shot_id": shot_id,
        "blocking_path": str(blocking_png),
        "depth_path": str(depth_png),
        "blocking_url": f"/file/{slug}/assets/previs/guides/{blocking_png.name}",
        "depth_url": f"/file/{slug}/assets/previs/guides/{depth_png.name}",
        "characters": char_specs,
        "lens_mm": lens_mm,
    }


def find_existing_shot_guide(pd: Path, shot_id: str) -> tuple[Path | None, Path | None]:
    """Return `(blocking_png, depth_png)` if previously rendered for `shot_id`."""
    guides_dir = pd / "assets" / "previs" / "guides"
    safe_sid = _safe_slug(shot_id, "shot")
    blk = guides_dir / f"{safe_sid}_blocking.png"
    dep = guides_dir / f"{safe_sid}_depth.png"
    return (blk if blk.is_file() else None), (dep if dep.is_file() else None)


# ==============================================================================
# 3. MULTI-ANGLE CONSISTENT 3D SET PLATES (STEP 11 SETS)
# ==============================================================================
SET_ANGLES: dict[str, tuple[tuple[float, float, float], tuple[float, float, float], float, str]] = {
    "wide": ((0.0, -3.05, 1.45), (0.0, 1.2, 1.15), 24.0, "Wide Establishing"),
    "reverse": ((0.0, 2.85, 1.45), (0.0, -1.2, 1.10), 28.0, "Reverse Angle"),
    "corner": ((-2.95, -2.60, 1.55), (0.9, 1.1, 1.05), 28.0, "Corner Three-Quarter"),
    "ots": ((-1.65, 1.20, 1.48), (1.4, -0.5, 0.95), 35.0, "Over-the-Shoulder"),
    "top_down": ((0.0, -0.20, 2.65), (0.0, 0.30, 0.30), 21.0, "Top-Down Floorplan"),
}


def render_set_multi_angle(
    pd: Path,
    slug: str,
    set_name: str,
    *,
    angles: tuple[str, ...] = ("wide", "reverse", "corner", "ots", "top_down"),
    description: str = "",
    lighting: str = "",
    width: int = 1024,
    height: int = 576,
) -> dict[str, Any]:
    """Render multiple consistent camera angles from one true-scale 3D set blockout and register them in sets_views.json."""
    safe_set = _safe_slug(set_name, "set")
    out_dir = pd / "assets" / "sets" / "blender_3d"
    exports_dir = pd / "exports"
    out_dir.mkdir(parents=True, exist_ok=True)
    exports_dir.mkdir(parents=True, exist_ok=True)

    features = _infer_room_features(set_name, f"{description} {lighting}", [])
    angle_jobs: list[dict[str, Any]] = []
    for ang in angles:
        key = str(ang).strip().lower()
        if key not in SET_ANGLES:
            continue
        pos, tgt, lens, label = SET_ANGLES[key]
        out_png = out_dir / f"{safe_set}_{key}.png"
        angle_jobs.append({
            "key": key,
            "label": label,
            "pos": list(pos),
            "tgt": list(tgt),
            "lens": lens,
            "out_png": str(out_png),
        })
    if not angle_jobs:
        raise ValueError("No valid set angles requested")

    glb_path = exports_dir / f"set_{safe_set}.glb"
    blend_path = exports_dir / f"set_{safe_set}.blend"

    script_src = (
        _BPY_COMMON_HELPERS
        + f"""
FEATURES = {repr(features)}
ANGLE_JOBS = {repr(angle_jobs)}
GLB_PATH = {repr(str(glb_path))}
BLEND_PATH = {repr(str(blend_path))}

bpy.ops.wm.read_factory_settings(use_empty=True)
scene = bpy.context.scene
_configure_render(scene, {int(width)}, {int(height)}, samples=16)
_build_room(FEATURES)
_setup_lighting(is_space=bool(FEATURES.get("is_space")))

bpy.ops.object.camera_add(location=(0.0, -3.0, 1.45))
cam = bpy.context.active_object
cam.name = "Set_Camera"
scene.camera = cam

bpy.ops.wm.save_as_mainfile(filepath=BLEND_PATH)
try:
    bpy.ops.export_scene.gltf(filepath=GLB_PATH, export_format="GLB")
except Exception as _ge:
    print("GLB export skipped:", _ge)

for job in ANGLE_JOBS:
    _aim_camera(cam, job["pos"], job["tgt"], lens_mm=job["lens"])
    scene.render.filepath = job["out_png"]
    bpy.ops.render.render(write_still=True)
"""
    )

    _run_blender_python(script_src, work_dir=out_dir, timeout=180.0)

    rendered_views: list[dict[str, Any]] = []
    for job in angle_jobs:
        p = Path(job["out_png"])
        if p.is_file():
            rendered_views.append({
                "angle": job["key"],
                "label": job["label"],
                "path": str(p),
                "rel": f"assets/sets/blender_3d/{p.name}",
                "image_url": f"/file/{slug}/assets/sets/blender_3d/{p.name}",
            })

    # Register rendered views into sets_views.json cleanly so Step 11 shows them immediately
    sv_path = pd / "sets_views.json"
    sv_doc: dict[str, Any] = {}
    if sv_path.is_file():
        with contextlib.suppress(OSError, ValueError):
            raw = json.loads(sv_path.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                sv_doc = raw
    set_key = set_name.strip().lower()
    raw_entry = sv_doc.get(set_key)
    entry: dict[str, Any] = dict(raw_entry) if isinstance(raw_entry, dict) else {"name": set_name, "views": []}
    raw_vl = entry.get("views")
    views_list: list[Any] = list(raw_vl) if isinstance(raw_vl, list) else []
    for rv in rendered_views:
        vid = f"blender_{rv['angle']}"
        existing = next((v for v in views_list if isinstance(v, dict) and v.get("id") == vid), None)
        rec = {
            "id": vid,
            "label": f"3D {rv['label']}",
            "notes": f"True-scale Blender 3D angle ({rv['angle']}) — ready to restyle or use as geometry guide",
            "ref_rel": rv["rel"],
            "generated_rel": rv["rel"],
            "source": "blender_3d",
        }
        if existing is not None:
            existing.update(rec)
        else:
            views_list.append(rec)
    entry["views"] = views_list
    sv_doc[set_key] = entry
    sv_path.write_text(json.dumps(sv_doc, indent=2, ensure_ascii=False), encoding="utf-8")

    return {
        "ok": True,
        "set_name": set_name,
        "views_rendered": len(rendered_views),
        "views": rendered_views,
        "glb_url": f"/download/{slug}/exports/{glb_path.name}" if glb_path.is_file() else "",
        "blend_url": f"/download/{slug}/exports/{blend_path.name}" if blend_path.is_file() else "",
    }


# ==============================================================================
# 4. 3D ANIMATED TITLE CARDS & CREDITS (STEP 18 / 20)
# ==============================================================================
def render_3d_title_card(
    pd: Path,
    slug: str,
    *,
    title: str,
    subtitle: str = "",
    style: str = "space_orbit",
    duration_s: float = 3.0,
    fps: int = 24,
    width: int = 1280,
    height: int = 720,
    render_video: bool = True,
) -> dict[str, Any]:
    """Render a 3D extruded bevelled title card (hero PNG + animated camera-sweep MP4) using headless Blender."""
    out_dir = pd / "assets" / "titles"
    out_dir.mkdir(parents=True, exist_ok=True)
    safe_t = _safe_slug(title or slug, "title")
    still_png = out_dir / f"{safe_t}_3d_title.png"
    mp4_path = out_dir / f"{safe_t}_3d_title.mp4"
    frames_dir = out_dir / f"_frames_{safe_t}"

    total_frames = max(12, min(96, int(round(duration_s * fps)))) if render_video else 1

    palette_map = {
        "space_orbit": {"bg": (0.01, 0.02, 0.06), "text": (0.96, 0.78, 0.28), "sub": (0.72, 0.86, 0.98), "metallic": 0.78, "planet": True},
        "cinema_gold": {"bg": (0.03, 0.03, 0.04), "text": (0.94, 0.74, 0.24), "sub": (0.86, 0.84, 0.78), "metallic": 0.90, "planet": False},
        "storybook_wood": {"bg": (0.06, 0.04, 0.03), "text": (0.96, 0.86, 0.64), "sub": (0.82, 0.72, 0.54), "metallic": 0.15, "planet": False},
    }
    pal = palette_map.get(str(style or "space_orbit").lower(), palette_map["space_orbit"])

    script_src = (
        _BPY_COMMON_HELPERS
        + f"""
import os
TITLE_TXT = {repr(str(title or slug).strip()[:80])}
SUB_TXT = {repr(str(subtitle or "").strip()[:100])}
PAL = {repr(pal)}
STILL_PNG = {repr(str(still_png))}
FRAMES_DIR = {repr(str(frames_dir))}
TOTAL_FRAMES = {int(total_frames)}

bpy.ops.wm.read_factory_settings(use_empty=True)
scene = bpy.context.scene
_configure_render(scene, {int(width)}, {int(height)}, samples=16)

world = bpy.data.worlds.new("TitleWorld")
scene.world = world
world.use_nodes = True
bg = next((n for n in world.node_tree.nodes if n.type == "BACKGROUND"), None)
if bg:
    bg.inputs["Color"].default_value = (PAL["bg"][0], PAL["bg"][1], PAL["bg"][2], 1.0)
    bg.inputs["Strength"].default_value = 0.8

m_title = _make_mat("TitleGold", PAL["text"], roughness=0.22, metallic=PAL["metallic"], emission=0.18)
m_sub = _make_mat("SubMat", PAL["sub"], roughness=0.35, metallic=0.25, emission=0.12)

bpy.ops.object.text_add(location=(0.0, 0.0, 0.35), rotation=(math.radians(90), 0.0, 0.0))
t_obj = bpy.context.active_object
t_obj.name = "Title_3D"
t_obj.data.body = TITLE_TXT
t_obj.data.align_x = "CENTER"
t_obj.data.align_y = "CENTER"
t_obj.data.size = 0.95 if len(TITLE_TXT) <= 18 else max(0.42, 16.5 / len(TITLE_TXT))
t_obj.data.extrude = 0.12
t_obj.data.bevel_depth = 0.022
_assign_mat(t_obj, m_title)

if SUB_TXT:
    bpy.ops.object.text_add(location=(0.0, 0.0, -0.55), rotation=(math.radians(90), 0.0, 0.0))
    s_obj = bpy.context.active_object
    s_obj.name = "Subtitle_3D"
    s_obj.data.body = SUB_TXT
    s_obj.data.align_x = "CENTER"
    s_obj.data.align_y = "CENTER"
    s_obj.data.size = 0.34 if len(SUB_TXT) <= 34 else max(0.20, 11.0 / len(SUB_TXT))
    s_obj.data.extrude = 0.04
    s_obj.data.bevel_depth = 0.008
    _assign_mat(s_obj, m_sub)

if PAL.get("planet"):
    _add_sphere("Orbit_Planet", (2.8, 3.8, 1.3), 1.15, _make_mat("Planet", (0.78, 0.65, 0.44), roughness=0.45, emission=0.18))
    bpy.ops.mesh.primitive_torus_add(major_radius=2.05, minor_radius=0.09, location=(2.8, 3.8, 1.3), rotation=(math.radians(74), math.radians(20), 0.0))
    rg = bpy.context.active_object
    rg.scale = (1.0, 1.0, 0.08)
    _assign_mat(rg, _make_mat("Ring", (0.92, 0.82, 0.62), roughness=0.35, emission=0.22))

bpy.ops.object.light_add(type="AREA", location=(-3.5, -4.5, 3.0))
k = bpy.context.active_object
k.data.energy = 600.0
k.data.size = 3.0
k.rotation_euler = (math.radians(55), 0.0, math.radians(-32))

bpy.ops.object.light_add(type="AREA", location=(3.8, -3.0, 2.2))
f = bpy.context.active_object
f.data.energy = 280.0
f.data.size = 2.5
f.rotation_euler = (math.radians(60), 0.0, math.radians(38))

bpy.ops.object.camera_add(location=(0.0, -7.2, 0.1))
cam = bpy.context.active_object
scene.camera = cam

# Hero still at mid-sweep
_aim_camera(cam, (0.0, -7.2, 0.1), (0.0, 0.0, 0.05), lens_mm=38.0)
scene.render.filepath = STILL_PNG
bpy.ops.render.render(write_still=True)

if TOTAL_FRAMES > 1:
    os.makedirs(FRAMES_DIR, exist_ok=True)
    # Render 16 key animation frames for fast encoding (smooth 24fps sweep via FFmpeg interpolation/rate)
    n_render = min(24, TOTAL_FRAMES)
    for idx in range(n_render):
        u = idx / max(1, n_render - 1)
        cx = -1.15 + 2.30 * u
        cy = -8.2 + 1.45 * u
        cz = 0.45 - 0.35 * u
        _aim_camera(cam, (cx, cy, cz), (0.0, 0.0, 0.05), lens_mm=38.0)
        scene.render.filepath = os.path.join(FRAMES_DIR, f"t_{{idx + 1:04d}}.png")
        bpy.ops.render.render(write_still=True)
"""
    )

    _run_blender_python(script_src, work_dir=out_dir, timeout=180.0)

    mp4_url = ""
    if render_video and frames_dir.is_dir():
        ffmpeg = find_ffmpeg_executable()
        rendered_frames = sorted(frames_dir.glob("t_*.png"))
        if ffmpeg and rendered_frames:
            in_fps = max(4.0, len(rendered_frames) / max(1.0, float(duration_s)))
            try:
                subprocess.run(
                    [
                        ffmpeg,
                        "-y",
                        "-framerate",
                        f"{in_fps:.2f}",
                        "-i",
                        str(frames_dir / "t_%04d.png"),
                        "-c:v",
                        "libx264",
                        "-pix_fmt",
                        "yuv420p",
                        "-r",
                        str(int(fps)),
                        str(mp4_path),
                    ],
                    stdin=subprocess.DEVNULL,
                    capture_output=True,
                    check=True,
                    timeout=90,
                )
                if mp4_path.is_file():
                    mp4_url = f"/file/{slug}/assets/titles/{mp4_path.name}"
            except (OSError, subprocess.SubprocessError) as e:
                log.warning("3D Title MP4 encode failed: %s", e)
        shutil.rmtree(frames_dir, ignore_errors=True)

    return {
        "ok": True,
        "title": title,
        "style": style,
        "still_path": str(still_png),
        "still_url": f"/file/{slug}/assets/titles/{still_png.name}" if still_png.is_file() else "",
        "video_path": str(mp4_path) if mp4_url else "",
        "video_url": mp4_url,
    }


# ==============================================================================
# 5. STEP 08 & 10: TRUE-SCALE CAST LINEUP & 4-ANGLE 3D TURNAROUND GUIDES
# ==============================================================================
def render_cast_scale_turnaround_guides(
    pd: Path,
    slug: str,
    *,
    character_name: str = "",
    include_turnarounds: bool = True,
    width: int = 960,
    height: int = 540,
) -> dict[str, Any]:
    """Render true-scale Cast Height Lineup PNG + optional 4-angle 3D Turnaround sheets (.png/.blend/.glb) in Blender."""
    import continuity_book

    book = continuity_book.load(pd) or {}
    raw_chars: list[dict[str, Any]] = []
    if isinstance(book.get("characters"), list):
        raw_chars.extend(c for c in book["characters"] if isinstance(c, dict) and str(c.get("name") or "").strip())
    if not raw_chars and (pd / "readin" / "coverage.json").is_file():
        with contextlib.suppress(OSError, ValueError):
            cov = json.loads((pd / "readin" / "coverage.json").read_text(encoding="utf-8")) or {}
            for c in cov.get("characters") or []:
                if isinstance(c, dict) and str(c.get("name") or "").strip():
                    raw_chars.append({"name": c["name"], "token": str(c.get("description") or "")})

    # Deduplicate by lowercase name and classify metric scale
    specs: list[dict[str, Any]] = []
    seen: set[str] = set()
    for ch in raw_chars:
        cname = str(ch.get("name") or "").strip()
        if not cname or cname.lower() in seen:
            continue
        if "offstage" in cname.lower() or "never appears" in str(ch.get("token") or "").lower():
            continue
        seen.add(cname.lower())
        specs.append(_classify_character_spec(cname, str(ch.get("token") or "")))
    if not specs:
        specs = [_classify_character_spec("PROTAGONIST", "adult human ~5'7\"")]

    if character_name.strip():
        filtered = [s for s in specs if s["name"].lower() == character_name.strip().lower()]
        turn_specs = filtered or specs[:1]
    else:
        turn_specs = specs[:6]

    out_dir = pd / "assets" / "blender_cast"
    exp_dir = pd / "exports"
    out_dir.mkdir(parents=True, exist_ok=True)
    exp_dir.mkdir(parents=True, exist_ok=True)

    lineup_png = out_dir / "cast_scale_lineup.png"
    lineup_blend = exp_dir / "cast_scale_lineup.blend"
    lineup_glb = exp_dir / "cast_scale_lineup.glb"
    turn_targets = [
        {
            **sp,
            "slug": _safe_slug(sp["name"], "char"),
            "angles": [
                ("front", 0.0),
                ("three_quarter", 45.0),
                ("side", 90.0),
                ("back", 180.0),
            ],
        }
        for sp in turn_specs
    ]

    script_src = (
        _BPY_COMMON_HELPERS
        + f"""
import os
SPECS = {repr(specs[:8])}
TURN_TARGETS = {repr(turn_targets if include_turnarounds else [])}
OUT_DIR = {repr(str(out_dir))}
LINEUP_PNG = {repr(str(lineup_png))}
LINEUP_BLEND = {repr(str(lineup_blend))}
LINEUP_GLB = {repr(str(lineup_glb))}
WIDTH = {int(width)}
HEIGHT = {int(height)}

def _add_arm_silhouette(spec, loc_xy):
    if spec["kind"] == "dog":
        return
    h = float(spec["height_m"])
    x, y = float(loc_xy[0]), float(loc_xy[1])
    leg_h = h * 0.46
    torso_h = h * 0.34
    w_scale = max(0.12, h * 0.14)
    m_arm = _make_mat("Arm_" + spec["name"], spec["color"], roughness=0.6)
    arm_len = torso_h * 0.92
    _add_cyl(spec["name"] + "_ArmL", (x - w_scale * 1.18, y, leg_h + torso_h * 0.48), w_scale * 0.22, arm_len, m_arm, rot=(0.0, math.radians(10), 0.0))
    _add_cyl(spec["name"] + "_ArmR", (x + w_scale * 1.18, y, leg_h + torso_h * 0.48), w_scale * 0.22, arm_len, m_arm, rot=(0.0, math.radians(-10), 0.0))

# --- 1. TRUE-SCALE CAST HEIGHT LINEUP ---
bpy.ops.wm.read_factory_settings(use_empty=True)
scene = bpy.context.scene
_configure_render(scene, WIDTH, HEIGHT, samples=16)
_setup_lighting(is_space=False)

n_cast = len(SPECS)
spacing = 0.95
total_w = max(2.6, (n_cast + 1) * spacing)
_add_box("Studio_Floor", (0.0, 0.0, -0.04), (total_w + 2.0, 4.0, 0.08), _make_mat("FloorMat", (0.14, 0.16, 0.20), roughness=0.85))
_add_box("Height_Chart_Wall", (0.0, 0.65, 1.15), (total_w + 1.6, 0.05, 2.35), _make_mat("ChartWall", (0.18, 0.21, 0.27), roughness=0.9))

m_rule = _make_mat("RulerBar", (0.45, 0.62, 0.85), roughness=0.4, emission=0.25)
m_lbl = _make_mat("LabelMat", (0.95, 0.82, 0.36), roughness=0.3, emission=0.35)
for ft in range(1, 7):
    z_m = ft * 0.3048
    _add_box(f"Ruler_{{ft}}ft", (0.0, 0.61, z_m), (total_w + 1.4, 0.015, 0.012), m_rule)
    bpy.ops.object.text_add(location=(-total_w * 0.5 - 0.55, 0.58, z_m - 0.04), rotation=(math.radians(90), 0.0, 0.0))
    t_ft = bpy.context.active_object
    t_ft.data.body = f"{{ft}}ft"
    t_ft.data.size = 0.14
    _assign_mat(t_ft, m_rule)

for idx, sp in enumerate(SPECS):
    cx = (idx - (n_cast - 1) / 2.0) * spacing
    _build_character(sp, (cx, 0.0))
    _add_arm_silhouette(sp, (cx, 0.0))
    ft_val = float(sp["height_m"]) / 0.3048
    bpy.ops.object.text_add(location=(cx, -0.45, 0.03), rotation=(math.radians(78), 0.0, 0.0))
    lbl = bpy.context.active_object
    lbl.data.body = f"{{sp['name'][:12]}} ({{ft_val:.1f}}ft)"
    lbl.data.align_x = "CENTER"
    lbl.data.size = 0.11
    _assign_mat(lbl, m_lbl)

bpy.ops.object.camera_add(location=(0.0, -5.8, 1.05))
cam = bpy.context.active_object
scene.camera = cam
cam_dist = max(4.2, total_w * 1.35)
_aim_camera(cam, (0.0, -cam_dist, 0.98), (0.0, 0.0, 0.95), lens_mm=65.0)
scene.render.filepath = LINEUP_PNG
bpy.ops.render.render(write_still=True)

bpy.ops.wm.save_as_mainfile(filepath=LINEUP_BLEND)
try:
    bpy.ops.export_scene.gltf(filepath=LINEUP_GLB, export_format="GLB")
except Exception:
    pass

# --- 2. PER-CHARACTER 4-ANGLE 3D TURNAROUND GUIDES ---
for t_sp in TURN_TARGETS:
    bpy.ops.wm.read_factory_settings(use_empty=True)
    sc2 = bpy.context.scene
    _configure_render(sc2, 360, 480, samples=12)
    _setup_lighting(is_space=False)
    _add_cyl("Turntable", (0.0, 0.0, -0.03), 0.65, 0.06, _make_mat("Base", (0.16, 0.19, 0.25), roughness=0.7))
    _build_character(t_sp, (0.0, 0.0))
    _add_arm_silhouette(t_sp, (0.0, 0.0))
    bpy.ops.object.camera_add(location=(0.0, -2.5, 1.0))
    c2 = bpy.context.active_object
    sc2.camera = c2
    h_m = max(0.35, float(t_sp["height_m"]))
    dist = max(1.15, h_m * 1.95)
    target_z = h_m * 0.52
    for ang_name, deg in t_sp["angles"]:
        rad = math.radians(deg)
        cx = dist * math.sin(rad)
        cy = -dist * math.cos(rad)
        _aim_camera(c2, (cx, cy, target_z), (0.0, 0.0, target_z), lens_mm=55.0)
        sc2.render.filepath = os.path.join(OUT_DIR, f"_tmp_{{t_sp['slug']}}_{{ang_name}}.png")
        bpy.ops.render.render(write_still=True)
"""
    )

    _run_blender_python(script_src, work_dir=out_dir, timeout=240.0)

    # Composite 4-angle turnaround sheets side-by-side via Pillow (if installed)
    turnaround_sheets: list[dict[str, Any]] = []
    if include_turnarounds:
        for t_sp in turn_targets:
            c_slug = t_sp["slug"]
            angle_files = [
                (ang_name, out_dir / f"_tmp_{c_slug}_{ang_name}.png")
                for ang_name, _ in t_sp["angles"]
            ]
            existing_angles = [(an, p) for an, p in angle_files if p.is_file()]
            sheet_png = out_dir / f"turnaround_{c_slug}_3d.png"
            if existing_angles:
                composited = False
                with contextlib.suppress(Exception):
                    from PIL import Image, ImageDraw

                    imgs = [Image.open(p).convert("RGB") for _, p in existing_angles]
                    pw, ph = imgs[0].size
                    sheet = Image.new("RGB", (pw * len(imgs), ph + 34), (15, 23, 42))
                    draw = ImageDraw.Draw(sheet)
                    labels_map = {"front": "FRONT", "three_quarter": "3/4 VIEW", "side": "PROFILE", "back": "BACK"}
                    ft_val = float(t_sp["height_m"]) / 0.3048
                    for i_a, ((an, _), im) in enumerate(zip(existing_angles, imgs, strict=False)):
                        sheet.paste(im, (i_a * pw, 34))
                        draw.text((i_a * pw + 12, 10), f"{t_sp['name']} · {labels_map.get(an, an.upper())} ({ft_val:.1f} ft)", fill=(250, 204, 21))
                    sheet.save(sheet_png)
                    composited = True
                if not composited:
                    shutil.copy2(existing_angles[0][1], sheet_png)
                for _, p in existing_angles:
                    p.unlink(missing_ok=True)
                if sheet_png.is_file():
                    turnaround_sheets.append({
                        "name": t_sp["name"],
                        "kind": t_sp["kind"],
                        "height_m": t_sp["height_m"],
                        "height_ft": round(float(t_sp["height_m"]) / 0.3048, 1),
                        "path": str(sheet_png),
                        "image_url": f"/file/{slug}/assets/blender_cast/{sheet_png.name}",
                    })

    return {
        "ok": True,
        "characters_count": len(specs),
        "characters": [
            {
                "name": s["name"],
                "kind": s["kind"],
                "height_m": s["height_m"],
                "height_ft": round(float(s["height_m"]) / 0.3048, 1),
            }
            for s in specs
        ],
        "lineup_path": str(lineup_png),
        "lineup_url": f"/file/{slug}/assets/blender_cast/{lineup_png.name}" if lineup_png.is_file() else "",
        "blend_url": f"/download/{slug}/exports/{lineup_blend.name}" if lineup_blend.is_file() else "",
        "glb_url": f"/download/{slug}/exports/{lineup_glb.name}" if lineup_glb.is_file() else "",
        "turnarounds": turnaround_sheets,
    }


def launch_blender_live(blend_path: Path | None = None, *, port: int = 9876) -> dict[str, Any]:
    """Launch portable Blender GUI with the Studio live MCP bridge addon pre-loaded."""
    exe = find_blender_executable()
    if exe is None:
        raise RuntimeError(f"Portable Blender not found in {STANDALONE_BLENDER_DIR}")
    addon_py = Path(__file__).resolve().parent / "blender_live_addon.py"
    argv = [str(exe)]
    if blend_path is not None and blend_path.is_file():
        argv.append(str(blend_path))
    argv.extend(["--python", str(addon_py)])
    env = {**os.environ, "STUDIO_BLENDER_MCP_PORT": str(port)}
    kw: dict[str, Any] = {}
    if sys.platform == "win32":
        kw["creationflags"] = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0x200) | getattr(subprocess, "DETACHED_PROCESS", 0x008)
    proc = subprocess.Popen(argv, env=env, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, **kw)
    return {"ok": True, "pid": proc.pid, "port": port, "blend": str(blend_path) if blend_path else ""}
