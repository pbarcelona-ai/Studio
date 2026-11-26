"""Deterministic 60 fps Code-Drawn Animation & Title-Card Pack for Pistachio's Studio.

Inspired by Lemo-Opuscar, HandDraw-Skill, Anidoodle, Manim, and Remotion coded animations:
renders zero-hallucination, crisp animated title cards, chalkboard hand-drawn reveals,
Prussian-blue engineering blueprint diagrams, golden neon kinetic typography, paper-cutout
credits, and 9:16 kinetic hook cards directly to MP4 via Pillow + FFmpeg (100% local, zero GPU/API),
while also writing a standalone HTML/SVG composition alongside the MP4 for HyperFrames/Remotion.
"""
from __future__ import annotations

import html
import math
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont

CODE_DRAWN_TEMPLATES: list[dict[str, str]] = [
    {
        "id": "cinema_title_card",
        "name": "Cinema Title Card & Chapter Opener",
        "icon": "🎬",
        "summary": "Deep midnight cinema canvas with animated gold rule reveal, tracking title fade, and subtle letterbox framing.",
    },
    {
        "id": "chalkboard_handdraw",
        "name": "Chalkboard Doodle Reveal (HandDraw)",
        "icon": "🖍️",
        "summary": "Green slate classroom chalkboard with wooden border, progressive white & crimson chalk strokes, and underline callouts.",
    },
    {
        "id": "blueprint_diagram",
        "name": "Blueprint / Line Diagram Explainer",
        "icon": "📐",
        "summary": "Prussian-blue cyanotype drafting grid with animated white vector nodes, rotating construction rings, and technical callouts.",
    },
    {
        "id": "golden_neon_kinetic",
        "name": "Golden Neon Glow Kinetic Card",
        "icon": "✨",
        "summary": "Pitch-black stage with dashed glowing golden perimeter lines, pulsing floor spotlight rings, and luminous headline.",
    },
    {
        "id": "paper_cutout_credits",
        "name": "Storybook Paper-Cutout Credits",
        "icon": "✂️",
        "summary": "Warm layered cardstock cards sliding cleanly into frame with tactile drop shadows for storybook intros or end credits.",
    },
    {
        "id": "kinetic_quote_card",
        "name": "Kinetic Word-Pop Hook Card (Shorts/Reels)",
        "icon": "⚡",
        "summary": "High-retention word-by-word highlight animation designed for 9:16 Reels/Shorts hooks and chapter intros.",
    },
]


def _load_font(size: int, bold: bool = True) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    candidates = [
        "C:/Windows/Fonts/arialbd.ttf" if bold else "C:/Windows/Fonts/arial.ttf",
        "C:/Windows/Fonts/segoeuib.ttf" if bold else "C:/Windows/Fonts/segoeui.ttf",
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    ]
    for fp in candidates:
        if Path(fp).is_file():
            try:
                return ImageFont.truetype(fp, size)
            except OSError:
                continue
    return ImageFont.load_default()


def _ease_out_cubic(t: float) -> float:
    x = max(0.0, min(1.0, t))
    return 1.0 - (1.0 - x) ** 3


def _draw_centered(draw: ImageDraw.ImageDraw, text: str, cx: int, y: int, font: Any, fill: tuple[int, int, int]) -> None:
    bbox = draw.textbbox((0, 0), text, font=font)
    tw = bbox[2] - bbox[0]
    draw.text((cx - tw // 2, y), text, font=font, fill=fill)


def _render_frame(
    template_id: str,
    w: int,
    h: int,
    t: float,
    duration: float,
    title: str,
    subtitle: str,
    bullets: list[str],
) -> Image.Image:
    p = max(0.0, min(1.0, t / max(0.1, duration)))
    e = _ease_out_cubic(min(1.0, p / 0.45))
    cx, cy = w // 2, h // 2
    scale = min(w, h) / 1080.0
    f_title = _load_font(max(24, int(74 * scale)), bold=True)
    f_sub = _load_font(max(16, int(34 * scale)), bold=False)
    f_item = _load_font(max(15, int(28 * scale)), bold=True)

    if template_id == "chalkboard_handdraw":
        im = Image.new("RGB", (w, h), (22, 54, 41))
        draw = ImageDraw.Draw(im)
        # Wooden chalk frame
        bw = max(12, int(22 * scale))
        draw.rectangle([0, 0, w - 1, h - 1], outline=(112, 72, 38), width=bw)
        # Progressive title reveal
        vis_n = max(1, int(len(title) * min(1.0, p / 0.40)))
        _draw_centered(draw, title[:vis_n], cx, int(h * 0.24), f_title, (242, 245, 236))
        # Red chalk underline sweeps left-to-right
        line_w = int(w * 0.46 * _ease_out_cubic(min(1.0, max(0.0, (p - 0.15) / 0.35))))
        if line_w > 4:
            uy = int(h * 0.36)
            draw.line([(cx - line_w // 2, uy), (cx + line_w // 2, uy)], fill=(239, 83, 80), width=max(3, int(6 * scale)))
        if subtitle and p > 0.30:
            _draw_centered(draw, subtitle, cx, int(h * 0.42), f_sub, (226, 232, 220))
        for idx, b in enumerate(bullets[:4]):
            bp = (p - (0.42 + idx * 0.12)) / 0.14
            if bp > 0:
                y_pos = int(h * 0.54 + idx * int(58 * scale))
                _draw_centered(draw, f"✓  {b}", cx, y_pos, f_item, (254, 240, 138))
        return im

    if template_id == "blueprint_diagram":
        im = Image.new("RGB", (w, h), (16, 52, 96))
        draw = ImageDraw.Draw(im)
        step = max(24, int(48 * scale))
        for x in range(0, w, step):
            draw.line([(x, 0), (x, h)], fill=(28, 74, 128), width=1)
        for y in range(0, h, step):
            draw.line([(0, y), (w, y)], fill=(28, 74, 128), width=1)
        # Rotating geometric construction circle + orbiting dot nodes
        rad = int(min(w, h) * 0.28 * e)
        if rad > 10:
            draw.ellipse([cx - rad, cy - rad, cx + rad, cy + rad], outline=(186, 230, 253), width=2)
            for k in range(3):
                ang = p * 2.0 * math.pi + k * (2.0 * math.pi / 3.0)
                nx = int(cx + math.cos(ang) * rad)
                ny = int(cy + math.sin(ang) * rad)
                dr = max(4, int(8 * scale))
                draw.ellipse([nx - dr, ny - dr, nx + dr, ny + dr], fill=(240, 249, 255))
        _draw_centered(draw, title.upper(), cx, int(h * 0.14), f_title, (240, 249, 255))
        if subtitle:
            _draw_centered(draw, subtitle, cx, int(h * 0.26), f_sub, (186, 230, 253))
        for idx, b in enumerate(bullets[:3]):
            if p >= 0.30 + idx * 0.16:
                y_pos = int(h * 0.72 + idx * int(46 * scale))
                _draw_centered(draw, f"[0{idx + 1}] {b}", cx, y_pos, f_item, (224, 242, 254))
        return im

    if template_id == "golden_neon_kinetic":
        im = Image.new("RGB", (w, h), (6, 7, 10))
        draw = ImageDraw.Draw(im)
        pulse = 0.85 + 0.15 * math.sin(p * 4.0 * math.pi)
        gold = (int(250 * pulse), int(204 * pulse), int(21 * pulse))
        # Dashed glowing border
        pad = max(20, int(44 * scale))
        seg = max(14, int(28 * scale))
        for x in range(pad, w - pad, seg * 2):
            draw.line([(x, pad), (min(w - pad, x + seg), pad)], fill=gold, width=3)
            draw.line([(x, h - pad), (min(w - pad, x + seg), h - pad)], fill=gold, width=3)
        # Concentric floor spotlight ring
        rx = int(w * 0.26 * e)
        ry = int(h * 0.06 * e)
        if rx > 10 and ry > 4:
            draw.ellipse([cx - rx, int(h * 0.78) - ry, cx + rx, int(h * 0.78) + ry], outline=(245, 158, 11), width=3)
        _draw_centered(draw, title, cx, int(h * 0.34 - (1.0 - e) * 30), f_title, gold)
        if subtitle and p > 0.25:
            _draw_centered(draw, subtitle, cx, int(h * 0.49), f_sub, (254, 243, 199))
        return im

    if template_id == "paper_cutout_credits":
        im = Image.new("RGB", (w, h), (244, 236, 220))
        draw = ImageDraw.Draw(im)
        card_w, card_h = int(w * 0.76), int(h * 0.62)
        slide_y = int((1.0 - e) * h * 0.35)
        x0, y0 = (w - card_w) // 2, (h - card_h) // 2 + slide_y
        # Layered drop shadow + warm cardstock card
        sh = max(8, int(16 * scale))
        draw.rectangle([x0 + sh, y0 + sh, x0 + card_w + sh, y0 + card_h + sh], fill=(195, 182, 160))
        draw.rectangle([x0, y0, x0 + card_w, y0 + card_h], fill=(255, 250, 240), outline=(180, 83, 9), width=4)
        _draw_centered(draw, title, cx, y0 + int(card_h * 0.16), f_title, (41, 37, 36))
        if subtitle:
            _draw_centered(draw, subtitle, cx, y0 + int(card_h * 0.38), f_sub, (120, 113, 108))
        for idx, b in enumerate(bullets[:4]):
            _draw_centered(draw, b, cx, y0 + int(card_h * 0.55) + idx * int(44 * scale), f_item, (180, 83, 9))
        return im

    if template_id == "kinetic_quote_card":
        im = Image.new("RGB", (w, h), (15, 23, 42))
        draw = ImageDraw.Draw(im)
        words = [w0 for w0 in f"{title} {subtitle}".split() if w0]
        active_idx = min(len(words) - 1, int(p * len(words))) if words else 0
        # Render up to 3 lines of words, highlighting the active word in electric amber
        line_words: list[list[tuple[int, str]]] = [[]]
        for wi, word in enumerate(words[:18]):
            if len(line_words[-1]) >= 3:
                line_words.append([])
            line_words[-1].append((wi, word))
        start_y = cy - (len(line_words) * int(92 * scale)) // 2
        for li, row in enumerate(line_words):
            y_pos = start_y + li * int(92 * scale)
            txt_full = " ".join(w0 for _, w0 in row)
            bbox_all = draw.textbbox((0, 0), txt_full, font=f_title)
            cur_x = cx - (bbox_all[2] - bbox_all[0]) // 2
            for wi, word in row:
                col = (250, 204, 21) if wi == active_idx else ((248, 250, 252) if wi < active_idx else (71, 85, 105))
                draw.text((cur_x, y_pos), word, font=f_title, fill=col)
                wb = draw.textbbox((0, 0), word + " ", font=f_title)
                cur_x += wb[2] - wb[0]
        return im

    # Default: cinema_title_card
    im = Image.new("RGB", (w, h), (10, 13, 20))
    draw = ImageDraw.Draw(im)
    # Cinema letterbox bars
    bar_h = int(h * 0.09)
    draw.rectangle([0, 0, w, bar_h], fill=(0, 0, 0))
    draw.rectangle([0, h - bar_h, w, h], fill=(0, 0, 0))
    # Expanding gold horizon rule
    rw = int(w * 0.42 * e)
    draw.line([(cx - rw // 2, cy - int(18 * scale)), (cx + rw // 2, cy - int(18 * scale))], fill=(245, 158, 11), width=3)
    fade = min(1.0, p / 0.35)
    t_col = (int(248 * fade), int(250 * fade), int(252 * fade))
    s_col = (int(203 * fade), int(213 * fade), int(225 * fade))
    _draw_centered(draw, title.upper(), cx, cy - int(115 * scale - (1.0 - e) * 24), f_title, t_col)
    if subtitle:
        _draw_centered(draw, subtitle, cx, cy + int(18 * scale), f_sub, s_col)
    return im


def render_code_drawn_clip(
    slug: str,
    pd: Path,
    *,
    template_id: str = "cinema_title_card",
    title: str = "",
    subtitle: str = "",
    bullets: list[str] | None = None,
    aspect: str = "16:9",
    duration: float = 4.0,
    fps: int = 30,
) -> dict[str, Any]:
    """Render a deterministic code-drawn animation clip to `exports/code_drawn/<safe>.mp4` + HTML twin."""
    ff = shutil.which("ffmpeg")
    if not ff:
        try:
            import imageio_ffmpeg
            ff = imageio_ffmpeg.get_ffmpeg_exe()
        except ImportError as e:
            raise RuntimeError("ffmpeg is required to encode code-drawn MP4 clips") from e

    valid_ids = {t["id"] for t in CODE_DRAWN_TEMPLATES}
    tid = template_id if template_id in valid_ids else "cinema_title_card"
    clean_title = str(title or slug.replace("_", " ").title()).strip()
    clean_sub = str(subtitle or "").strip()
    clean_bullets = [str(b).strip() for b in (bullets or []) if str(b).strip()][:5]
    dur = max(2.0, min(12.0, float(duration or 4.0)))
    safe_fps = max(12, min(60, int(fps or 30)))
    w, h = (1080, 1920) if aspect == "9:16" else (1280, 720)
    total_frames = max(12, int(round(dur * safe_fps)))

    out_dir = pd / "exports" / "code_drawn"
    out_dir.mkdir(parents=True, exist_ok=True)
    safe_name = re.sub(r"[^a-z0-9]+", "_", f"{tid}_{clean_title[:24]}".lower()).strip("_") or tid
    out_mp4 = out_dir / f"{safe_name}.mp4"
    out_html = out_dir / f"{safe_name}.html"

    with tempfile.TemporaryDirectory(prefix="codedrawn-") as tmp:
        tmp_dir = Path(tmp)
        for fi in range(total_frames):
            frame_im = _render_frame(tid, w, h, fi / float(safe_fps), dur, clean_title, clean_sub, clean_bullets)
            frame_im.save(tmp_dir / f"f_{fi:04d}.png", "PNG")
        cmd = [
            ff, "-y", "-v", "error",
            "-framerate", str(safe_fps),
            "-i", str(tmp_dir / "f_%04d.png"),
            "-c:v", "libx264", "-pix_fmt", "yuv420p", "-movflags", "+faststart",
            str(out_mp4),
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True, stdin=subprocess.DEVNULL, timeout=120)
        if proc.returncode != 0 or not out_mp4.is_file():
            raise RuntimeError(f"FFmpeg code-drawn encode failed: {(proc.stderr or '')[-250:]}")

    # Save standalone deterministic HTML/HyperFrames twin
    html_doc = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>{html.escape(clean_title)}</title>
<style>html,body{{margin:0;width:{w}px;height:{h}px;background:#0a0d14;color:#f8fafc;display:grid;place-items:center;font-family:system-ui,sans-serif}}</style>
</head><body data-composition-id="{html.escape(tid)}" data-width="{w}" data-height="{h}" data-fps="{safe_fps}" data-duration="{dur}">
<div style="text-align:center;padding:48px"><h1>{html.escape(clean_title)}</h1><p>{html.escape(clean_sub)}</p></div>
</body></html>
"""
    out_html.write_text(html_doc, encoding="utf-8")

    return {
        "status": "ok",
        "project": slug,
        "template_id": tid,
        "aspect": aspect,
        "fps": safe_fps,
        "duration": dur,
        "video_url": f"/file/{slug}/exports/code_drawn/{out_mp4.name}",
        "download_url": f"/download/{slug}/exports/code_drawn/{out_mp4.name}",
        "html_url": f"/file/{slug}/exports/code_drawn/{out_html.name}",
    }
