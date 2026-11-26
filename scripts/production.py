"""The "Choose a format and what to make" step (BOOK_TO_SCREEN_BUILD.md Sections 1, 6, 7 and 10.2; milestone M2).

A book's production settings live in projects/books/<book>/production.json:

  recipe          the format recipe (recipes/*.json, crew.py); choosing one fills in the settings below
  products        any of A-G (the screenplay, A, is always made): screenplay, storyboard, illustrated_book, animatic, film, audiobook, marketing
  target_minutes  the film's length; aspect 16:9 | 9:16 | 1:1 | 4:3; rating all | 8 | 13 | adult; faithfulness strict | balanced | free;
  tier            draft | final (Section 10.2)
  styles          one or more of the presets, or custom styles {id, name, text}; `master` is the style made first (default: the first picked)

normalise() fills in what is missing and adds the products a chosen product needs, saying so in plain words (the film needs the storyboard
in the same style ...). estimate() gives shots, AI calls, GPU hours and dollars per product and per style, with +30% for regenerations.
"""
from __future__ import annotations

import json
import math
import re
from pathlib import Path

import character_types_registry as _ctr
import crew

PRODUCTS = {      # key: (letter, title, made once per style?)
    "screenplay": ("A", "Screenplay (PDF, Fountain, Word)", False),
    "storyboard": ("B", "Storyboard", True),
    "illustrated_book": ("C", "Illustrated book", True),
    "animatic": ("D", "Animatic", True),
    "film": ("E", "Film", True),
    "audiobook": ("F", "Audiobook", False),
    "marketing": ("G", "Marketing kit", True),
}
NEEDS = {"animatic": ["storyboard"], "film": ["storyboard"], "marketing": ["film", "storyboard"]}
WHY = {("animatic", "storyboard"): "The animatic is made from the storyboard pictures, so the storyboard was added.",
       ("film", "storyboard"): "The film's clips start from the storyboard pictures, so the storyboard was added.",
       ("marketing", "film"): "The trailer is cut from the film's clips, so the film was added.",
       ("marketing", "storyboard"): "The marketing kit needs the storyboard (for the poster and the clips), so it was added."}
STYLES: dict[str, tuple[str, str]] = {
    "realistic": ("Realistic live action", "photographic live action, natural skin and fabric, real-world lighting, cinema camera"),
    "claymation": ("Claymation", "plasticine stop-motion: clay skin with faint fingerprints, handmade sets, soft studio lights, slight frame jitter"),
    "pixar_3d": ("3D animated (Pixar-style)", "stylised 3D animation: appealing shapes, subsurface skin, soft global illumination, rich colour"),
    "anime": ("Anime", "Japanese anime: clean line art, cel shading, expressive eyes, painted backgrounds"),
    "watercolour": ("Watercolour storybook", "watercolour illustration: soft washes, paper texture, gentle edges, storybook palette"),
    "comic_ink": ("Comic ink", "comic book art: bold ink lines, flat colours, halftone shading, dynamic framing"),
    "felt": ("Stop-motion felt", "felt and fabric stop-motion: wool textures, stitched seams, miniature sets, warm practical light"),
    "noir": ("Noir black-and-white", "film noir: black-and-white, hard shadows, venetian-blind light, high contrast, smoky air"),
    "glazed_ceramic": ("Glazed ceramic miniature", "hand-painted glazed ceramic miniature: glossy crackle-glazed surfaces, subtle handmade imperfections, warm specular highlights, shallow depth of field"),
    "painted_sign": ("Hand-painted vintage sign", "vintage hand-painted 2D sign illustration: bold dark outlines, visible directional brushstrokes, weathered flat pigments, warm painted highlights, no 3D render"),
    "scratchboard": ("Scratchboard engraving", "handcrafted scratchboard engraving: deep midnight ground, fine ivory and muted-ochre scratched lines, delicate cross-hatching, large preserved dark areas, no smooth gradients"),
    "tin_toy": ("Vintage tin-toy macro", "vintage wind-up tin-toy macro photography: chipped enamel paint, stamped metal panels, rivets, brass winding keys, directional studio light, shallow macro depth of field"),
    "ukiyo_e": ("Ukiyo-e woodblock print", "Japanese Ukiyo-e woodblock print: fine dark ink outlines, carved hatching, flat faded indigo, vermilion and ochre pigments, aged washi-paper grain, subtle print imperfections"),
    "midcentury_2d": ("Mid-century 2D cartoon", "hand-painted mid-century 2D cartoon: stylized geometric shapes, dry-gouache textures, simplified elongated anatomy, muted earthy palette, subtle paper grain"),
    "fabric_collage": ("Fabric-collage appliqué", "handmade textile-collage artwork: layered felt, printed cotton, linen, embroidery thread and yarn, visible blanket stitches, frayed edges, soft shadows between appliqué layers"),
}


def refresh_styles() -> dict[str, tuple[str, str]]:
    """Sync `STYLES` with all built-in + custom styles from `character_types_registry`."""
    for sid, val in _ctr.production_styles_dict().items():
        if sid not in STYLES or sid not in ("realistic", "claymation", "pixar_3d", "anime", "watercolour", "comic_ink", "felt", "noir", "glazed_ceramic", "painted_sign", "scratchboard", "tin_toy", "ukiyo_e", "midcentury_2d", "fabric_collage"):
            STYLES[sid] = val
    return STYLES


refresh_styles()
ASPECTS = ("16:9", "9:16", "1:1", "4:3")
RATINGS = {"all": "All ages", "8": "8+", "13": "13+", "adult": "Adult"}
FAITHFULNESS = {"strict": "Strict", "balanced": "Balanced", "free": "Free"}
TIERS = {"draft": "Draft (cheaper, faster, lower resolution)", "final": "Final"}
REGEN = 0.30                                   # expected regenerations (Section 10.2 default)
MAX_STYLES = 8
ID_RE = re.compile(r"^[a-z0-9_]{2,30}$")
# the cost model: seconds per shot by format, GPU seconds per picture / clip on a free T4, dollars per call on paid services
SECONDS_PER_SHOT = {"vertical_microdrama": 2.5, "music_video": 2.5, "trailer_only": 2.0}
GPU_SECONDS = {"draft": {"picture": 6, "clip": 60}, "final": {"picture": 14, "clip": 150}}
PAID_DOLLARS = {"draft": {"picture": 0.004, "clip": 0.10}, "final": {"picture": 0.03, "clip": 0.50}}
KAGGLE_FREE_HOURS_A_WEEK = 30


def path(pdir: Path) -> Path:
    return pdir / "production.json"


def defaults(recipe_name: str = "") -> dict:
    r = crew.recipe(recipe_name) if recipe_name else {}
    products = [p for p in r.get("products", ["screenplay", "storyboard", "animatic", "film"]) if p in PRODUCTS]
    return {"recipe": recipe_name, "products": products, "target_minutes": r.get("target_minutes") or 10, "aspect": r.get("aspect", "16:9"),
            "rating": "13", "faithfulness": "balanced", "tier": r.get("quality_tier", "final"), "styles": [{"id": "realistic"}], "master": "realistic"}


def style_name(st: dict) -> str:
    return STYLES[st["id"]][0] if st["id"] in STYLES else str(st.get("name") or st["id"])


def normalise(d: dict) -> tuple[dict, list[str]]:
    """Checked settings and plain-word notes about what was changed or added. Raises ValueError for a value that cannot be used."""
    recipe_name = str(d.get("recipe", "") or "")
    base = defaults(recipe_name)
    out = {**base, **{k: v for k, v in d.items() if k in base}}
    notes: list[str] = []
    prods = [p for p in out["products"] if p in PRODUCTS] if isinstance(out["products"], list) else []
    if "screenplay" not in prods:
        prods.insert(0, "screenplay")
    changed = True
    while changed:
        changed = False
        for p in list(prods):
            for need in NEEDS.get(p, []):
                if need not in prods:
                    prods.append(need)
                    notes.append(WHY[(p, need)])
                    changed = True
    out["products"] = [p for p in PRODUCTS if p in prods]
    try:
        minutes = float(out["target_minutes"])
    except (TypeError, ValueError):
        raise ValueError("the length must be a number of minutes") from None
    if not math.isfinite(minutes) or not 0.5 <= minutes <= 600:
        raise ValueError("the length must be between half a minute and 600 minutes")
    out["target_minutes"] = round(minutes, 1)
    for key, allowed in (("aspect", ASPECTS), ("rating", RATINGS), ("faithfulness", FAITHFULNESS), ("tier", TIERS)):
        if str(out[key]) not in allowed:
            raise ValueError(f"{key} must be one of: {', '.join(allowed)}")
        out[key] = str(out[key])
    styles, seen = [], set()
    for st in out["styles"] if isinstance(out["styles"], list) else []:
        st = st if isinstance(st, dict) else {"id": str(st)}
        sid = str(st.get("id", "")).strip().lower()
        if sid in STYLES:
            styles.append({"id": sid})
        elif ID_RE.match(sid) and str(st.get("text", "")).strip():
            styles.append({"id": sid, "name": str(st.get("name") or sid)[:60], "text": str(st["text"]).strip()[:1500],
                           **({"image": str(st["image"])[:200]} if st.get("image") else {})})
        else:
            raise ValueError(f"unknown style {sid!r}: pick a preset or describe a custom style in words")
        if sid in seen:
            styles.pop()
        seen.add(sid)
    if not styles:
        styles = [{"id": "realistic"}]
        notes.append("No style was picked, so Realistic live action is used.")
    if len(styles) > MAX_STYLES:
        raise ValueError(f"pick at most {MAX_STYLES} styles")
    out["styles"] = styles
    if out.get("master") not in {s["id"] for s in styles}:
        out["master"] = styles[0]["id"]
    styles.sort(key=lambda s: s["id"] != out["master"])     # the master style first
    return out, notes


def load(pdir: Path) -> dict:
    try:
        raw = json.loads(path(pdir).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        raw = {}
    if not isinstance(raw, dict):
        raw = {}
    chosen = crew.project_recipe(pdir)                  # the Format card (crew.js) owns the recipe
    if raw.get("recipe", "") != chosen:                 # a new recipe: its settings, keeping the styles
        raw = {"recipe": chosen, **({"styles": raw["styles"], "master": raw.get("master")} if raw.get("styles") else {})}
    try:
        return normalise(raw)[0]
    except ValueError:
        return normalise({"recipe": raw.get("recipe", "")})[0]


def save(pdir: Path, d: dict) -> tuple[dict, list[str]]:
    out, notes = normalise({**d, "recipe": crew.project_recipe(pdir)})
    path(pdir).write_text(json.dumps(out, indent=1, ensure_ascii=False), encoding="utf-8")
    return out, notes


def estimate(d: dict, recipe_name: str = "", paid: bool = False) -> dict:
    """Shots, calls, GPU hours and dollars per product and per style (+30% regenerations). Free GPUs cost $0 but use the weekly quota."""
    sps = SECONDS_PER_SHOT.get(recipe_name or d.get("recipe", ""), 4.0)
    shots = max(1, round(d["target_minutes"] * 60 / sps))
    gpu, dollars = GPU_SECONDS[d["tier"]], PAID_DOLLARS[d["tier"]]
    pages = max(8, round(d["target_minutes"] * 2)) if "illustrated_book" in d["products"] else 0
    per_style = []
    for st in d["styles"]:
        pictures = (shots if "storyboard" in d["products"] else 0) + pages
        clips = shots if "film" in d["products"] else 0
        if "marketing" in d["products"]:
            pictures += 4                                  # poster, thumbnail and two key frames
        calls = math.ceil((pictures + clips) * (1 + REGEN))
        hours = ((pictures * gpu["picture"]) + (clips * gpu["clip"])) * (1 + REGEN) / 3600
        cost = ((pictures * dollars["picture"]) + (clips * dollars["clip"])) * (1 + REGEN) if paid else 0.0
        per_style.append({"style": st["id"], "name": style_name(st), "pictures": pictures, "clips": clips, "calls": calls,
                          "gpu_hours": round(hours, 1), "dollars": round(cost, 2), "master": st["id"] == d["master"]})
    text_calls = 12 + math.ceil(d["target_minutes"] / 10) * 3              # Read it in: coverage, plan, beats, treatment, acts, critique rounds
    hours = round(sum(s["gpu_hours"] for s in per_style), 1)
    return {"shots": shots, "seconds_per_shot": sps, "text_calls": text_calls, "styles": per_style, "gpu_hours": hours,
            "free_weeks": round(hours / KAGGLE_FREE_HOURS_A_WEEK, 1), "dollars": round(sum(s["dollars"] for s in per_style), 2),
            "regen_allowance": REGEN, "paid": paid}


def catalog() -> dict:
    return {"products": [{"id": k, "letter": v[0], "title": v[1], "per_style": v[2], "needs": NEEDS.get(k, [])} for k, v in PRODUCTS.items()],
            "styles": [{"id": k, "name": v[0], "about": v[1]} for k, v in STYLES.items()], "aspects": list(ASPECTS),
            "ratings": [{"id": k, "name": v} for k, v in RATINGS.items()], "faithfulness": [{"id": k, "name": v} for k, v in FAITHFULNESS.items()],
            "tiers": [{"id": k, "name": v} for k, v in TIERS.items()],
            "recipes": [{"name": r["name"], "title": r["title"], "about": r.get("about", "")} for r in crew.recipes()]}
