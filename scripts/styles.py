#!/usr/bin/env python3
"""The style system (BOOK_TO_SCREEN_BUILD.md Section 7, milestone M5): style cards, style translations, prompt assembly and look development.

  python3 styles.py <project> [--style ID] [--engine claude|... |fake] [--model M]     write the cards and translations of the chosen styles

WHAT is shared by every style (screenplay, continuity tokens, shot list); HOW is per style:
  styles/<id>/card.json          the Art Director + Colorist's style card: medium, materials, rendering, lighting_language, palette, grade,
                                 prefix, suffix, negative
  styles/<id>/translations.json  the Character Designer's STYLE TRANSLATION of every character, location and prop ("in Claymation:
                                 plasticine skin with faint fingerprints, oversized hands, felt coat"); identity stays the token's
assemble() builds a picture prompt in CODE (never AI), so it is the same for every style (Section 7.3):
  style prefix + composition and camera (DP) + action and expression (Director) + each character in frame: identity + style translation
  + the location: identity + style translation + lighting intent (DP) + the style's lighting language + style suffix;
  negative = the style's negative + the global negative. Every part is kept separately (for the Script Supervisor and the picture library).
Look development (Section 6): per style, character sheets (front, side, face) and location key art, 4 variants each, as a prompt set
projects/prompts/<book>_ld_<style>/all_images.csv that the usual image runners render; the owner picks the best of 4 (picks.json) and
approves (gates.py, step "lookdev").
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from collections.abc import Callable
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import continuity_book  # noqa: E402
import crew  # noqa: E402
import gates  # noqa: E402
import layout  # noqa: E402
import production  # noqa: E402

CARD_KEYS = ("medium", "materials", "rendering", "lighting_language", "palette", "grade", "prefix", "suffix", "negative")
GLOBAL_NEGATIVE = "text, subtitles, logo, watermark, extra limbs, extra fingers, deformed hands, duplicate person"
VIEWS = {"front": "full-body character sheet, front view, standing, neutral pose, plain light grey background",
         "side": "full-body character sheet, side view (profile), standing, plain light grey background",
         "face": "face close-up portrait, front, neutral expression, plain light grey background"}
VARIANTS = 4
SIZES = {"16:9": (1344, 768), "9:16": (768, 1344), "1:1": (1024, 1024), "4:3": (1152, 864)}
Ask = Callable[[str, str | list[str], str, Callable[[dict], None]], dict]


class StyleError(RuntimeError):
    """A style step cannot be done as asked; the message says why."""


def sdir(pdir: Path, sid: str) -> Path:
    if not re.fullmatch(r"[a-z0-9_]{2,30}", sid):
        raise StyleError(f"bad style id {sid!r}")
    return pdir / "styles" / sid


def _read(p: Path, default=None):
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def _write(p: Path, d) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_text(json.dumps(d, indent=1, ensure_ascii=False), encoding="utf-8")
    tmp.replace(p)


def chosen(pdir: Path) -> list[dict]:
    """The book's styles (production.json), master first, each {id, name, about, master}."""
    st = production.load(pdir)
    out = []
    for s in st["styles"]:
        about = production.STYLES[s["id"]][1] if s["id"] in production.STYLES else s.get("text", "")
        out.append({"id": s["id"], "name": production.style_name(s), "about": about, "master": s["id"] == st["master"]})
    return out


def style_of(pdir: Path, sid: str) -> dict:
    s = next((x for x in chosen(pdir) if x["id"] == sid), None)
    if s is None:
        raise StyleError(f"{sid} is not one of this book's styles (choose it in the Format card)")
    return s


# ---------------------------------------------------------------------------------------------- style cards and translations
def check_card(d) -> None:
    if not isinstance(d, dict):
        raise ValueError("reply with one JSON object")
    for k in CARD_KEYS:
        if not isinstance(d.get(k), str) or not d[k].strip():
            raise ValueError(f"the style card needs '{k}'")
        if len(d[k]) > 400:
            raise ValueError(f"'{k}' is too long (keep it under 300 characters)")


def translation_checker(book: dict) -> Callable[[dict], None]:
    def check(d) -> None:
        if not isinstance(d, dict):
            raise ValueError("reply with one JSON object")
        for kind in ("characters", "locations", "props"):
            want = {c["name"] for c in book.get(kind, [])}
            got = d.get(kind, {})
            if not isinstance(got, dict):
                raise ValueError(f"'{kind}' maps each name to its style translation")
            missing = sorted(want - set(got))
            if missing:
                raise ValueError(f"translate every {kind[:-1]}: missing {', '.join(missing)}")
            for name, t in got.items():
                if not isinstance(t, str) or not t.strip() or len(t) > 300:
                    raise ValueError(f"the translation of {name} must be a short text (under 250 characters)")
    return check


def write_card(pdir: Path, sid: str, ask: Ask) -> dict:
    s = style_of(pdir, sid)
    d = ask(f"Write the style card for the look '{s['name']}': {s['about']}. It is used for every picture of the film in this style, on top of "
            "the shared shot descriptions, so it describes only HOW things look: the medium, materials, rendering, lighting language, palette and "
            "colour grade, a short prompt prefix and suffix for an image model, and a negative prompt of what this style must avoid. "
            'Reply as JSON: {"medium": "...", "materials": "...", "rendering": "...", "lighting_language": "...", "palette": "...", "grade": "...", '
            '"prefix": "...", "suffix": "...", "negative": "..."}', ["production_designer", "colorist"], f"style card: {sid}", check_card)
    card = {"id": sid, "name": s["name"], **{k: " ".join(str(d[k]).split()) for k in CARD_KEYS}}
    _write(sdir(pdir, sid) / "card.json", card)
    return card


def write_translations(pdir: Path, sid: str, ask: Ask) -> dict:
    book = continuity_book.load(pdir)
    if not book.get("characters"):
        raise StyleError("There is no continuity book yet: write and approve it first.")
    card = card_of(pdir, sid)
    listing = "\n".join(f"{kind}: {c['name']}: {c['token']}" for kind in ("characters", "locations", "props") for c in book.get(kind, []))
    d = ask(f"Write the STYLE TRANSLATION of every character, location and prop for the style '{card['name']}' ({card['medium']}; {card['materials']}; "
            f"{card['rendering']}). Keep identity exactly as the token says (age, build, face, hair, colours, outfit); say only how it is MADE in this "
            "style, e.g. 'in Claymation: plasticine skin with faint fingerprints, oversized hands, felt coat'. Each under 200 characters. "
            'Reply as JSON: {"characters": {"NAME": "..."}, "locations": {"name": "..."}, "props": {"name": "..."}}\n\n' + listing,
            ["casting_director", "production_designer"], f"style translations: {sid}", translation_checker(book))
    tr = {kind: {name: " ".join(str(t).split()) for name, t in d.get(kind, {}).items()} for kind in ("characters", "locations", "props")}
    _write(sdir(pdir, sid) / "translations.json", tr)
    return tr


def card_of(pdir: Path, sid: str) -> dict:
    c = _read(sdir(pdir, sid) / "card.json")
    if not c:
        raise StyleError(f"the {sid} style has no style card yet: write it first")
    return c


def translations_of(pdir: Path, sid: str) -> dict:
    return _read(sdir(pdir, sid) / "translations.json", {}) or {}


def edit_card(pdir: Path, sid: str, fields: dict) -> dict:
    card = {**card_of(pdir, sid), **{k: str(v) for k, v in fields.items() if k in CARD_KEYS}}
    check_card(card)
    _write(sdir(pdir, sid) / "card.json", card)
    return card


def edit_translation(pdir: Path, sid: str, kind: str, name: str, text: str) -> dict:
    tr = translations_of(pdir, sid)
    if kind not in ("characters", "locations", "props") or name not in tr.get(kind, {}):
        raise StyleError(f"no {kind} translation for {name!r}")
    if not text.strip() or len(text) > 300:
        raise StyleError("a translation is a short text (under 250 characters)")
    tr[kind][name] = " ".join(text.split())
    _write(sdir(pdir, sid) / "translations.json", tr)
    return tr


# ---------------------------------------------------------------------------------------------- prompt assembly (code, identical for every style)
def _match(name: str, items: list[dict]) -> dict | None:
    """The continuity item called `name` (case and articles ignored; a location heading may be longer than its name)."""
    n = re.sub(r"^(the|a|an)\s+", "", name.lower().strip())
    for it in items:
        m = re.sub(r"^(the|a|an)\s+", "", it["name"].lower().strip())
        if m == n or (m and (m in n or n in m)):
            return it
    return None


def assemble(shot: dict, location: str, card: dict, tr: dict, book: dict, global_negative: str = GLOBAL_NEGATIVE) -> dict:
    """The picture prompt of one shot in one style: every part separately, and the joined prompt and negative."""
    chars = []
    for name in shot.get("characters", []):
        c = _match(name, book.get("characters", []))
        if c:
            chars.append({"name": c["name"], "identity": c["token"], "style": tr.get("characters", {}).get(c["name"], "")})
    loc = _match(location, book.get("locations", [])) if location else None
    props = []
    for name in shot.get("props", []):
        p = _match(name, book.get("props", []))
        if p:
            props.append({"name": p["name"], "identity": p["token"], "style": tr.get("props", {}).get(p["name"], "")})
    parts = {
        "prefix": card["prefix"],
        "camera": ", ".join(x for x in (f"{shot.get('type', '')} shot", f"{shot.get('lens_mm', '')}mm lens" if shot.get("lens_mm") else "",
                                        f"{shot.get('height', '')} height" if shot.get("height") else "", shot.get("angle", ""),
                                        shot.get("movement", "") if shot.get("movement") not in ("", "static") else "", shot.get("composition", "")) if x),
        "action": ". ".join(x.strip().rstrip(".") for x in (shot.get("action", ""), shot.get("expression", "")) if x.strip()),
        "characters": chars,
        "location": {"name": loc["name"], "identity": loc["token"], "style": tr.get("locations", {}).get(loc["name"], "")} if loc else None,
        "props": props,
        "lighting": shot.get("lighting", ""),
        "lighting_language": card["lighting_language"],
        "suffix": card["suffix"],
    }
    pieces = [parts["prefix"], parts["camera"], parts["action"]]
    pieces += [f"{c['identity']}" + (f", {c['style']}" if c["style"] else "") for c in chars]
    if parts["location"]:
        pieces.append(parts["location"]["identity"] + (f", {parts['location']['style']}" if parts["location"]["style"] else ""))
    pieces += [p["identity"] + (f", {p['style']}" if p["style"] else "") for p in props]
    pieces += [parts["lighting"], parts["lighting_language"], parts["suffix"]]
    negative = ", ".join(x for x in (card["negative"], global_negative) if x)
    return {"parts": parts, "prompt": ". ".join(" ".join(p.split()).rstrip(".") for p in pieces if p and p.strip()), "negative": negative}


# ---------------------------------------------------------------------------------------------- look development
def lookdev_set(pdir: Path, sid: str) -> str:
    """The prompt-set name of a style's look development: <book>_ld_<style>, cut to the 40-character limit of a project name."""
    return f"{pdir.name[:40 - 4 - len(sid)]}_ld_{sid}"[:40]


def lookdev_items(pdir: Path, sid: str) -> list[dict]:
    """Character sheets (front, side, face) and location key art, each with its prompt (4 variants are rendered per item)."""
    book = continuity_book.load(pdir)
    card, tr = card_of(pdir, sid), translations_of(pdir, sid)
    if not tr:
        raise StyleError(f"the {sid} style has no translations yet: write them first")
    items = []
    for c in book.get("characters", []):
        for view, how in VIEWS.items():
            body = f"{card['prefix']}. {how}. {c['token']}" + (f", {tr['characters'].get(c['name'], '')}" if tr.get("characters", {}).get(c["name"]) else "")
            items.append({"key": f"character:{c['name']}:{view}", "kind": "character", "name": c["name"], "view": view,
                          "prompt": f"{body}. {card['lighting_language']}. {card['suffix']}"})
    for loc in book.get("locations", []):
        body = f"{card['prefix']}. Location key art, wide establishing shot, no people. {loc['token']}" + (f", {tr['locations'].get(loc['name'], '')}" if tr.get("locations", {}).get(loc["name"]) else "")
        items.append({"key": f"location:{loc['name']}", "kind": "location", "name": loc["name"], "view": "key art", "prompt": f"{body}. {card['lighting_language']}. {card['suffix']}"})
    return items


def write_lookdev(pdir: Path, sid: str, seed: int = 1000) -> dict:
    """The prompt set (all_images.csv, 4 rows per item) and lookdev.json (which row is which item and variant)."""
    items = lookdev_items(pdir, sid)
    card = card_of(pdir, sid)
    w, h = SIZES.get(production.load(pdir)["aspect"], SIZES["16:9"])
    name = lookdev_set(pdir, sid)
    out = layout.new_dir(name, "prompts") if layout.find_dir(name) is None else layout.find_dir(name)
    assert out is not None
    out.mkdir(parents=True, exist_ok=True)
    (out / "promptset.json").write_text(json.dumps({"type": "prompts", "lookdev_of": pdir.name, "style": sid}), encoding="utf-8")
    rows: list[dict] = []
    index: list[dict] = []
    for it in items:
        for v in range(VARIANTS):
            portrait = it["kind"] == "character" and it["view"] != "face"
            rows.append({"prompt": it["prompt"], "negative": f"{card['negative']}, {GLOBAL_NEGATIVE}", "width": h if portrait and w > h else w,
                         "height": w if portrait and w > h else h, "seed": seed + len(rows), "steps": 30, "guidance": 5})
            index.append({"row": len(rows), "key": it["key"], "variant": v + 1})
    with open(out / "all_images.csv", "w", newline="", encoding="utf-8") as fh:
        wr = csv.DictWriter(fh, list(rows[0]))
        wr.writeheader()
        wr.writerows(rows)
    _write(sdir(pdir, sid) / "lookdev.json", {"set": name, "rows": len(rows), "index": index, "items": items})
    return {"set": name, "rows": len(rows), "items": len(items)}


def lookdev_status(pdir: Path, sid: str) -> dict:
    """The look development of a style: each item with its rendered candidates (image paths relative to the prompt set) and the pick."""
    ld = _read(sdir(pdir, sid) / "lookdev.json")
    if not ld:
        return {"set": "", "rows": 0, "items": []}
    setdir = layout.find_dir(ld["set"])
    found: dict[int, str] = {}
    if setdir and (setdir / "images").is_dir():
        for model_dir in sorted((setdir / "images").iterdir()):
            for img in sorted(model_dir.glob("image-*.png")):
                m = re.match(r"image-(\d+)\.png$", img.name)
                if m:
                    found.setdefault(int(m.group(1)), img.relative_to(setdir).as_posix())
    picks = _read(sdir(pdir, sid) / "picks.json", {}) or {}
    items = []
    for it in ld["items"]:
        rows = [x for x in ld["index"] if x["key"] == it["key"]]
        items.append({**{k: it[k] for k in ("key", "kind", "name", "view")}, "candidates": [{"row": x["row"], "variant": x["variant"], "image": found.get(x["row"], "")} for x in rows],
                      "pick": picks.get(it["key"])})
    return {"set": ld["set"], "rows": ld["rows"], "items": items, "rendered": len(found)}


def pick(pdir: Path, sid: str, key: str, row: int) -> dict:
    ld = _read(sdir(pdir, sid) / "lookdev.json")
    if not ld or not any(x["key"] == key and x["row"] == row for x in ld["index"]):
        raise StyleError("that picture is not one of this item's candidates")
    picks = _read(sdir(pdir, sid) / "picks.json", {}) or {}
    picks[key] = row
    _write(sdir(pdir, sid) / "picks.json", picks)
    return picks


def gate_data(pdir: Path) -> list:
    """What the look-development approval covers: every style's card, translations and picks."""
    out = []
    for s in chosen(pdir):
        d = sdir(pdir, s["id"])
        out.append([s["id"], _read(d / "card.json"), _read(d / "translations.json"), _read(d / "picks.json")])
    return out


def summary(pdir: Path) -> dict:
    styles = []
    for s in chosen(pdir):
        d = sdir(pdir, s["id"])
        styles.append({**s, "card": _read(d / "card.json"), "translations": _read(d / "translations.json"), "lookdev": lookdev_status(pdir, s["id"])})
    return {"styles": styles, "gate": gates.status(pdir, "lookdev", gate_data(pdir))}


# ---------------------------------------------------------------------------------------------- engines
def fake_ask(pdir: Path) -> Ask:
    def ask(prompt: str, roles, step: str, validate: Callable[[dict], None]) -> dict:
        if step.startswith("style card"):
            sid = step.split(": ", 1)[1]
            look = production.STYLES.get(sid, (sid, sid))[1]
            d: dict = {"medium": look.split(":")[0], "materials": look, "rendering": "soft detail", "lighting_language": "soft key, gentle fill",
                       "palette": "muted blues and warm amber", "grade": "gentle contrast", "prefix": f"{production.STYLES.get(sid, (sid,))[0]} film still",
                       "suffix": "cinematic composition, high detail", "negative": "blurry, low quality"}
        else:
            book = continuity_book.load(pdir)
            d = {kind: {c["name"]: f"made in this style, {c['name'].lower()} kept recognisable" for c in book.get(kind, [])} for kind in ("characters", "locations", "props")}
        validate(d)
        return d
    return ask


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("project")
    ap.add_argument("--style", default="", help="only this style (default: every chosen style)")
    ap.add_argument("--engine", default="claude", choices=["claude", "fcc-claude", "codex", "fcc-codex", "hf", "local", "fake"])
    ap.add_argument("--model", default=None)
    a = ap.parse_args(argv)
    pdir = layout.project_dir(a.project, "book")
    if not pdir.is_dir():
        print(f"no book called {a.project}", flush=True)
        return 1
    if a.engine == "fake":
        ask = fake_ask(pdir)
    else:
        import bookkit

        def ask(prompt, roles, step, validate):
            return bookkit.llm_json(prompt, crew.system(roles, pdir, step), model=a.model, engine=a.engine, validate=validate)
    try:
        todo = [s for s in chosen(pdir) if not a.style or s["id"] == a.style]
        if not todo:
            raise StyleError(f"{a.style} is not one of this book's styles")
        for i, s in enumerate(todo, 1):
            print(f"Your art director and colorist are writing the {s['name']} style card ({i} of {len(todo)})", flush=True)
            write_card(pdir, s["id"], ask)
            print(f"Your character designer is translating the cast into {s['name']}", flush=True)
            write_translations(pdir, s["id"], ask)
            r = write_lookdev(pdir, s["id"])
            print(f"Look development prompts for {s['name']}: {r['items']} sheets and key art, {r['rows']} pictures to render (prompt set {r['set']})", flush=True)
    except (StyleError, RuntimeError, ValueError) as e:
        print(f"The styles were not written: {e}", flush=True)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
