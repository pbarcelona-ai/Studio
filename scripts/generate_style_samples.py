"""Generate unique, canned animated GIF style previews for every built-in visual style in Step 09.

Each of the 46 built-in styles gets its own distinct character/scene subject (no repeated scenes),
rendered locally via `sd-cli` (`z-image-turbo`) and encoded into a lightweight looping animated GIF
(`web/static/img/style_samples/<style_id>.gif`) with motion cadence tailored to that style.
"""
from __future__ import annotations

import argparse
import math
import sys
import tempfile
import time
from pathlib import Path

from PIL import Image, ImageEnhance

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import character_types_registry as ctr  # noqa: E402
from local_runners.sd_cli_runner import SdCliRunner  # noqa: E402

OUT_DIR = ROOT / "web" / "static" / "img" / "style_samples"

# Distinct, iconic subject & scene tailored specifically to each style ID (zero repeats!)
STYLE_SUBJECTS: dict[str, str] = {
    "claymation": "a cheerful plump clay baker in a white apron kneading bread dough inside a cozy miniature terracotta bakery kitchen",
    "toy_bricks": "a smiling plastic brick minifigure astronaut planting a bright yellow flag on a studded grey brick lunar crater",
    "felt": "a tiny needle-felted red fox wearing a wool scarf roasting a marshmallow beside a miniature felt campfire",
    "plush_doll": "a stitched burlap rag-doll sailor with button eyes steering a patchwork sailboat across cloth waves",
    "puppet_muppet": "a fuzzy emerald-green fleece monster orchestra conductor waving a tiny baton on a miniature velvet theater stage",
    "papercraft": "a crisp folded origami clipper ship sailing across layered turquoise paper-cut ocean swells toward a paper lighthouse",
    "glazed_ceramic": "a hand-painted cobalt-and-gold porcelain koi fish and tiny ceramic dragon perched beside a glowing teahouse lantern",
    "tin_toy": "a retro 1950s wind-up lithographed red tin robot with a brass key marching across a sunlit wooden workshop bench",
    "paper_cutout": "a layered construction-paper great owl perched on an autumn oak branch framed by a glowing cut-paper harvest moon",
    "fabric_collage": "a cheerful patchwork stitched girl with braided yarn hair holding a coral-and-teal fabric pinwheel beside a tiny white felt rabbit in a stitched daisy garden",
    "anime": "a young traveler with a backpack standing on a sunlit coastal train platform as pink cherry blossoms drift in the sea breeze",
    "cartoon_2d": "an energetic cartoon beagle wearing red sneakers skateboarding over a fire hydrant down a sunny suburban street",
    "flat_vector": "a sleek geometric cyclist riding along a desert highway past terracotta mesas beneath a clean amber sunset",
    "comic_ink": "a caped nocturnal detective perched on a gothic rooftop gargoyle overlooking a dramatic rain-soaked city skyline",
    "watercolour": "a gentle woodland badger in a knitted vest holding a glowing brass lantern outside a mossy cottage at dusk",
    "midcentury_2d": "a stylish elongated black cat strolling past glowing 1950s teal-and-ochre jazz club doors",
    "travel_poster": "a streamlined art-deco silver express locomotive racing across a sunlit alpine stone viaduct over mountain pines",
    "ukiyo_e": "a lone wooden-hat fisherman rowing a narrow skiff beneath towering curling indigo ocean waves and Mount Fuji",
    "painted_sign": "a cheerful vintage roadside diner server carrying a steaming coffee pot and cherry pie on a sunny boardwalk",
    "scratchboard": "a snowy horned owl gliding silently over frosted pine silhouettes beneath a carved silver crescent moon",
    "charcoal_sketch": "a passionate street violinist bowing beside a tall rain-streaked Parisian studio window",
    "stained_glass": "a luminous jewel-toned phoenix rising with outstretched cobalt, ruby, and amber wings inside an arched cathedral frame",
    "ghibli_2d": "a joyful young airship mechanic waving from a windswept flower-covered cliff overlooking sunlit cumulus cloud seas",
    "pencil_flipbook": "a graceful ballet dancer mid-leap surrounded by gestural blue construction arcs on warm animation paper",
    "pixar_3d": "a wide-eyed young girl inventor holding a glowing jar of golden fireflies inside a cluttered warm attic workshop",
    "pixar_disney": "a friendly chestnut foal wearing a braided flower garland trotting down a lantern-lit storybook cobblestone lane",
    "painted_3d": "a young desert astronomer adjusting a gleaming brass telescope atop a sunlit sandstone observatory dome",
    "retro_low_poly": "a low-poly fantasy explorer holding a glowing cyan crystal sword before a misty stone castle drawbridge",
    "isometric_3d": "a charming miniature floating island bakery with a spinning wooden windmill, smoking brick chimney, and tiny pastry cart",
    "cyberpunk_3d": "a sleek hoverbike courier paused in a rain-slick neon alley under glowing magenta and cyan holographic signs",
    "soft_3d_explainer": "a friendly rounded glossy gardener watering sprouting pastel tulips inside a warm sunlit glass greenhouse",
    "cinematic_moody_3d": "a lone traveler in a long coat holding a crimson umbrella crossing a misty cyan-lit night bridge over dark reflections",
    "spiderverse_3d": "an acrobatic street-art runner vaulting mid-air between bold graphic skyscraper rooftops at golden hour",
    "arcane_painterly_3d": "a steampunk clockmaker apprentice holding a glowing turquoise crystal core inside a shadowed brass bell tower",
    "pixel_art_16bit": "a cloaked 16-bit pixel mage casting twinkling starlight beside an emerald forest waterfall shrine",
    "pixel_8bit_hud": "an 8-bit armored pixel knight jumping across floating stone platforms toward a sparkling golden treasure key",
    "rubber_hose": "a cheerful 1930s pie-eyed cartoon riverboat captain whistling at a wooden ship wheel with puffing smokestacks",
    "live_action": "a weathered lighthouse keeper in a yellow oilskin coat lifting a warm lantern against crashing twilight ocean surf",
    "noir": "a 1940s fedora-wearing private eye glancing at a pocket watch beneath a foggy iron streetlamp on wet cobblestones",
    "vintage_16mm": "a classic two-tone 1970s camper van parked beside tall golden pines overlooking a calm sunset mountain lake",
    "vintage_1940s_2d": "a friendly 1940s hand-drawn cartoon bear in a red wool coat and green felt hat smiling beside a woodland cabin",
    "hybrid_2d_live_action": "a real live-action smiling young man in a dark wool coat at a candlelit wooden tavern table while a vintage hand-drawn 2D bluebird perches on his mug",
    "chalkboard_doodle": "a chalk-drawn owl professor holding a bright red chalk umbrella with playful arrows and stars on a green classroom chalkboard",
    "golden_neon_sketch": "a graceful dancer drawn in glowing dashed golden lines spinning inside a luminous spotlight ring on a pitch-black stage",
    "line_diagram": "a clean articulated white-hairline sprinter figure with tiny dot joints and geometric drafting circles on a pure black background",
    "shadow_puppet": "an ornate articulated black silhouette princess and crested bird backlit against a glowing amber-and-indigo parchment screen",
    "risograph_zine": "a joyful bicyclist carrying a basket of coral wildflowers past teal park trees in 3-color indie risograph print",
    "blueprint_tech": "an intricate Victorian steampunk airship schematic drawn in crisp white technical lines on Prussian-blue blueprint paper",
}

STEPPED_STYLES = {
    "claymation", "toy_bricks", "felt", "plush_doll", "puppet_muppet",
    "papercraft", "paper_cutout", "fabric_collage", "glazed_ceramic", "tin_toy",
    "pixel_art_16bit", "pixel_8bit_hud", "retro_low_poly",
}
TWOS_STYLES = {
    "anime", "cartoon_2d", "comic_ink", "watercolour", "midcentury_2d",
    "ukiyo_e", "painted_sign", "scratchboard", "charcoal_sketch", "ghibli_2d",
    "pencil_flipbook", "vintage_1940s_2d", "chalkboard_doodle", "rubber_hose",
    "risograph_zine", "spiderverse_3d", "shadow_puppet",
}
GLOW_STYLES = {"golden_neon_sketch", "cyberpunk_3d", "stained_glass", "line_diagram", "cinematic_moody_3d", "blueprint_tech"}


def encode_style_gif(src_png: Path, out_gif: Path, style_id: str, width: int = 320, height: int = 200) -> None:
    """Create a smooth, lightweight looping animated GIF showcasing the style's motion cadence."""
    base = Image.open(src_png).convert("RGB")
    # Ensure plenty of margin for smooth pan/zoom without upscaling artifacts
    work_w, work_h = int(width * 1.14), int(height * 1.14)
    base = base.resize((work_w, work_h), Image.Resampling.LANCZOS)

    is_stepped = style_id in STEPPED_STYLES
    is_twos = style_id in TWOS_STYLES
    is_glow = style_id in GLOW_STYLES

    n_frames = 10 if is_stepped else (12 if is_twos else 16)
    duration_ms = 140 if is_stepped else (110 if is_twos else 85)

    frames: list[Image.Image] = []
    for i in range(n_frames):
        # Seamless ping-pong cosine cycle (0 -> 1 -> 0) so the loop never jumps
        t = 0.5 * (1.0 - math.cos(2.0 * math.pi * i / n_frames))
        zoom = 1.0 + 0.08 * t
        cw = int(work_w / zoom)
        ch = int(work_h / zoom)
        # Subtle horizontal pan + micro stop-motion jitter for tactile/stepped styles
        pan_x = int((work_w - cw) * (0.35 + 0.30 * t))
        pan_y = int((work_h - ch) * 0.50)
        if is_stepped:
            pan_x += (i % 2) * 2 - 1
            pan_y += ((i + 1) % 2) * 2 - 1
        x0 = max(0, min(work_w - cw, pan_x))
        y0 = max(0, min(work_h - ch, pan_y))
        crop = base.crop((x0, y0, x0 + cw, y0 + ch))

        resample = Image.Resampling.NEAREST if style_id in ("pixel_art_16bit", "pixel_8bit_hud") else Image.Resampling.LANCZOS
        frame = crop.resize((width, height), resample)

        if is_glow:
            # Subtle luminous breathing pulse
            bright = 1.0 + 0.08 * math.sin(2.0 * math.pi * i / n_frames)
            frame = ImageEnhance.Brightness(frame).enhance(bright)
        elif is_twos:
            # Subtle paper/cel warmth shimmer
            bright = 1.0 + 0.025 * (1 if i % 2 == 0 else -1)
            frame = ImageEnhance.Brightness(frame).enhance(bright)

        frames.append(frame.convert("P", palette=Image.Palette.ADAPTIVE, colors=160))

    out_gif.parent.mkdir(parents=True, exist_ok=True)
    frames[0].save(
        out_gif,
        save_all=True,
        append_images=frames[1:],
        duration=duration_ms,
        loop=0,
        optimize=True,
    )


def main() -> int:
    ap = argparse.ArgumentParser(description="Generate canned animated GIF style samples for Step 09.")
    ap.add_argument("--only", nargs="*", help="Only generate specific style IDs")
    ap.add_argument("--force", action="store_true", help="Regenerate even if GIF already exists")
    ap.add_argument("--steps", type=int, default=6, help="Diffusion steps for z-image-turbo (default: 6)")
    args = ap.parse_args()

    runner = SdCliRunner()
    if not runner.is_installed():
        print("ERROR: sd-cli not installed", file=sys.stderr)
        return 1
    ready = runner.ready_models()
    if not ready:
        print("ERROR: no ready sd-cli models found in models/sd_cli/", file=sys.stderr)
        return 1
    model_id = "z-image-turbo" if "z-image-turbo" in ready else ready[0]
    print(f"Using local GPU model: {model_id} (steps={args.steps})")

    styles = ctr.BUILTIN_STYLES
    if args.only:
        want = set(args.only)
        styles = [s for s in styles if s["id"] in want]

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    t_all = time.time()
    generated = 0
    skipped = 0

    with tempfile.TemporaryDirectory(prefix="style-samples-") as tmp:
        tmp_dir = Path(tmp)
        for idx, st in enumerate(styles, start=1):
            sid = st["id"]
            out_gif = OUT_DIR / f"{sid}.gif"
            if not args.force and out_gif.is_file() and out_gif.stat().st_size > 10_000:
                skipped += 1
                continue
            subject = STYLE_SUBJECTS.get(sid, f"a charming storybook explorer in a scenic landscape representing {st['name']}")
            prompt = f"{subject}. {st['positives']}. High craft, iconic composition, no text, no watermark."
            neg = ", ".join(x for x in (st.get("negatives", ""), "text, watermark, signature, logo, blurry") if x)
            tmp_png = tmp_dir / f"{sid}.png"
            t0 = time.time()
            seed = 1000 + idx * 37
            runner.run({
                "model": model_id,
                "prompt": prompt,
                "negative_prompt": neg,
                "width": 512,
                "height": 320,
                "steps": args.steps,
                "seed": seed,
                "output_path": str(tmp_png),
            })
            encode_style_gif(tmp_png, out_gif, sid)
            kb = out_gif.stat().st_size / 1024.0
            print(f"[{idx:02d}/{len(styles)}] {sid:24s} -> {out_gif.name} ({kb:.1f} KB, {time.time() - t0:.1f}s)", flush=True)
            generated += 1

    print(f"Done: {generated} generated, {skipped} skipped in {time.time() - t_all:.1f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
