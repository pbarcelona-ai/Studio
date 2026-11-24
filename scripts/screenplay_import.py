"""Import Final Draft XML (.fdx) into the Studio's screenplay format (scene-*.json).
Standard library only, works on Windows and macOS.

  python3 screenplay_import.py <project> <fdx_file>     -> projects/books/<book>/screenplay/

The .fdx format uses <Paragraph Type="..."> with Types: Scene Heading, Character, Parenthetical, Dialogue, Action, Transition.
Scene numbers are in the Number attribute of Scene Heading paragraphs.
"""

from __future__ import annotations

import json
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import screenplay  # noqa: E402

# Final Draft paragraph types we handle
FD_TYPES = {
    "Scene Heading": "heading",
    "Action": "action",
    "Character": "dialogue",
    "Parenthetical": "parenthetical",
    "Dialogue": "dialogue",
    "Transition": "transition",
}


def parse_fdx(fdx_path: Path) -> list[dict]:
    """Parse a Final Draft .fdx file into a list of scenes matching the Studio's format.
    Returns: [{"heading": str, "elements": [...]}]
    """
    raw = fdx_path.read_bytes()
    if b"<!ENTITY" in raw.upper():
        raise ValueError("The .fdx file contains XML entity declarations, which are not accepted.")
    root = ET.fromstring(raw)  # noqa: S314  (entity declarations were refused above)

    # Handle potential XML namespaces in Final Draft XML
    # Register namespace if present, or use namespace-agnostic search
    ns = {"": ""}  # default namespace
    # Check for namespace in root tag
    if "}" in root.tag:
        ns_uri = root.tag.split("}")[0].strip("{")
        ns = {"fd": ns_uri}

    # Find Content element (namespace-agnostic)
    content = root.find(".//Content", ns) if ns.get("") else root.find(".//Content")
    if content is None:
        # Try with namespace prefix
        content = root.find(".//fd:Content", ns)
    if content is None:
        raise ValueError("No <Content> element found in .fdx file")

    scenes: list[dict] = []
    current_scene: dict | None = None
    current_character: str | None = None

    # Find all Paragraph elements (namespace-agnostic)
    paragraphs = content.findall("Paragraph", ns) if ns.get("") else content.findall("Paragraph")
    if not paragraphs:
        paragraphs = content.findall("fd:Paragraph", ns)

    for para in paragraphs:
        p_type = para.get("Type", "")
        number = para.get("Number", "")

        # Find Text element (namespace-agnostic)
        text_elem = para.find("Text", ns) if ns.get("") else para.find("Text")
        if text_elem is None:
            text_elem = para.find("fd:Text", ns)
        text = text_elem.text if text_elem is not None and text_elem.text else ""

        if p_type == "Scene Heading":
            # Save previous scene
            if current_scene is not None:
                scenes.append(current_scene)

            # Start new scene
            scene_num = number.strip() if number else str(len(scenes) + 1)
            current_scene = {
                "heading": text.strip(),
                "elements": [],
                "_scene_number": scene_num,
            }
            current_character = None

        elif p_type == "Character":
            # Character cue - start a dialogue element
            current_character = text.strip().upper()
            # We'll add the dialogue element when we see the Dialogue paragraph

        elif p_type == "Parenthetical":
            # Parenthetical belongs to the current character's dialogue
            if current_scene is not None and current_character:
                # Find the last dialogue element for this character and add note
                for elem in reversed(current_scene["elements"]):
                    if elem["type"] == "dialogue" and elem["character"] == current_character:
                        elem["note"] = text.strip().strip("()")
                        break

        elif p_type == "Dialogue":
            if current_scene is not None:
                if current_character:
                    current_scene["elements"].append({
                        "type": "dialogue",
                        "character": current_character,
                        "text": text.strip(),
                    })
                else:
                    # Dialogue without character - treat as action
                    current_scene["elements"].append({
                        "type": "action",
                        "text": text.strip(),
                    })
                current_character = None

        elif p_type in ("Action", "Transition"):
            if current_scene is not None:
                current_scene["elements"].append({
                    "type": "action" if p_type == "Action" else "transition",
                    "text": text.strip(),
                })
                current_character = None

    # Don't forget the last scene
    if current_scene is not None:
        scenes.append(current_scene)

    return scenes


def match_scenes_to_plan(fdx_scenes: list[dict], plan_scenes: list[dict]) -> list[tuple[str, dict]]:
    """Match imported FDX scenes to the adaptation plan's scenes by number/heading.
    Returns list of (scene_id, fdx_scene) tuples.
    """
    matches = []
    used_fdx = set()

    for plan_scene in plan_scenes:
        sid = plan_scene["id"]
        matched = None

        # Try to match by scene number first (from Number attribute in FDX)
        for i, fdx_scene in enumerate(fdx_scenes):
            if i in used_fdx:
                continue
            fdx_num = fdx_scene.get("_scene_number", "")
            if fdx_num and fdx_num.isdigit() and int(fdx_num) == int(sid[1:]):
                matched = fdx_scene
                used_fdx.add(i)
                break

        # Fallback: match by heading similarity
        if not matched:
            plan_heading = plan_scene.get("heading", "").upper().strip()
            for i, fdx_scene in enumerate(fdx_scenes):
                if i in used_fdx:
                    continue
                fdx_heading = fdx_scene.get("heading", "").upper().strip()
                if plan_heading and fdx_heading and (plan_heading in fdx_heading or fdx_heading in plan_heading):
                    matched = fdx_scene
                    used_fdx.add(i)
                    break

        # Fallback: sequential assignment
        if not matched:
            for i, fdx_scene in enumerate(fdx_scenes):
                if i not in used_fdx:
                    matched = fdx_scene
                    used_fdx.add(i)
                    break

        if matched:
            # Remove internal _scene_number before returning
            clean_scene = {k: v for k, v in matched.items() if k != "_scene_number"}
            matches.append((sid, clean_scene))

    return matches


def import_fdx(pdir: Path, fdx_path: Path) -> dict:
    """Import a .fdx file into the Studio's screenplay folder.
    Returns summary of what was imported.
    """
    import adaptation as ad

    plan = ad.load(pdir)
    if not plan:
        raise ValueError("No adaptation plan found for this project. Run 'Adapt' first.")

    plan_scenes = ad.active_scenes(plan)
    if not plan_scenes:
        raise ValueError("Adaptation plan has no scenes.")

    # Parse the .fdx file
    fdx_scenes = parse_fdx(fdx_path)
    if not fdx_scenes:
        raise ValueError("No scenes found in .fdx file.")

    # Match to plan scenes
    matched = match_scenes_to_plan(fdx_scenes, plan_scenes)

    # Save each scene
    imported = 0
    errors = []
    for sid, scene_data in matched:
        try:
            screenplay.save_scene(pdir, sid, scene_data, edited=True)
            imported += 1
        except Exception as e:
            errors.append(f"{sid}: {e}")

    # Clear approval since screenplay changed
    screenplay.clear_approval(pdir)

    return {
        "imported": imported,
        "total_plan_scenes": len(plan_scenes),
        "total_fdx_scenes": len(fdx_scenes),
        "matched": len(matched),
        "errors": errors,
    }


def import_fountain(pdir: Path, fountain_path: Path) -> dict:
    """Import a Fountain (.fountain) file into the Studio's screenplay folder.
    Simpler parser for the plain-text format.
    """
    import adaptation as ad

    plan = ad.load(pdir)
    if not plan:
        raise ValueError("No adaptation plan found for this project. Run 'Adapt' first.")

    plan_scenes = ad.active_scenes(plan)
    if not plan_scenes:
        raise ValueError("Adaptation plan has no scenes.")

    text = fountain_path.read_text(encoding="utf-8")
    lines = text.split("\n")

    # Simple Fountain parser - handles Studio's export format
    scenes: list[dict] = []
    current_scene: dict | None = None
    current_character: str | None = None
    expect_dialogue = False  # After character, next non-empty line is dialogue or parenthetical

    def is_character_name(line: str) -> bool:
        """Check if a line is a Fountain character name (all caps, short, no sentence punctuation)."""
        s = line.strip()
        return (s.isupper() and len(s) < 60 and not s.endswith(".") and not s.endswith("?")
                and not s.endswith("!") and not s.startswith("("))

    i = 0
    while i < len(lines):
        line = lines[i].rstrip()

        # Scene heading: starts with INT./EXT./INT. and may end with #N#
        if re.match(r"^(INT\.|EXT\.|INT/EXT\.|I\.?E\.?)", line.upper()):
            if current_scene:
                scenes.append(current_scene)
            # Remove trailing #N# scene number
            heading = re.sub(r"\s*#\d+#\s*$", "", line).strip()
            current_scene = {"heading": heading, "elements": []}
            current_character = None
            expect_dialogue = False

        elif line.startswith(">"):
            # Transition
            if current_scene:
                current_scene["elements"].append({"type": "transition", "text": line[1:].strip().upper()})
            current_character = None
            expect_dialogue = False

        elif line and not line.startswith(" ") and not line.startswith("\t") and current_scene and is_character_name(line):
            # Character name (all caps, no indent)
            current_character = line.strip().upper()
            current_scene["elements"].append({"type": "dialogue", "character": current_character, "text": ""})
            expect_dialogue = True

        elif line.startswith("(") and line.endswith(")") and current_scene and current_character and expect_dialogue:
            # Parenthetical right after character
            if current_scene["elements"] and current_scene["elements"][-1]["type"] == "dialogue" and current_scene["elements"][-1]["character"] == current_character:
                current_scene["elements"][-1]["note"] = line.strip("()")
            expect_dialogue = True  # Still expect dialogue after parenthetical

        elif current_scene and current_character and expect_dialogue and line:
            # Dialogue text (after character or parenthetical)
            if current_scene["elements"] and current_scene["elements"][-1]["type"] == "dialogue" and current_scene["elements"][-1]["character"] == current_character:
                current_scene["elements"][-1]["text"] = line.strip()
            expect_dialogue = False

        elif current_scene and line:
            # Action text (any non-empty line when not expecting dialogue)
            current_scene["elements"].append({"type": "action", "text": line.strip()})
            current_character = None
            expect_dialogue = False

        # Empty lines just reset expect_dialogue
        elif not line:
            if current_scene and expect_dialogue and current_character:
                # Character with no dialogue - treat as action
                if current_scene["elements"] and current_scene["elements"][-1]["type"] == "dialogue" and current_scene["elements"][-1]["character"] == current_character:
                    # Convert the empty dialogue to action
                    current_scene["elements"][-1]["type"] = "action"
                    current_scene["elements"][-1].pop("character", None)
            current_character = None
            expect_dialogue = False

        i += 1

    if current_scene:
        scenes.append(current_scene)

    # Match to plan scenes (sequential)
    imported = 0
    errors = []
    for i, plan_scene in enumerate(plan_scenes):
        if i < len(scenes):
            try:
                screenplay.save_scene(pdir, plan_scene["id"], scenes[i], edited=True)
                imported += 1
            except Exception as e:
                errors.append(f"{plan_scene['id']}: {e}")

    screenplay.clear_approval(pdir)

    return {
        "imported": imported,
        "total_plan_scenes": len(plan_scenes),
        "total_fountain_scenes": len(scenes),
        "errors": errors,
    }


if __name__ == "__main__":
    from layout import project_dir

    if len(sys.argv) < 3:
        sys.exit(__doc__)

    try:
        pdir = project_dir(sys.argv[1])
        fdx_path = Path(sys.argv[2])
        result = import_fdx(pdir, fdx_path)
        print(json.dumps(result, indent=2))
    except Exception as e:
        sys.exit(str(e))
