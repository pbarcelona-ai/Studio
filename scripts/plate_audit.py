"""Per-plate consistency contact sheets & close-up face crop reference helper for Pistachio's Studio.

Adapted from Trendjack Animator's plate-first QA workflow (`plate_check.py` + close-up face-crop lock):
1. `ensure_face_closeup_crop(src_img, out_path)`: extracts and caches a clean portrait head/face
   crop from a 3-panel character sheet or full-body turnaround so close-up shots (CU / MCU / ECU)
   never lose facial identity because the face was too small on a wide sheet.
2. `audit_project_plates(slug, pd)`: inspects all Step 10 character plates, Step 11 set plates,
   and Step 17 rendered keyframes, builds one side-by-side contact sheet JPEG per plate
   (`qa/plate_sheets/plate_<kind>_<id>.jpg` with the approved plate as Tile 1 followed by every
   keyframe that used it), and reports any unreferenced/unplated keyframes or missing plates.
"""
from __future__ import annotations

import json
import math
import re
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageOps

_CLOSEUP_SHOT_RE = re.compile(
    r"\b(?:ecu|xcu|cu|mcu|close[\s-]*up|tight\s+close|extreme\s+close|medium\s+close|face\s+shot|portrait\s+shot)\b",
    re.IGNORECASE,
)


def is_closeup_shot(shot: dict[str, Any] | None, prompt: str = "") -> bool:
    """Return True when a shot's camera type or prompt calls for a close-up / MCU / ECU framing."""
    parts: list[str] = []
    if isinstance(shot, dict):
        parts.append(str(shot.get("type") or ""))
        parts.append(str(shot.get("composition") or ""))
        parts.append(str(shot.get("shot_size") or ""))
    if prompt:
        parts.append(str(prompt)[:280])
    combined = " ".join(p for p in parts if p)
    return bool(_CLOSEUP_SHOT_RE.search(combined))


def ensure_face_closeup_crop(src_path: Path, cache_dir: Path, char_slug: str) -> Path | None:
    """Create (or reuse cached) a tight face/upper-body crop from a turnaround or 3-panel sheet.

    - For wide 3-panel sheets (aspect >= 1.25, e.g. 4:3 or 16:9 where panel 1 on the left is the
      close-up portrait or front view), crops the left third upper 68%.
    - For single-figure full-body portrait turnarounds, crops the upper-center 44% (head + shoulders).
    - Reuses cached crop if newer than `src_path`.
    """
    if not src_path.is_file() or src_path.stat().st_size <= 100:
        return None
    # If the source is ALREADY a dedicated face close-up, use it directly
    stem_low = src_path.stem.lower()
    if stem_low.endswith("_face") or stem_low.endswith("_face_crop") or "closeup" in stem_low:
        return src_path

    cache_dir.mkdir(parents=True, exist_ok=True)
    safe = re.sub(r"[^a-z0-9_-]+", "_", str(char_slug or src_path.stem).lower()).strip("_") or "char"
    out_path = cache_dir / f"{safe}_face_crop.png"
    try:
        if out_path.is_file() and out_path.stat().st_size > 100 and out_path.stat().st_mtime >= src_path.stat().st_mtime:
            return out_path
    except OSError:
        pass

    try:
        with Image.open(src_path) as raw_im:
            im = ImageOps.exif_transpose(raw_im).convert("RGB")
            w, h = im.size
            if w < 64 or h < 64:
                return None
            aspect = w / float(h)
            if "sheet" in stem_low or aspect >= 1.25:
                # 3-panel character sheet: left panel is close-up portrait / front face
                x0 = 0
                x1 = max(64, int(round(w * 0.35)))
                y0 = 0
                y1 = max(64, int(round(h * 0.72)))
            else:
                # Single full-body turnaround: head & shoulders occupy top-center ~44%
                x0 = int(round(w * 0.16))
                x1 = int(round(w * 0.84))
                y0 = 0
                y1 = max(64, int(round(h * 0.46)))
            crop = im.crop((x0, y0, x1, y1))
            # Upscale tiny crops cleanly so vision/image models get crisp facial features
            if min(crop.size) < 384:
                scale = 512.0 / float(max(1, max(crop.size)))
                crop = crop.resize(
                    (max(64, int(round(crop.width * scale))), max(64, int(round(crop.height * scale)))),
                    Image.Resampling.LANCZOS,
                )
            crop.save(out_path, "PNG")
        return out_path if out_path.is_file() and out_path.stat().st_size > 100 else None
    except Exception:
        return None


def _build_plate_contact_sheet(
    plate_path: Path,
    plate_label: str,
    still_items: list[tuple[str, Path]],
    out_jpg: Path,
    *,
    tile_w: int = 320,
    tile_h: int = 200,
    cols: int = 4,
) -> Path | None:
    """Render one JPEG sheet with the approved Plate as Tile #1 followed by every keyframe using it."""
    entries: list[tuple[str, Path, bool]] = [(f"PLATE: {plate_label}", plate_path, True)]
    for sid, sp in still_items:
        if sp.is_file() and sp.stat().st_size > 100:
            entries.append((sid, sp, False))
    if not plate_path.is_file() or plate_path.stat().st_size <= 100:
        return None

    eff_cols = max(1, min(cols, len(entries)))
    rows = math.ceil(len(entries) / eff_cols)
    pad = 10
    header_h = 26
    canvas_w = eff_cols * (tile_w + pad) + pad
    canvas_h = rows * (tile_h + header_h + pad) + pad
    sheet = Image.new("RGB", (canvas_w, canvas_h), (15, 23, 42))
    draw = ImageDraw.Draw(sheet)

    for idx, (label, fpath, is_plate) in enumerate(entries):
        r, c = divmod(idx, eff_cols)
        x = pad + c * (tile_w + pad)
        y = pad + r * (tile_h + header_h + pad)

        # Label bar (gold for approved plate, slate for shot still)
        bar_bg = (217, 119, 6) if is_plate else (30, 41, 59)
        bar_fg = (11, 14, 20) if is_plate else (226, 232, 240)
        draw.rectangle([x, y, x + tile_w, y + header_h], fill=bar_bg)
        draw.text((x + 8, y + 6), label[:40], fill=bar_fg)

        try:
            with Image.open(fpath) as raw_im:
                im = ImageOps.exif_transpose(raw_im).convert("RGB")
                im.thumbnail((tile_w, tile_h), Image.Resampling.LANCZOS)
                tile = Image.new("RGB", (tile_w, tile_h), (10, 13, 20))
                ox = (tile_w - im.width) // 2
                oy = (tile_h - im.height) // 2
                tile.paste(im, (ox, oy))
        except Exception:
            tile = Image.new("RGB", (tile_w, tile_h), (45, 20, 20))
        sheet.paste(tile, (x, y + header_h))
        border_col = (245, 158, 11) if is_plate else (51, 65, 85)
        draw.rectangle([x, y, x + tile_w - 1, y + header_h + tile_h - 1], outline=border_col, width=2 if is_plate else 1)

    out_jpg.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(out_jpg, "JPEG", quality=88)
    return out_jpg


def audit_project_plates(slug: str, pd: Path) -> dict[str, Any]:
    """Audit Step 10 character plates + Step 11 set plates against rendered Step 17 keyframes.

    Generates `qa/plate_sheets/plate_<kind>_<safe>.jpg` for each plate and persists a summary report
    to `qa/plate_audit.json`.
    """
    from studio_app.keyframe_context import (
        find_character_visual_ref,
        load_keyframe_project_context,
        match_location_context,
        match_wardrobe_state,
        resolve_shot_characters,
    )

    ctx = load_keyframe_project_context(slug, pd)
    sl_path = pd / "shots" / "shotlist.json"
    sl_data: dict[str, Any] = {}
    if sl_path.is_file():
        try:
            sl_data = json.loads(sl_path.read_text(encoding="utf-8")) or {}
        except Exception:
            sl_data = {}

    kf_dir = pd / "keyframes"
    out_dir = pd / "qa" / "plate_sheets"
    out_dir.mkdir(parents=True, exist_ok=True)

    # Map plate_key -> {"kind", "label", "path", "stills": [(shot_id, Path)]}
    plates_map: dict[str, dict[str, Any]] = {}
    missing_plates: list[dict[str, str]] = []
    unplated_stills: list[dict[str, Any]] = []
    total_rendered_stills = 0

    def _safe_id(text: str) -> str:
        return re.sub(r"[^a-z0-9]+", "_", str(text or "").lower()).strip("_")[:48] or "plate"

    for sc in sl_data.get("scenes") or []:
        if not isinstance(sc, dict):
            continue
        sc_id = str(sc.get("id") or sc.get("scene") or "S001")
        heading = str(sc.get("heading") or "")
        for idx, sh in enumerate(sc.get("shots") or [], start=1):
            if not isinstance(sh, dict):
                continue
            n = int(sh.get("n") or idx)
            shot_id = f"{sc_id}-{n:02d}"
            kf_png = kf_dir / f"{shot_id}.png"
            if not (kf_png.is_file() and kf_png.stat().st_size > 100):
                continue
            total_rendered_stills += 1
            shot_plates_found = 0

            # Characters in this shot
            chars = resolve_shot_characters(sh, sc_id, heading, ctx)
            for cname in chars:
                _, prefer_outfit = match_wardrobe_state(ctx, cname, sc_id, heading)
                rp, _rurl, _rsrc = find_character_visual_ref(ctx, cname, prefer_outfit=prefer_outfit)
                pkey = f"char_{_safe_id(cname)}"
                if rp and rp.is_file():
                    shot_plates_found += 1
                    rec = plates_map.setdefault(pkey, {"id": pkey, "kind": "character", "label": cname, "path": rp, "stills": []})
                    if all(s[0] != shot_id for s in rec["stills"]):
                        rec["stills"].append((shot_id, kf_png))
                else:
                    if not any(m["kind"] == "character" and m["name"] == cname for m in missing_plates):
                        missing_plates.append({"kind": "character", "name": cname, "step": "Step 10"})

            # Location / Set plate for this shot
            if heading:
                _loc_tok, set_img, matched_locs = match_location_context(ctx, heading)
                loc_label = matched_locs[0] if matched_locs else heading
                pkey = f"set_{_safe_id(loc_label)}"
                if set_img and set_img.is_file():
                    shot_plates_found += 1
                    rec = plates_map.setdefault(pkey, {"id": pkey, "kind": "location", "label": loc_label, "path": set_img, "stills": []})
                    if all(s[0] != shot_id for s in rec["stills"]):
                        rec["stills"].append((shot_id, kf_png))
                else:
                    if not any(m["kind"] == "location" and m["name"] == loc_label for m in missing_plates):
                        missing_plates.append({"kind": "location", "name": loc_label, "step": "Step 11"})

            if shot_plates_found == 0:
                unplated_stills.append({"shot_id": shot_id, "scene": sc_id, "heading": heading})

    sheets_out: list[dict[str, Any]] = []
    for pkey, rec in sorted(plates_map.items(), key=lambda kv: (kv[1]["kind"], kv[1]["label"].lower())):
        jpg_path = out_dir / f"plate_{pkey}.jpg"
        built = _build_plate_contact_sheet(rec["path"], rec["label"], rec["stills"], jpg_path)
        if built:
            rel = built.relative_to(pd).as_posix()
            sheets_out.append({
                "id": pkey,
                "kind": rec["kind"],
                "label": rec["label"],
                "still_count": len(rec["stills"]),
                "shot_ids": [s[0] for s in rec["stills"]],
                "sheet_url": f"/file/{slug}/{rel}",
                "plate_url": f"/file/{slug}/{rec['path'].relative_to(pd).as_posix()}" if rec["path"].is_relative_to(pd) else "",
            })

    warnings: list[str] = []
    char_plates = [s for s in sheets_out if s["kind"] == "character"]
    if len(char_plates) > 4:
        warnings.append(
            f"{len(char_plates)} recurring character plates active — inspect every face sheet closely to prevent identity drift."
        )
    if missing_plates:
        warnings.append(
            f"{len(missing_plates)} referenced cast/location plate(s) have no rendered image yet."
        )
    if unplated_stills:
        warnings.append(
            f"{len(unplated_stills)} rendered keyframe(s) had no matching Step 10 character or Step 11 set plate."
        )

    passed = (total_rendered_stills > 0) and (len(missing_plates) == 0) and (len(unplated_stills) == 0)
    report: dict[str, Any] = {
        "status": "ok",
        "project": slug,
        "passed": passed,
        "total_rendered_stills": total_rendered_stills,
        "plate_count": len(sheets_out),
        "sheets": sheets_out,
        "missing_plates": missing_plates,
        "unplated_stills": unplated_stills,
        "warnings": warnings,
    }
    report_path = pd / "qa" / "plate_audit.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report
