"""One-click Pitch Deck (.pptx) & Production Breakdown (.xlsx) exporters for Pistachio's Studio (Step 22).

100% free & local using `python-pptx` and `openpyxl`. Automatically gathers:
- Book title, logline/overview, Step 09 visual style recipe
- Step 08/10 character dossiers & rendered turnarounds / 3-panel sheets
- Step 11 baselined set plates & location specs
- Step 12 shot list & Step 17 rendered storyboard keyframes
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

log = logging.getLogger("studio.exports_office")


def _read_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception as e:
        log.debug("failed reading %s: %s", path.name, e)
        return {}


def export_pitch_deck_pptx(slug: str, pd: Path) -> dict[str, Any]:
    """Generate a widescreen 16:9 dark-cinema Film Pitch Deck (.pptx) in `exports/<slug>_pitch_deck.pptx`."""
    from pptx import Presentation
    from pptx.dml.color import RGBColor
    from pptx.util import Inches, Pt
    from studio_app import keyframe_context as kfc

    ctx = kfc.load_keyframe_project_context(slug, pd)
    sl = _read_json(pd / "shots" / "shotlist.json")
    cov = _read_json(pd / "readin" / "coverage.json")
    scenes = [s for s in (sl.get("scenes") or []) if isinstance(s, dict)]
    total_shots = sum(len(s.get("shots") or []) for s in scenes)
    total_sec = sum(float(sh.get("seconds") or 4.0) for s in scenes for sh in (s.get("shots") or []) if isinstance(sh, dict))

    title_str = str(cov.get("title") or slug.replace("_", " ").title()).strip()
    logline = str(cov.get("logline") or cov.get("premise") or cov.get("summary") or f"An animated film adaptation of {title_str}.").strip()

    prs = Presentation()
    prs.slide_width = Inches(13.333)
    prs.slide_height = Inches(7.5)
    blank = prs.slide_layouts[6]

    bg_dark = RGBColor(11, 14, 20)
    card_bg = RGBColor(19, 25, 38)
    gold = RGBColor(245, 158, 11)
    text_light = RGBColor(241, 245, 249)
    text_muted = RGBColor(148, 163, 184)

    def _new_dark_slide():
        slide = prs.slides.add_slide(blank)
        fill = slide.background.fill
        fill.solid()
        fill.fore_color.rgb = bg_dark
        return slide

    def _add_text(slide, left: float, top: float, w: float, h: float, text: str, *, size: int = 16, bold: bool = False, color: RGBColor = text_light):
        tb = slide.shapes.add_textbox(Inches(left), Inches(top), Inches(w), Inches(h))
        tf = tb.text_frame
        tf.word_wrap = True
        p = tf.paragraphs[0]
        run = p.add_run()
        run.text = text
        run.font.size = Pt(size)
        run.font.bold = bold
        run.font.color.rgb = color
        return tb

    def _safe_add_pic(slide, img_path: Path | None, left: float, top: float, max_w: float, max_h: float) -> bool:
        if not img_path or not img_path.is_file() or img_path.stat().st_size <= 100:
            return False
        try:
            from PIL import Image
            with Image.open(img_path) as im:
                iw, ih = im.size
            if iw <= 0 or ih <= 0:
                return False
            ratio = min(max_w / float(iw), max_h / float(ih))
            w_in = iw * ratio
            h_in = ih * ratio
            ox = left + (max_w - w_in) / 2.0
            oy = top + (max_h - h_in) / 2.0
            slide.shapes.add_picture(str(img_path), Inches(ox), Inches(oy), width=Inches(w_in), height=Inches(h_in))
            return True
        except Exception as e:
            log.debug("skipped pptx image %s: %s", img_path, e)
            return False

    # --- Slide 1: Cover ---
    s1 = _new_dark_slide()
    _add_text(s1, 0.8, 0.7, 11.7, 0.5, "PISTACHIO'S STUDIO · FILM PITCH DECK", size=12, bold=True, color=gold)
    _add_text(s1, 0.8, 1.3, 6.2, 1.6, title_str, size=40, bold=True, color=text_light)
    _add_text(s1, 0.8, 3.1, 6.0, 2.2, logline[:420], size=16, color=text_muted)
    stats_line = f"{len(scenes)} Scenes  ·  {total_shots} Shots  ·  ~{int(round(total_sec))}s Runtime  ·  Look: {ctx['look']}"
    _add_text(s1, 0.8, 6.4, 11.5, 0.5, stats_line, size=14, bold=True, color=gold)

    hero_img: Path | None = None
    kf_files = sorted((pd / "keyframes").glob("*.png")) if (pd / "keyframes").is_dir() else []
    if kf_files:
        hero_img = kf_files[0]
    elif ctx["set_images"]:
        hero_img = next(iter(ctx["set_images"].values()))
    _safe_add_pic(s1, hero_img, 7.1, 1.3, 5.5, 4.7)

    # --- Slide 2: Visual Direction & Style Recipe ---
    s2 = _new_dark_slide()
    _add_text(s2, 0.8, 0.6, 11.7, 0.6, "VISUAL DIRECTION & ART STYLE", size=24, bold=True, color=gold)
    _add_text(s2, 0.8, 1.4, 11.7, 0.5, f"Active Visual Look: {ctx['look']}", size=18, bold=True, color=text_light)
    _add_text(s2, 0.8, 2.1, 11.7, 2.0, f"Style Positives:\n{ctx['style_prefix'][:600]}", size=14, color=text_muted)
    if ctx["style_negatives"]:
        _add_text(s2, 0.8, 4.4, 11.7, 1.4, f"Style Guardrails (Avoid):\n{ctx['style_negatives'][:400]}", size=13, color=text_muted)

    # --- Slide 3+: Cast & Character Sheets (up to 3 per slide, max 9 cast) ---
    cast_items = list(ctx["cast_profiles"].values())[:9]
    for i in range(0, len(cast_items), 3):
        chunk = cast_items[i : i + 3]
        sc_slide = _new_dark_slide()
        _add_text(sc_slide, 0.8, 0.5, 11.7, 0.6, "CAST & CHARACTER DESIGN", size=24, bold=True, color=gold)
        for col_idx, rec in enumerate(chunk):
            x = 0.8 + col_idx * 4.05
            shape = sc_slide.shapes.add_shape(1, Inches(x), Inches(1.3), Inches(3.8), Inches(5.6))
            shape.fill.solid()
            shape.fill.fore_color.rgb = card_bg
            shape.line.color.rgb = RGBColor(51, 65, 85)
            rp, _rurl, _rsrc = kfc.find_character_visual_ref(ctx, rec["name"])
            _safe_add_pic(sc_slide, rp, x + 0.15, 1.45, 3.5, 3.1)
            _add_text(sc_slide, x + 0.15, 4.65, 3.5, 0.45, rec["name"], size=16, bold=True, color=text_light)
            _add_text(sc_slide, x + 0.15, 5.1, 3.5, 1.7, str(rec.get("token") or "")[:190], size=11, color=text_muted)

    # --- World & Step 11 Set Plates (2 per slide, max 6 sets) ---
    set_entries = list(ctx["set_images"].items())[:6]
    for i in range(0, len(set_entries), 2):
        chunk = set_entries[i : i + 2]
        st_slide = _new_dark_slide()
        _add_text(st_slide, 0.8, 0.5, 11.7, 0.6, "WORLD & LOCKED SET PLATES (STEP 11)", size=24, bold=True, color=gold)
        for col_idx, (nk, spath) in enumerate(chunk):
            x = 0.8 + col_idx * 6.0
            loc_meta = ctx["locations"].get(nk) or {}
            lbl = str(loc_meta.get("name") or nk.title())
            _safe_add_pic(st_slide, spath, x, 1.35, 5.7, 3.6)
            _add_text(st_slide, x, 5.1, 5.7, 0.45, lbl, size=16, bold=True, color=text_light)
            _add_text(st_slide, x, 5.55, 5.7, 1.4, str(loc_meta.get("token") or "")[:240], size=11, color=text_muted)

    # --- Storyboard Showcase (up to 8 keyframes, 4 per slide) ---
    for i in range(0, min(8, len(kf_files)), 4):
        chunk = kf_files[i : i + 4]
        kf_slide = _new_dark_slide()
        _add_text(kf_slide, 0.8, 0.45, 11.7, 0.55, "STORYBOARD KEYFRAMES (STEP 17)", size=22, bold=True, color=gold)
        for idx, kfp in enumerate(chunk):
            r, c = divmod(idx, 2)
            x = 0.8 + c * 6.0
            y = 1.15 + r * 3.05
            _safe_add_pic(kf_slide, kfp, x, y, 5.65, 2.55)
            _add_text(kf_slide, x, y + 2.58, 5.65, 0.35, kfp.stem, size=12, bold=True, color=text_muted)

    exp_dir = pd / "exports"
    exp_dir.mkdir(parents=True, exist_ok=True)
    out_pptx = exp_dir / f"{slug}_pitch_deck.pptx"
    prs.save(str(out_pptx))
    return {
        "status": "ok",
        "target": "pitch_pptx",
        "slides": len(prs.slides),
        "path": str(out_pptx),
        "download_url": f"/download/{slug}/exports/{out_pptx.name}",
    }


def export_production_sheet_xlsx(slug: str, pd: Path) -> dict[str, Any]:
    """Generate a formatted multi-tab Production Breakdown workbook (.xlsx) in `exports/<slug>_production_breakdown.xlsx`."""
    import openpyxl
    from openpyxl.styles import Alignment, Font, PatternFill
    from studio_app import keyframe_context as kfc

    ctx = kfc.load_keyframe_project_context(slug, pd)
    sl = _read_json(pd / "shots" / "shotlist.json")
    scenes = [s for s in (sl.get("scenes") or []) if isinstance(s, dict)]

    wb = openpyxl.Workbook()
    hdr_fill = PatternFill(start_color="1E293B", end_color="1E293B", fill_type="solid")
    hdr_font = Font(bold=True, color="F8FAFC")

    def _style_header(ws, headers: list[str]) -> None:
        ws.append(headers)
        for col_idx in range(1, len(headers) + 1):
            cell = ws.cell(row=1, column=col_idx)
            cell.fill = hdr_fill
            cell.font = hdr_font
            cell.alignment = Alignment(vertical="center")
        ws.freeze_panes = "A2"

    def _autofit(ws) -> None:
        for col in ws.columns:
            max_len = 10
            col_letter = col[0].column_letter
            for cell in col:
                val = str(cell.value or "")
                max_len = max(max_len, min(52, len(val) + 2))
            ws.column_dimensions[col_letter].width = max_len

    # --- Tab 1: Shot List ---
    ws_shots = wb.active
    assert ws_shots is not None
    ws_shots.title = "Shot List"
    _style_header(
        ws_shots,
        ["Shot ID", "Scene", "Heading", "Type", "Lens (mm)", "Movement", "Duration (s)", "Characters", "Action / Composition", "Keyframe", "Video"],
    )
    row_count = 0
    for sc in scenes:
        sc_id = str(sc.get("id") or sc.get("scene") or "S001")
        heading = str(sc.get("heading") or "")
        for idx, sh in enumerate(sc.get("shots") or [], start=1):
            if not isinstance(sh, dict):
                continue
            sid = f"{sc_id}-{int(sh.get('n') or idx):02d}"
            has_kf = (pd / "keyframes" / f"{sid}.png").is_file()
            has_vid = (pd / "videos" / f"{sid}.mp4").is_file()
            ws_shots.append([
                sid,
                sc_id,
                heading,
                str(sh.get("type") or "MS"),
                int(sh.get("lens_mm") or 35),
                str(sh.get("movement") or "static"),
                float(sh.get("seconds") or 4.0),
                ", ".join(str(c) for c in (sh.get("characters") or []) if c),
                str(sh.get("action") or sh.get("composition") or ""),
                "Yes" if has_kf else "Pending",
                "Yes" if has_vid else "Pending",
            ])
            row_count += 1
    if row_count > 0:
        tot_row = row_count + 2
        ws_shots.cell(row=tot_row, column=1, value="TOTAL").font = Font(bold=True)
        ws_shots.cell(row=tot_row, column=7, value=f"=SUM(G2:G{row_count + 1})").font = Font(bold=True)
    _autofit(ws_shots)

    # --- Tab 2: Cast & Wardrobe ---
    ws_cast = wb.create_sheet("Cast & Wardrobe")
    _style_header(ws_cast, ["Character", "Archetype", "Visual Dossier / Wardrobe", "Turnaround Ref"])
    for rec in ctx["cast_profiles"].values():
        rp, _rurl, rsrc = kfc.find_character_visual_ref(ctx, rec["name"])
        ws_cast.append([
            rec["name"],
            str(rec.get("archetype") or "human"),
            str(rec.get("token") or ""),
            f"{rp.name} ({rsrc})" if rp else "Missing",
        ])
    _autofit(ws_cast)

    # --- Tab 3: Locations & Sets ---
    ws_sets = wb.create_sheet("Locations & Sets")
    _style_header(ws_sets, ["Location", "Description", "Lighting", "Step 11 Set Plate"])
    seen_locs: set[str] = set()
    for nk, loc in ctx["locations"].items():
        seen_locs.add(nk)
        sp = ctx["set_images"].get(nk)
        ws_sets.append([
            str(loc.get("name") or nk),
            str(loc.get("token") or ""),
            str(loc.get("lighting") or ""),
            sp.name if sp else "Missing",
        ])
    for nk, sp in ctx["set_images"].items():
        if nk not in seen_locs:
            ws_sets.append([nk.title(), "", "", sp.name])
    _autofit(ws_sets)

    exp_dir = pd / "exports"
    exp_dir.mkdir(parents=True, exist_ok=True)
    out_xlsx = exp_dir / f"{slug}_production_breakdown.xlsx"
    wb.save(str(out_xlsx))
    return {
        "status": "ok",
        "target": "prod_xlsx",
        "shots": row_count,
        "cast": len(ctx["cast_profiles"]),
        "sets": len(ctx["set_images"]),
        "path": str(out_xlsx),
        "download_url": f"/download/{slug}/exports/{out_xlsx.name}",
    }
