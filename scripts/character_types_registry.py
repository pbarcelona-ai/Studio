"""Data-driven registry of Visual Render Styles, Motion Cadence rules, and Character Archetypes.

Combines:
- All 10 detailed Image + Motion Cadence recipes from `character_types.txt`
- Studio's built-in handcrafted and cinematic presets
- 42 categorized Character Archetypes (Humans, Animals & Anthro, Toys & Objects, Sci-Fi, Fantasy, Biblical/Epic)
- Persistent user-defined custom styles & archetypes in `config/custom_character_types.json`
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
CUSTOM_REGISTRY_PATH = ROOT / "config" / "custom_character_types.json"
_SLUG_RE = re.compile(r"[^a-z0-9_]+")


def _clean_id(raw: str, prefix: str = "custom") -> str:
    s = _SLUG_RE.sub("_", str(raw or "").strip().lower()).strip("_")
    if len(s) < 2:
        s = f"{prefix}_{s or 'type'}"
    return s[:30]


# ---------------------------------------------------------------------------
# 30 Visual Render Styles (paired Image Style + Motion Cadence + Restyle Prompt)
# ---------------------------------------------------------------------------
BUILTIN_STYLES: list[dict[str, str]] = [
    # --- Stop-Motion & Tactile ---
    {
        "id": "claymation",
        "name": "Claymation",
        "icon": "🧸",
        "category": "Stop-Motion & Tactile",
        "summary": "Hand-sculpted plasticine clay figures with subtle fingerprint ridges and miniature tabletop sets.",
        "positives": "stop-motion miniature film still photographed on a physical tabletop stage, hand-sculpted plasticine clay, matte-waxy clay skin with subtle sculptor fingerprint ridges and pressed seam lines, 55mm macro cinema lens, warm 4000K tabletop studio light, grounded contact shadows",
        "negatives": "skin smoothing, glossy CGI 3D render, smooth vinyl shine, photorealistic human pores, real hair strands, overall blur, morphing, melting",
        "motion_cadence": "stepped 12-fps stop-motion cadence ('on twos') with zero motion blur, rigid sculpted clay volumes, tiny crisp clay micro-movement, firm grounded foot contact with zero sliding or melting",
        "restyle_prompt": "Turn this image into Claymation stop-motion miniature style: hand-sculpted plasticine clay with matte-waxy surface, tiny sculptor fingerprint ridges, pressed seams, and miniature tabletop studio lighting",
    },
    {
        "id": "toy_bricks",
        "name": "Toy Bricks (Minifigure)",
        "icon": "🧱",
        "category": "Stop-Motion & Tactile",
        "summary": "Glossy interlocking ABS plastic bricks, studded plates, and articulated plastic minifigure.",
        "positives": "macro toy-brick miniature construction, glossy interlocking ABS plastic bricks, studded baseplates, articulated plastic minifigure with molded hairpiece, printed expressive face, C-shaped hands, blocky hinged legs, bright daylight specular highlights, shallow macro depth of field",
        "negatives": "clay texture, rubbery limb bending, soft cloth weave, photorealistic human skin, melting, morphing, logos, text",
        "motion_cadence": "smooth 24-fps toy animation with crisp mechanical minifigure hinge articulation, rigid blocky legs pivoting cleanly from hip hinges with zero rubbery bending, firm foot lock onto raised plastic studs",
        "restyle_prompt": "Turn this image into Toy Bricks miniature construction, rebuilding the character and environment from glossy interlocking ABS plastic bricks, studded plates, and an articulated plastic minifigure with molded hairpiece, printed face, C-shaped hands, and blocky hinged legs",
    },
    {
        "id": "felt",
        "name": "Stop-Motion Felt",
        "icon": "🧵",
        "category": "Stop-Motion & Tactile",
        "summary": "Needle-felted wool figures with fuzzy fibers, hand-stitched seams, and cozy miniature sets.",
        "positives": "stop-motion felt and needle-felted wool miniature film still, soft fuzzy wool fibers, visible hand-stitched seams, tiny button or bead eyes, handmade fabric wardrobe, warm practical tabletop studio lighting, shallow macro depth of field",
        "negatives": "glossy CGI, plastic shine, photorealistic human skin, harsh digital sharpness, smooth airbrushed render",
        "motion_cadence": "stepped 12-fps tactile stop-motion cadence ('on twos'), gentle fuzzy wool fiber stability without noisy boiling, firm grounded footsteps, zero motion blur",
        "restyle_prompt": "Turn this image into Stop-Motion Felt style, crafted from soft needle-felted wool with delicate fuzzy fiber texture, stitched cloth seams, and warm miniature tabletop lighting",
    },
    {
        "id": "plush_doll",
        "name": "Plush & Rag Doll",
        "icon": "🪡",
        "category": "Stop-Motion & Tactile",
        "summary": "Soft stitched cloth dolls with yarn hair, embroidered faces, and cozy storybook miniature sets.",
        "positives": "handcrafted stuffed plush and rag-doll studio photography, soft cotton and fleece fabric textures, visible embroidered stitching, yarn hair strands, button eyes, gentle stuffing creases, soft warm studio lighting",
        "negatives": "hard plastic, metallic shine, realistic human skin, sharp CGI edges, glossy render",
        "motion_cadence": "gentle 12-to-24 fps tactile puppet motion with soft stuffed-cloth weight, floppy secondary follow-through on yarn hair and limbs, grounded contact shadows",
        "restyle_prompt": "Turn this image into a handcrafted Plush Rag Doll style with soft stitched cloth fabric, yarn hair, embroidered features, and cozy warm miniature lighting",
    },
    {
        "id": "puppet_muppet",
        "name": "Muppet / Studio Puppet",
        "icon": "🎭",
        "category": "Stop-Motion & Tactile",
        "summary": "Practical foam-and-fleece theatrical hand puppets filmed on physical stage sets.",
        "positives": "practical theatrical television puppet film still, Antron fleece skin, fluffy faux-fur and feather hair, hinged expressive mouth, round glossy pupil eyes, real tailored miniature costumes, warm 35mm practical studio stage lighting",
        "negatives": "CGI animation, flat 2D illustration, photorealistic human anatomy, plastic action figure",
        "motion_cadence": "lively 24-fps practical puppetry performance with bouncy energetic head nods, expressive mouth articulation, natural stage-light motion blur, physical fleece texture stability",
        "restyle_prompt": "Turn this image into a practical Studio Puppet style with Antron fleece texture, expressive round puppet eyes, tailored miniature clothing, and real theatrical stage lighting",
    },
    {
        "id": "papercraft",
        "name": "Cut-Paper Diorama",
        "icon": "✂️",
        "category": "Stop-Motion & Tactile",
        "summary": "Layered cardstock cut-outs, folded origami edges, and real shadow-box depth lighting.",
        "positives": "handcrafted layered cut-paper diorama photography, thick textured matte cardstock silhouettes, clean scissor-cut edges, subtle paper-layer drop shadows, folded origami details, warm backlit shadow-box lighting, macro lens",
        "negatives": "smooth 3D CGI, glossy plastic, photorealistic skin, blurry gradients, digital airbrushing",
        "motion_cadence": "crisp stepped 12-fps cut-paper stop-motion animation, flat cardstock planes articulating cleanly at paper-fastener joints, multi-layer paper parallax",
        "restyle_prompt": "Turn this image into a handcrafted Cut-Paper Diorama built from layered textured matte cardstock cutouts with real paper-edge shadows and warm shadow-box lighting",
    },
    {
        "id": "glazed_ceramic",
        "name": "Glazed Ceramic Miniature",
        "icon": "🏺",
        "category": "Stop-Motion & Tactile",
        "summary": "Hand-painted porcelain and kiln-glazed ceramic figurines with crackle-glaze highlights.",
        "positives": "hand-painted glazed ceramic miniature figurine photography, glossy crackle-glazed porcelain surfaces, subtle hand-brushed underglaze pigments, handmade kiln imperfections, warm specular highlights, shallow macro depth of field",
        "negatives": "matte plastic, rough 2D sketch, photorealistic human skin, flat cel shading",
        "motion_cadence": "delicate stepped 12-fps porcelain stop-motion cadence with crisp specular glaze highlights staying locked to rigid ceramic surfaces",
        "restyle_prompt": "Turn this image into a hand-painted Glazed Ceramic Miniature figurine with glossy crackle-glazed porcelain surfaces, artisan brushwork, and macro studio lighting",
    },
    {
        "id": "tin_toy",
        "name": "Vintage Tin-Toy Macro",
        "icon": "🤖",
        "category": "Stop-Motion & Tactile",
        "summary": "1950s wind-up lithographed tin toys with stamped metal seams, rivets, and brass keys.",
        "positives": "vintage wind-up tin-toy macro photography, lithographed chipped enamel paint on stamped sheet metal panels, tiny steel rivets, brass winding keys, articulated metal hinges, directional tabletop studio light, shallow macro depth of field",
        "negatives": "soft organic skin, fabric weave, flat 2D drawing, smooth modern plastic",
        "motion_cadence": "charming stepped 12-to-24 fps wind-up mechanical toy motion with rhythmic ticking limb hinges and crisp metallic reflections",
        "restyle_prompt": "Turn this image into a Vintage Wind-Up Tin Toy crafted from stamped lithographed sheet metal panels with tiny rivets, enamel paint sheen, and mechanical hinges",
    },

    # --- 2D & Illustration ---
    {
        "id": "anime",
        "name": "Anime (Japanese 2D)",
        "icon": "🌸",
        "category": "2D & Illustration",
        "summary": "Japanese 2D theatrical anime with fine ink outlines, two-tone cel shading, and gouache skies.",
        "positives": "Japanese 2D theatrical animated film still, fine dark-brown ink outlines, crisp two-tone cel shading on character and props, expressive anime eyes, painterly gouache background brushwork, sunlit luminous atmosphere",
        "negatives": "3D CGI render, clay texture, photorealistic skin, blurry airbrush, western rubber-hose distortion",
        "motion_cadence": "hand-drawn limited character animation on twos (12 fps) paired with smooth 24-fps multi-plane painted background pan, zero 3D CGI blur, subtle hair and cloth breeze flutter on twos",
        "restyle_prompt": "Turn this image into Japanese 2D Anime film style with fine dark-brown ink outlines, crisp two-tone cel shading, expressive anime eyes, and painterly gouache background brushwork",
    },
    {
        "id": "cartoon_2d",
        "name": "Western 2D TV Cartoon",
        "icon": "📺",
        "category": "2D & Illustration",
        "summary": "Vibrant modern 2D TV cartoon with bold uniform black outlines and saturated flat cel fills.",
        "positives": "vibrant Western 2D TV cartoon animation still, bold uniform black ink outlines, simplified appealing rounded shapes, saturated flat cel shading, crisp oval cast shadows, playful energetic color palette",
        "negatives": "3D CGI shading, photorealistic textures, clay residue, painterly blur, muted muddy colors",
        "motion_cadence": "snappy digital ink-and-paint cel animation (12-to-24 fps), crisp uniform line weight, buoyant rhythmic bounce, zero motion blur, no rubbery distortion of solid props",
        "restyle_prompt": "Turn this image into a vibrant Western 2D TV Cartoon with bold uniform black outlines, simplified rounded shapes, and saturated flat cel shading",
    },
    {
        "id": "flat_vector",
        "name": "Flat Vector Graphic",
        "icon": "📐",
        "category": "2D & Illustration",
        "summary": "Razor-sharp lineless 2D geometric shapes, smooth solid color fills, and modern studio polish.",
        "positives": "flat vector 2D illustration, razor-sharp lineless geometric shapes, smooth pure solid color fills, minimal flat shadow planes, clean mid-modern graphic palette, crisp orthographic clarity, zero outlines and zero gradients",
        "negatives": "black outlines, gradients, film grain, 3D shading, clay texture, photorealism, sketchy lines",
        "motion_cadence": "crisp smooth 24-fps vector puppet motion-graphics animation with clean geometric arcs, zero motion blur, pure flat solid color fills",
        "restyle_prompt": "Turn this image into a lineless Flat Vector 2D illustration built from razor-sharp geometric shapes, smooth pure solid color fills, minimal flat shadow planes, and zero outlines or gradients",
    },
    {
        "id": "comic_ink",
        "name": "Comic Book (Halftone Ink)",
        "icon": "💥",
        "category": "2D & Illustration",
        "summary": "Bold vintage American comic print with India-ink outlines, spot-blacks, and Ben-Day halftones.",
        "positives": "bold vintage American comic-book pop-art print, variable-weight black India-ink outlines, solid spot-blacks, crisp ink crosshatching, authentic Ben-Day halftone dot shading, dynamic graphic-novel framing, print paper grain",
        "negatives": "3D CGI smoothing, clay texture, speech bubbles, sound-effect lettering, text, blurry airbrushing",
        "motion_cadence": "punchy hand-inked animation on twos (12 fps) with snappy graphic-novel cadence, stable Ben-Day halftone dots locked to surfaces without flicker, zero motion blur",
        "restyle_prompt": "Turn this image into Vintage Comic Book style with variable black India-ink outlines, solid spot-blacks, crisp crosshatching, and Ben-Day halftone dot shading",
    },
    {
        "id": "watercolour",
        "name": "Storybook Watercolor",
        "icon": "🎨",
        "category": "2D & Illustration",
        "summary": "Hand-painted sepia ink & colored-pencil outlines with translucent watercolor washes on cold-press paper.",
        "positives": "hand-painted storybook illustration, delicate warm-sepia ink and colored-pencil outlines, translucent watercolor washes, soft organic pigment bleeds, visible cold-press cotton paper grain, cozy golden-hour picture-book warmth",
        "negatives": "3D CGI render, harsh neon colors, thick digital vector lines, clay texture, glossy plastic",
        "motion_cadence": "gentle picture-book animation on twos (12 fps) with soft organic hand-drawn movement, calm cold-press paper texture without noisy boiling flicker, zero digital motion blur",
        "restyle_prompt": "Turn this image into a hand-painted Storybook Watercolor illustration with delicate warm-sepia ink and colored-pencil outlines, translucent watercolor washes, and visible cold-press paper grain",
    },
    {
        "id": "midcentury_2d",
        "name": "Mid-Century 2D Gouache",
        "icon": "🖌️",
        "category": "2D & Illustration",
        "summary": "1950s UPA-inspired geometric 2D animation with dry-gouache textures and earthy palette.",
        "positives": "hand-painted mid-century 2D cartoon illustration, 1950s UPA geometric styling, dry-gouache brush textures, stylized elongated proportions, muted earthy retro palette, subtle vintage animation cel paper grain",
        "negatives": "photorealism, modern 3D CGI, glossy gradients, neon cyberpunk",
        "motion_cadence": "stylized 12-fps limited animation ('on twos') with crisp graphic poses, subtle dry-gouache texture stability, snappy retro timing",
        "restyle_prompt": "Turn this image into a 1950s Mid-Century 2D Gouache animation cel with bold geometric shapes, dry-gouache brushwork, and a warm retro earthy palette",
    },
    {
        "id": "travel_poster",
        "name": "Vintage Travel Poster",
        "icon": "🚂",
        "category": "2D & Illustration",
        "summary": "1930s Art Deco lithograph with flat bold shapes, limited printed palette, and screen grain.",
        "positives": "vintage 1930s Art Deco travel poster lithograph, bold sweeping silhouettes, flat color-blocked planes, limited retro ink palette, subtle screen-print registration grain, sunlit sky gradients",
        "negatives": "photorealistic, 3D CGI, glossy render, anime, cluttered micro-detail, garbled lettering, text",
        "motion_cadence": "stately 12-to-24 fps graphic multi-plane parallax motion preserving flat lithograph planes and vintage screen-print grain",
        "restyle_prompt": "Turn this image into a 1930s Vintage Art Deco Travel Poster lithograph with bold flat silhouettes, limited printed ink palette, and screen-print grain",
    },
    {
        "id": "ukiyo_e",
        "name": "Ukiyo-e Woodblock Print",
        "icon": "🌊",
        "category": "2D & Illustration",
        "summary": "Japanese woodblock print with carved ink lines, flat indigo/vermilion pigments, and washi paper.",
        "positives": "traditional Japanese Ukiyo-e woodblock print, fine carved dark-sumi ink outlines, flat faded indigo, vermilion, and ochre mineral pigments, aged washi-paper fiber grain, subtle woodblock print registration texture",
        "negatives": "3D CGI, glossy modern gradients, photorealistic lighting, neon colors",
        "motion_cadence": "graceful 12-fps woodblock-print motion on twos with flowing calligraphic drapery and layered flat-plane parallax on stable washi paper",
        "restyle_prompt": "Turn this image into a traditional Japanese Ukiyo-e Woodblock Print with carved dark ink outlines, flat indigo and vermilion pigments, and aged washi-paper grain",
    },
    {
        "id": "painted_sign",
        "name": "Hand-Painted Vintage Sign",
        "icon": "🪧",
        "category": "2D & Illustration",
        "summary": "Americana hand-painted enamel sign illustration with directional brushstrokes and weathered pigment.",
        "positives": "vintage hand-painted 2D enamel sign illustration, bold dark outlines, visible directional bristle brushstrokes, weathered flat matte pigments, warm painted highlights on subtle aged board texture, no 3D render",
        "negatives": "3D CGI, photorealistic photography, smooth airbrushed digital gradients, text, logos",
        "motion_cadence": "lively 12-fps hand-painted frame animation preserving visible brushwork and weathered enamel colors",
        "restyle_prompt": "Turn this image into a Hand-Painted Vintage Enamel Sign illustration with bold outlines, visible directional brushstrokes, and weathered flat pigments",
    },
    {
        "id": "scratchboard",
        "name": "Scratchboard Engraving",
        "icon": "🖋️",
        "category": "2D & Illustration",
        "summary": "High-contrast carved white-and-ochre etching lines over a deep midnight-black ground.",
        "positives": "handcrafted scratchboard engraving illustration, deep midnight-black ground, fine ivory and muted-ochre scratched lines, delicate cross-hatching, bold preserved dark negative space, dramatic chiaroscuro",
        "negatives": "smooth gradients, soft pastel watercolor, glossy 3D CGI, photorealistic color photo",
        "motion_cadence": "atmospheric 12-fps engraved-line animation on twos keeping fine ivory hatching crisp against deep velvet blacks",
        "restyle_prompt": "Turn this image into a Scratchboard Engraving illustration carved with fine ivory and muted-ochre crosshatched lines on a deep midnight-black ground",
    },
    {
        "id": "charcoal_sketch",
        "name": "Charcoal & Graphite Sketch",
        "icon": "✏️",
        "category": "2D & Illustration",
        "summary": "Expressive hand-drawn charcoal and pencil animation on textured warm rag sketchbook paper.",
        "positives": "expressive hand-drawn charcoal and graphite pencil illustration on textured warm ivory sketchbook paper, lively gestural contour lines, smudged tonal shading, soft chalk highlights, visible tooth of drawing paper",
        "negatives": "3D CGI, glossy colors, vector flat fills, photorealistic color",
        "motion_cadence": "organic 12-fps hand-drawn pencil-test animation on twos with gentle expressive line boil and soft smudged shadows",
        "restyle_prompt": "Turn this image into an expressive Charcoal and Graphite Sketch on textured warm sketchbook paper with gestural contour lines and smudged tonal shading",
    },
    {
        "id": "stained_glass",
        "name": "Illuminated Stained Glass",
        "icon": "🪟",
        "category": "2D & Illustration",
        "summary": "Luminous jewel-toned cathedral glass panes framed in dark lead cames with backlit glow.",
        "positives": "illuminated stained-glass artwork, rich jewel-toned translucent glass shards in cobalt, ruby, amber, and emerald, bold dark lead came outlines, radiant backlit sunlight glow, subtle textured antique glass bubbles",
        "negatives": "matte plastic, photorealistic skin, soft blurry smudge, low contrast",
        "motion_cadence": "luminous 12-to-24 fps animated stained-glass tableau with shimmering backlit glass caustics and crisp dark lead outlines",
        "restyle_prompt": "Turn this image into Illuminated Stained Glass made of glowing jewel-toned translucent glass panes framed in bold dark lead outlines",
    },

    # --- 3D & Digital ---
    {
        "id": "pixar_3d",
        "name": "3D Animation (Pixar-Grade)",
        "icon": "✨",
        "category": "3D & Digital",
        "summary": "Polished theatrical 3D CGI with subsurface skin, groomed hair, woven fabric shaders, and warm GI.",
        "positives": "polished theatrical 3D CGI animated film still, stylized appealing 3D forms, subsurface-scattered skin, groomed hair strands, woven fabric shaders, warm global illumination, rich saturated color, soft cinematic bokeh",
        "negatives": "photorealistic human skin, clay texture, flat 2D drawing, uncanny valley, harsh flat lighting",
        "motion_cadence": "silky-smooth 24-fps feature-animation motion with natural weight transfer, subtle cinematic motion blur, overlapping follow-through, and rich PBR lighting",
        "restyle_prompt": "Complete 3D Pixar animated movie transformation (like The Incredibles and Toy Story): convert into exaggerated stylized 3D CGI cartoon proportions, smooth sculpted 3D animated surfaces and features, stylized groomed 3D hair, chunky stylized clothing and materials, warm global illumination, and rich saturated Pixar colors — NOT a real-world photograph, NOT photorealistic human skin",
    },
    {
        "id": "pixar_disney",
        "name": "Pixar-Disney Storybook 3D",
        "icon": "🏰",
        "category": "3D & Digital",
        "summary": "Theatrical 3D animation blended with hand-painted fairytale textures and luminous storybook light.",
        "positives": "3D animated fairytale feature film still with painterly hand-brushed surface textures, expressive luminous eyes, graceful storybook silhouette, golden fairytale rim lighting, rich lush color harmony",
        "negatives": "gritty realism, harsh cyberpunk neon, clay texture, flat unshaded vector",
        "motion_cadence": "fluid 24-fps feature animation with graceful theatrical acting, soft magical lighting continuity, and painterly surface stability",
        "restyle_prompt": "Complete Pixar-Disney Storybook 3D animated feature film transformation: convert into appealing stylized 3D CGI cartoon proportions, smooth sculpted 3D animated forms, hand-painted fairytale textures, and luminous golden storybook lighting — NOT a real-world photograph, NOT photorealistic",
    },
    {
        "id": "painted_3d",
        "name": "Painted 3D (Spider-Verse / Arcane)",
        "icon": "⚡",
        "category": "3D & Digital",
        "summary": "Stylized 3D geometry surfaced with hand-painted brushstrokes, graphic ink accents, and rim light.",
        "positives": "stylized painted 3D feature animation still, sculpted 3D characters covered in visible hand-painted gouache and oil brushstrokes, crisp selective ink contour lines, dramatic complementary rim lighting, rich graphic shadows",
        "negatives": "smooth plastic CGI, photorealistic photography, clay texture, flat featureless shading",
        "motion_cadence": "dynamic stepped 12-fps character animation ('on twos') against smooth 24-fps camera movement, preserving crisp painted brushstroke planes on every surface",
        "restyle_prompt": "Turn this image into Stylized Painted 3D (Arcane / Spider-Verse look) combining 3D sculpted forms with visible hand-painted brushstrokes, crisp graphic ink contours, and dramatic rim lighting",
    },
    {
        "id": "retro_low_poly",
        "name": "Retro Low-Poly 3D",
        "icon": "🔷",
        "category": "3D & Digital",
        "summary": "Crisp lineless flat-shaded triangular and quad polygon facets with hard geometric edges.",
        "positives": "retro low-poly 3D art, crisp lineless flat-shaded triangular and quad polygon facets, hard geometric edges, angular blocky volumes, clean directional per-facet lighting, zero smooth subdivision",
        "negatives": "smooth Phong shading, subdivision smoothing, clay texture, photorealistic skin, blurry edges",
        "motion_cadence": "clean 24-fps rigid skeletal game-engine motion with crisp per-polygon facet lighting, angular limb articulation without soft rubbery deformation, zero motion blur",
        "restyle_prompt": "Turn this image into Retro Low-Poly 3D, rebuilding every surface from crisp lineless flat-shaded triangular and quad polygon facets with hard geometric edges and zero smooth subdivision",
    },
    {
        "id": "isometric_3d",
        "name": "Isometric Miniature 3D",
        "icon": "🧊",
        "category": "3D & Digital",
        "summary": "Clean tilt-shift isometric 3D diorama with soft matte clay-like PBR shaders and crisp shadows.",
        "positives": "stylized isometric 3D diorama render, adorable clean rounded 3D geometry, soft matte vinyl-and-wood PBR shaders, crisp studio softbox lighting, subtle tilt-shift miniature depth, cheerful cohesive color palette",
        "negatives": "gritty realism, harsh noise, flat 2D linework, chaotic clutter",
        "motion_cadence": "clean 24-fps miniature diorama motion with crisp tilt-shift depth and steady smooth camera gliding",
        "restyle_prompt": "Turn this image into a stylized Isometric 3D Miniature Diorama with clean rounded 3D geometry, soft matte PBR shaders, and studio softbox lighting",
    },
    {
        "id": "cyberpunk_3d",
        "name": "Cyberpunk Neon 3D",
        "icon": "🌆",
        "category": "3D & Digital",
        "summary": "Nocturnal 3D neon cinema with glowing magenta/cyan rim light, rain reflections, and volumetric fog.",
        "positives": "cyberpunk neon 3D cinematic render, moody night atmosphere, glowing magenta and electric-cyan neon rim lights, rain-slick reflective surfaces, volumetric fog, holographic accents, high-contrast cinema lighting",
        "negatives": "bright pastel daylight, pastoral watercolor, claymation, washed-out low contrast",
        "motion_cadence": "sleek 24-fps cinematic 3D camera motion with steady neon reflections, subtle drifting volumetric haze, and crisp silhouette rim light",
        "restyle_prompt": "Turn this image into Cyberpunk Neon 3D with moody night lighting, glowing magenta and cyan neon rim lights, reflective wet surfaces, and volumetric fog",
    },

    # --- Game & Retro ---
    {
        "id": "pixel_art_16bit",
        "name": "16-Bit Pixel Art",
        "icon": "👾",
        "category": "Game & Retro",
        "summary": "Crisp 16-bit retro game scene on an aliased square pixel grid with 1px dark sprite outlines.",
        "positives": "crisp 16-bit retro pixel-art game scene on a clean aliased square pixel grid, dark one-pixel sprite outlines, stepped pixel-cluster shading, classic subtle dithering, vivid arcade palette, razor-sharp pixels",
        "negatives": "anti-aliased blur, smooth 3D shading, clay texture, sub-pixel warping, photorealism, HUD UI text",
        "motion_cadence": "crisp stepped 8-to-10 fps pixel sprite animation with strict pixel-grid alignment, zero motion blur or anti-aliasing smear, multi-layer arcade parallax scrolling",
        "restyle_prompt": "Turn this image into 16-Bit Pixel Art on a crisp aliased square pixel grid with dark one-pixel sprite outlines, stepped pixel-cluster shading, and classic dithering",
    },
    {
        "id": "rubber_hose",
        "name": "1930s Rubber-Hose Cartoon",
        "icon": "🎞️",
        "category": "Game & Retro",
        "summary": "Classic 1930s vintage ink-and-paint cartoon with pie-cut eyes, white gloves, and film grain.",
        "positives": "classic 1930s vintage rubber-hose cartoon cel animation, bold hand-inked contours, pie-cut expressive eyes, warm sepia-cream or muted vintage Technicolor palette, painted watercolor backdrop, authentic 35mm vintage nitrate film grain",
        "negatives": "modern 3D CGI, anime, photorealistic skin, sharp vector sterility",
        "motion_cadence": "bouncy 12-fps classic golden-age cartoon cadence with lively rhythmic squash-and-stretch and vintage hand-inked cel warmth",
        "restyle_prompt": "Turn this image into a classic 1930s Rubber-Hose Vintage Cartoon with bold hand-inked outlines, pie-cut eyes, vintage muted Technicolor fills, and subtle film grain",
    },

    # --- Live-Action & Film ---
    {
        "id": "live_action",
        "name": "Realistic Live Action",
        "icon": "🎬",
        "category": "Live-Action & Film",
        "summary": "Cinematic 35mm live-action film still with real skin texture, practical lighting, and natural grain.",
        "positives": "cinematic live-action film still photographed on 35mm anamorphic cinema camera, natural unretouched skin and woven fabric textures, motivated practical lighting, organic film grain, shallow cinematic depth of field",
        "negatives": "cartoon, animated, 3D CGI render, claymation, anime, plastic skin, doll-like, airbrushed",
        "motion_cadence": "natural 24-fps cinema camera motion with authentic optical motion blur, realistic human weight and physics, steady practical lighting",
        "restyle_prompt": "Turn this image into a Realistic Live-Action 35mm cinema film still with authentic real-world textures, practical cinematic lighting, and natural depth of field",
    },
    {
        "id": "noir",
        "name": "Film Noir (B&W)",
        "icon": "🕵️",
        "category": "Live-Action & Film",
        "summary": "High-contrast 1940s black-and-white silver-gelatin cinema with hard Venetian-blind shadows.",
        "positives": "classic 1940s film noir black-and-white 35mm cinema still, dramatic chiaroscuro hard shadows, Venetian-blind light shafts, silver-gelatin film grain, atmospheric mist, crisp rim lighting",
        "negatives": "color, pastel palette, cartoon, flat even lighting, modern glossy CGI",
        "motion_cadence": "moody 24-fps classic cinema camera motion with dramatic light-and-shadow contrast, drifting atmospheric haze, and authentic 35mm grain",
        "restyle_prompt": "Turn this image into a 1940s Film Noir black-and-white 35mm film still with dramatic chiaroscuro shadows, crisp silver-gelatin contrast, and classic grain",
    },
    {
        "id": "vintage_16mm",
        "name": "Vintage 1970s 16mm Film",
        "icon": "📽️",
        "category": "Live-Action & Film",
        "summary": "Warm nostalgic 1970s Kodak 16mm film photography with rich grain, halation, and golden warmth.",
        "positives": "nostalgic 1970s 16mm Kodak film still, rich organic film grain, subtle warm amber highlight halation, natural vintage color rendition, soft vintage prime-lens character, authentic practical daylight",
        "negatives": "modern sterile digital CGI, neon cyberpunk, flat 2D vector, plastic skin",
        "motion_cadence": "organic 24-fps handheld or tripod 16mm film motion with natural vintage film grain and warm highlight halation",
        "restyle_prompt": "Turn this image into a Vintage 1970s 16mm Film photograph with rich organic film grain, warm golden halation, and nostalgic Kodachrome colors",
    },

    # --- 2D Meets Realism & Mixed-Media Hybrid (from 2D_Realism_Tutorial.pdf) ---
    {
        "id": "vintage_1940s_2d",
        "name": "Vintage 1940s Hand-Drawn 2D",
        "icon": "🐻",
        "category": "Hybrid & 2D Realism",
        "summary": "Classic 1940s hand-drawn cel animation with clean ink line art, flat muted colours, and soft painted shading.",
        "positives": "vintage 1940s hand-drawn 2D cartoon style, clean dark ink line art, flat muted storybook colours, soft hand-painted cel shading, warm classic theatrical animation proportions, expressive friendly character design",
        "negatives": "3D CGI render, photorealistic fur or skin, glossy plastic, harsh neon digital gradients, anime speedlines, blurry airbrush",
        "motion_cadence": "classic hand-drawn 2D animation strictly on twos (12 fps) with warm fluid follow-through, expressive eye-lines, zero 3D motion blur, and grounded contact shadows",
        "restyle_prompt": "Turn this image into vintage 1940s hand-drawn 2D cartoon style with clean ink line art, flat muted colours, and soft painted cel shading",
    },
    {
        "id": "hybrid_2d_live_action",
        "name": "2D Meets Live-Action Hybrid",
        "icon": "🎭",
        "category": "Hybrid & 2D Realism",
        "summary": "Who Framed Roger Rabbit hybrid: 35mm live-action sets & real actors sharing the frame with vintage hand-drawn 2D cartoons.",
        "positives": "mixed-media live-action and vintage 1940s 2D cartoon hybrid film still, real-world 35mm cinema photography with warm practical lighting and real human actor alongside cleanly inked flat-shaded hand-drawn 2D cartoon characters integrated seamlessly with matched contact shadows and bounce light",
        "negatives": "all-3D CGI render, turning the real person into a cartoon, turning the 2D cartoon photorealistic, floating characters with no contact shadow, mismatched lighting",
        "motion_cadence": "24-fps live-action cinema camera and real actor performance paired with vintage hand-drawn 2D cartoon characters animated strictly on twos (12 fps) reacting naturally with eye-line and grounded contact shadows",
        "restyle_prompt": "Composite vintage 1940s hand-drawn 2D cartoon characters (clean ink outlines, flat muted colours, soft painted shading) seamlessly into this real 35mm live-action photograph while keeping the real actor, camera framing, and practical lighting 100% locked",
    },

    # --- Additional Animation & Graphic Styles (from more_characters.txt & studio repertoire) ---
    {
        "id": "chalkboard_doodle",
        "name": "Chalkboard Doodle",
        "icon": "🖍️",
        "category": "Graphic & Experimental",
        "summary": "Green slate chalkboard with wooden frame, rough dusty chalk strokes, red accent chalk, and hand-lettered notes.",
        "positives": "hand-drawn chalkboard illustration on a dark green slate blackboard with wooden frame, rough textured white and pastel chalk strokes, crimson red accent chalk highlights, dusty chalk smudges, playful hand-drawn callout arrows",
        "negatives": "3D CGI render, glossy plastic, photorealistic human skin, smooth digital gradients, neon glow",
        "motion_cadence": "charming stepped 12-fps hand-drawn chalk animation on twos with gentle chalk-line boil and lively hand-drawn motion dashes",
        "restyle_prompt": "Turn this image into a Chalkboard Doodle drawn in rough dusty white and red chalk strokes on a textured green slate classroom chalkboard",
    },
    {
        "id": "golden_neon_sketch",
        "name": "Golden Neon Glow Sketch",
        "icon": "✨",
        "category": "Graphic & Experimental",
        "summary": "Pitch-black void illuminated by glowing dashed gold and red-gold sketch lines, spotlight beams, and floor rings.",
        "positives": "glowing golden neon line-sketch artwork on a pitch-black background, luminous dashed and dotted golden contour lines, warm red-gold glow accents, soft volumetric bloom, glowing spotlight beam and luminous concentric floor rings",
        "negatives": "daylight, white background, solid photorealistic skin, muted matte clay, flat paper",
        "motion_cadence": "sleek 24-fps luminous vector-glow motion with pulsing golden dashed strokes, drifting light particles, and expanding floor ripple rings",
        "restyle_prompt": "Turn this image into a Golden Neon Glow Sketch drawn in luminous dashed gold and red-gold glowing lines against a pitch-black background with soft bloom and spotlight glow",
    },
    {
        "id": "line_diagram",
        "name": "Minimal Line Diagram",
        "icon": "📏",
        "category": "Graphic & Experimental",
        "summary": "Stark black canvas with razor-thin white hairlines, dot-jointed figures, and rotating geometric construction circles.",
        "positives": "minimal technical line-art diagram on a pure black background, razor-thin crisp white hairlines, clean articulated figure with tiny dot joints and delicate construction rings, subtle drafting geometry circles, ultra-clean architectural minimalism",
        "negatives": "color fills, heavy shading, photorealism, 3D CGI, thick cartoon outlines, messy sketch",
        "motion_cadence": "precise 24-fps kinetic drafting-diagram motion with smooth mechanical joint articulation, rotating construction circles, and clean ripple ticks",
        "restyle_prompt": "Turn this image into a Minimal Line Diagram on a pure black background using razor-thin white hairlines, articulated dot joints, and delicate geometric construction circles",
    },
    {
        "id": "soft_3d_explainer",
        "name": "Soft 3D Explainer",
        "icon": "🫧",
        "category": "3D & Digital",
        "summary": "Smooth glossy toy-like plastic 3D explainer animation with shallow DoF blurred backdrop and warm dusk light.",
        "positives": "smooth 3D explainer animation still, glossy rounded toy-like vinyl and matte-plastic materials, warm dusk studio lighting, shallow depth-of-field softly blurred background layer, crisp sharp foreground character with soft grounded contact shadow",
        "negatives": "gritty photorealistic skin, harsh horror lighting, rough 2D sketch, pixel art, noisy grain",
        "motion_cadence": "buttery-smooth 24-fps playful 3D explainer motion with clean squash-and-stretch, crisp foreground focus, and gentle parallax over soft bokeh background",
        "restyle_prompt": "Turn this image into a Soft 3D Explainer render with glossy rounded toy-like plastic materials, warm dusk lighting, soft contact shadows, and shallow depth-of-field background blur",
    },
    {
        "id": "cinematic_moody_3d",
        "name": "Cinematic Moody Night 3D",
        "icon": "🌧️",
        "category": "3D & Digital",
        "summary": "Atmospheric ACES-tonemapped dark CGI night scene with layered fog, cyan rim light, and mirror-wet reflections.",
        "positives": "cinematic moody dark 3D CGI film still, ACES filmic tone mapping, layered atmospheric volumetric fog, crisp cyan rim lighting on subject, warm glowing red lanterns and lit windows, mirror-wet reflective pavement with rain ripple rings",
        "negatives": "bright flat daylight, pastel cartoon, chalk drawing, low-poly blocky mesh, flat 2D vector",
        "motion_cadence": "cinematic 24-fps moody CGI camera tracking with drifting layered fog, glistening rain ripples on wet pavement, and subtle optical bloom",
        "restyle_prompt": "Turn this image into a Cinematic Moody Night 3D CGI still with layered volumetric fog, cyan rim lighting, warm glowing lanterns, ACES tone mapping, and mirror-wet reflective ground",
    },
    {
        "id": "pixel_8bit_hud",
        "name": "8-Bit Arcade Quest",
        "icon": "🕹️",
        "category": "Retro & Game",
        "summary": "Chunky crisp 8-bit retro arcade sprite graphics with limited NES palette and nearest-neighbor pixel clarity.",
        "positives": "authentic 8-bit retro arcade video game screenshot, chunky crisp nearest-neighbor pixel art sprite, limited vibrant NES color palette, crisp pixel tile environment, nostalgic retro game charm, zero anti-aliasing",
        "negatives": "smooth HD vectors, 3D CGI, photorealistic textures, soft blur, painterly brushwork",
        "motion_cadence": "authentic stepped 8-to-12 fps retro sprite-sheet walk cycle with crisp pixel-grid stepping, zero sub-pixel blur, and sparkling pixel pickups",
        "restyle_prompt": "Turn this image into chunky 8-Bit Arcade Quest pixel art with crisp nearest-neighbor pixels, classic limited retro game palette, and sprite-sheet character styling",
    },
    {
        "id": "ghibli_2d",
        "name": "Ghibli Hand-Painted 2D",
        "icon": "🍃",
        "category": "2D & Illustration",
        "summary": "Lush hand-painted gouache & watercolor backgrounds paired with warm, expressive traditional cel characters.",
        "positives": "classic Japanese hand-painted theatrical 2D anime film still in warm pastoral storybook style, delicate soft ink outlines, luminous gouache painted skies and lush foliage, dappled sunlight, nostalgic handcrafted warmth",
        "negatives": "3D CGI, plastic shine, gritty cybernetic neon, harsh thick black comic ink, photorealistic pores",
        "motion_cadence": "fluid hand-drawn traditional 2D animation on twos (12 fps) with gentle wind-swept grass and clouds, expressive natural body language, and warm painterly light",
        "restyle_prompt": "Turn this image into lush Hand-Painted Japanese Storybook 2D Anime with delicate soft ink lines, warm cel shading, and rich gouache-painted backgrounds",
    },
    {
        "id": "spiderverse_3d",
        "name": "Halftone Graphic 3D (Spider-Verse)",
        "icon": "🕸️",
        "category": "3D & Digital",
        "summary": "Stylized 3D CGI fused with comic halftone dots, chromatic offset lines, painted brush strokes, and stepped framing.",
        "positives": "stylized graphic-novel 3D CGI animation still, expressive painted brush textures on 3D forms, Ben-Day halftone shadow dots, crisp hand-inked contour accents, subtle CMYK chromatic offset, vibrant high-contrast rim lighting",
        "negatives": "photorealistic live action, sterile smooth Pixar skin, flat monochrome sketch, blurry motion smears",
        "motion_cadence": "dynamic stepped 12-fps ('on twos') graphic-novel 3D character animation over smooth 24-fps camera movement with crisp comic impact frames",
        "restyle_prompt": "Turn this image into stylized Halftone Graphic 3D CGI blending painted 3D surfaces with Ben-Day halftone shadow dots, inked contour accents, and vibrant rim lighting",
    },
    {
        "id": "arcane_painterly_3d",
        "name": "Painterly Concept-Art 3D",
        "icon": "⚔️",
        "category": "3D & Digital",
        "summary": "Sculptural 3D forms hand-textured with bold oil-and-gouache brushwork, dramatic chiaroscuro, and rich color.",
        "positives": "hand-painted concept-art 3D animation still, sculptural stylized 3D character with visible bold oil and gouache brushwork baked directly into skin and cloth textures, dramatic theatrical rim lighting, rich painterly depth",
        "negatives": "smooth plastic toy sheen, photorealistic camera photo, flat 2D cartoon, pixel art, anime cel flatness",
        "motion_cadence": "cinematic 24-fps sculptural painterly 3D animation with weighty expressive acting, drifting atmospheric dust motes, and dramatic moving key light",
        "restyle_prompt": "Turn this image into Painterly Concept-Art 3D animation with sculptural 3D forms, visible bold hand-painted oil brushwork on every surface, and dramatic theatrical lighting",
    },
    {
        "id": "paper_cutout",
        "name": "Paper Cutout Collage",
        "icon": "✂️",
        "category": "Stop-Motion & Tactile",
        "summary": "Layered hand-cut construction paper shapes with crisp scissor edges, drop shadows, and craft collage depth.",
        "positives": "handcrafted layered construction-paper cutout collage animation still, crisp scissor-cut matte cardstock shapes, tactile paper fiber texture, multi-plane depth with soft physical drop shadows between layers, warm tabletop lighting",
        "negatives": "smooth 3D CGI, glossy plastic, photorealistic skin, blurry gradients, neon glow",
        "motion_cadence": "playful stepped 12-fps paper-cutout stop-motion cadence with crisp hinged cardstock limbs and stable physical paper drop shadows",
        "restyle_prompt": "Turn this image into a handcrafted Paper Cutout Collage built from layered matte construction-paper shapes with crisp scissor edges and physical multi-plane drop shadows",
    },
    {
        "id": "fabric_collage",
        "name": "Fabric-Collage Appliqué",
        "icon": "🧶",
        "category": "Stop-Motion & Tactile",
        "summary": "Handmade 2D textile collage built from layered felt, printed cotton, linen, blanket stitches, and yarn.",
        "positives": "handmade textile-collage appliqué artwork viewed straight on, every element assembled from layered felt, printed cotton, linen, embroidery thread, and yarn, visible fabric weave, blanket stitches, slightly frayed cloth edges, soft drop shadows between appliqué layers, tactile children's-book warmth",
        "negatives": "photorealistic skin, glossy plastic surfaces, smooth 3D CGI, digital airbrushing, blurry gradients, melting stitches, text, watermark",
        "motion_cadence": "gentle stepped 12-fps textile-collage cutout motion preserving visible blanket stitches, woven fabric textures, frayed edges, and crisp shadows between appliqué layers with zero stitch flicker",
        "restyle_prompt": "Turn this image into a handmade Fabric-Collage Appliqué artwork built from layered felt, printed cotton, linen, embroidery thread, and yarn with visible blanket stitches, fabric weave, slightly frayed edges, and soft appliqué layer shadows",
    },
    {
        "id": "shadow_puppet",
        "name": "Shadow Puppet Silhouette",
        "icon": "🏮",
        "category": "Graphic & Experimental",
        "summary": "Lotte Reiniger inspired articulated dark silhouettes backlit by glowing amber parchment and atmospheric mist.",
        "positives": "theatrical shadow-puppet silhouette animation still, intricate articulated dark obsidian cut-out silhouettes backlit through glowing warm amber and twilight-blue parchment screen, dramatic ornamental filigree edges, soft diffused lantern halo",
        "negatives": "front-lit realistic faces, 3D CGI plastic, bright flat cartoon colors, white background",
        "motion_cadence": "graceful 12-to-24 fps backlit shadow-puppet articulation with delicate hinged limbs and softly flickering lantern backlight",
        "restyle_prompt": "Turn this image into a theatrical Shadow Puppet Silhouette composition with intricate dark cut-out silhouettes backlit by glowing amber and indigo parchment",
    },
    {
        "id": "risograph_zine",
        "name": "Risograph Indie Zine",
        "icon": "🖨️",
        "category": "Graphic & Experimental",
        "summary": "Tactile 3-ink risograph print with fluorescent coral, teal, and indigo soy-ink grain and slight misregistration.",
        "positives": "indie risograph print illustration on warm speckled cream paper, limited 3-color fluorescent coral, teal, and deep indigo soy-ink halftone layers, charming slight print misregistration, grainy stippled ink texture",
        "negatives": "photorealistic photo, glossy 3D CGI, smooth digital airbrush, full rainbow gradients",
        "motion_cadence": "tactile 12-fps risograph zine animation on twos with organic soy-ink grain and charming subtle print registration shift",
        "restyle_prompt": "Turn this image into a 3-color Risograph Indie Zine print with textured coral, teal, and indigo soy-ink halftone layers on warm speckled paper",
    },
    {
        "id": "blueprint_tech",
        "name": "Architectural Blueprint",
        "icon": "📐",
        "category": "Graphic & Experimental",
        "summary": "Classic Prussian-blue cyanotype engineering blueprint with crisp white drafting lines, cross-sections, and grid.",
        "positives": "classic Prussian-blue cyanotype engineering blueprint illustration, crisp white technical drafting ink lines, subtle drafting grid, schematic dimension ticks, clean orthographic precision, vintage paper crease grain",
        "negatives": "full color photo, 3D CGI render, painterly watercolor, dark black background, cartoon fills",
        "motion_cadence": "crisp 24-fps animated technical blueprint motion with clean drafting-line sweeps and stable Prussian-blue cyanotype paper",
        "restyle_prompt": "Turn this image into a classic Prussian-blue Architectural Blueprint with crisp white technical drafting lines, subtle grid markings, and clean schematic precision",
    },
    {
        "id": "pencil_flipbook",
        "name": "Animator's Pencil Flipbook",
        "icon": "📓",
        "category": "2D & Illustration",
        "summary": "Lively rough blue-and-graphite animation pencil drawings on punched animation pegbar paper with construction lines.",
        "positives": "traditional animator's rough pencil flipbook drawing on warm cream animation paper, expressive non-photo blue construction lines under crisp dark graphite pencil strokes, lively gestural motion arcs, visible paper tooth",
        "negatives": "3D CGI, full saturated paint, photorealistic color, glossy plastic, vector perfection",
        "motion_cadence": "energetic hand-drawn 12-fps pencil-test flipbook animation on twos with lively gestural line boil and classic squash-and-stretch arcs",
        "restyle_prompt": "Turn this image into an Animator's Pencil Flipbook drawing with light blue construction lines and expressive dark graphite strokes on warm cream animation paper",
    },
]

# Legacy ID aliases so `realistic` <-> `live_action` and all existing production.STYLES IDs stay 100% compatible
STYLE_ALIASES: dict[str, str] = {
    "realistic": "live_action",
}

# ---------------------------------------------------------------------------
# 42 Character Archetypes (grouped cleanly by category)
# ---------------------------------------------------------------------------
BUILTIN_ARCHETYPES: list[dict[str, Any]] = [
    # --- Humans ---
    {"id": "human", "name": "Adult Human", "category": "Humans", "icon": "🧑", "hint": "Age, build, face shape, skin tone, hair, eyes, wardrobe", "required_physical": ["age", "height", "build", "skin", "hair", "eyes"], "optional_physical": ["facial_hair", "expression", "distinguishing_features", "scars", "tattoos"], "required_fields": ["clothing", "voice"], "optional_fields": ["accessories", "weapons", "posture", "gait"]},
    {"id": "child", "name": "Child", "category": "Humans", "icon": "🧒", "hint": "Age (4–12), proportions/height relative to adults, hair, eyes, everyday outfit", "required_physical": ["age", "hair", "eyes"], "optional_physical": ["height", "build", "skin", "expression", "distinguishing_features"], "required_fields": ["clothing"], "optional_fields": ["voice", "accessories", "posture", "gait"]},
    {"id": "infant_toddler", "name": "Infant / Toddler", "category": "Humans", "icon": "👶", "hint": "Chubby cheeks, wispy hair, onesie/romper, small proportions", "required_physical": ["age", "eyes"], "optional_physical": ["hair", "skin", "expression", "distinguishing_features"], "required_fields": ["clothing"], "optional_fields": ["voice", "accessories", "posture"]},
    {"id": "teen", "name": "Teenager / Young Adult", "category": "Humans", "icon": "🎒", "hint": "Age (13–19), lanky/athletic build, hairstyle, casual or school wardrobe", "required_physical": ["age", "hair", "eyes"], "optional_physical": ["height", "build", "skin", "expression", "distinguishing_features"], "required_fields": ["clothing"], "optional_fields": ["voice", "accessories", "posture", "gait"]},
    {"id": "elder", "name": "Elder / Senior", "category": "Humans", "icon": "🧓", "hint": "Silver/gray hair, laugh lines, glasses, warm knitwear or dignified attire", "required_physical": ["age", "hair", "eyes"], "optional_physical": ["height", "build", "skin", "facial_hair", "expression", "distinguishing_features"], "required_fields": ["clothing"], "optional_fields": ["voice", "accessories", "posture", "gait"]},
    {"id": "chibi", "name": "Stylized / Chibi Human", "category": "Humans", "icon": "🌟", "hint": "2-to-3-head-tall cute proportions, oversized expressive eyes, simplified silhouette", "required_physical": ["hair", "eyes"], "optional_physical": ["skin", "expression", "distinguishing_features"], "required_fields": ["clothing"], "optional_fields": ["voice", "accessories", "posture"]},
    {"id": "historical", "name": "Historical / Period Figure", "category": "Humans", "icon": "🏛️", "hint": "Era-accurate garments, hairstyle, headwear, and period props", "required_physical": ["age", "hair", "eyes"], "optional_physical": ["height", "build", "skin", "facial_hair", "expression", "distinguishing_features"], "required_fields": ["clothing"], "optional_fields": ["voice", "accessories", "weapons", "posture"]},
    {"id": "astronaut", "name": "Sci-Fi Explorer / Astronaut", "category": "Humans", "icon": "👩‍🚀", "hint": "Flight suit or spacesuit, visor/helmet details, mission patches, boots", "required_physical": ["age", "hair", "eyes"], "optional_physical": ["height", "build", "skin", "expression", "distinguishing_features"], "required_fields": ["clothing"], "optional_fields": ["voice", "accessories", "armor", "posture"]},
    {"id": "fantasy_hero", "name": "Fantasy Adventurer / Mage", "category": "Humans", "icon": "🧙", "hint": "Cloak, tunic, armor or mage robes, staff/sword, magical accents", "required_physical": ["age", "hair", "eyes"], "optional_physical": ["height", "build", "skin", "facial_hair", "expression", "scars"], "required_fields": ["clothing"], "optional_fields": ["voice", "accessories", "weapons", "armor", "aura"]},
    {"id": "superhero", "name": "Superhero / Vigilante", "category": "Humans", "icon": "🦸", "hint": "Suit palette, emblem, mask/cape, athletic silhouette, boots", "required_physical": ["build", "eyes"], "optional_physical": ["age", "height", "skin", "hair", "expression", "distinguishing_features"], "required_fields": ["clothing"], "optional_fields": ["voice", "accessories", "armor", "aura", "posture"]},

    # --- Animals & Anthropomorphic ---
    {"id": "domestic_pet", "name": "Domestic Pet (Dog / Cat / Horse)", "category": "Animals & Anthro", "icon": "🐕", "hint": "Breed, coat color/texture, ear shape, eye color, tail, collar/vest", "required_physical": [], "optional_physical": ["height", "build", "skin", "eyes", "expression", "distinguishing_features"], "required_fields": [], "optional_fields": ["voice", "clothing", "accessories", "posture", "gait"]},
    {"id": "wild_mammal", "name": "Wild Mammal (Bear / Fox / Wolf / Lion)", "category": "Animals & Anthro", "icon": "🦊", "hint": "Species, fur markings, snout/ears, claws, natural posture", "required_physical": [], "optional_physical": ["height", "build", "skin", "eyes", "expression", "distinguishing_features", "scars"], "required_fields": [], "optional_fields": ["voice", "accessories", "posture", "gait"]},
    {"id": "avian", "name": "Bird / Avian", "category": "Animals & Anthro", "icon": "🦉", "hint": "Species, plumage colors, beak shape, wing span, talons", "required_physical": [], "optional_physical": ["height", "build", "eyes", "wings", "expression", "distinguishing_features"], "required_fields": [], "optional_fields": ["voice", "accessories", "posture"]},
    {"id": "marine", "name": "Marine / Aquatic Creature", "category": "Animals & Anthro", "icon": "🐙", "hint": "Species, scales/fins/tentacles, color pattern, bioluminescence", "required_physical": [], "optional_physical": ["height", "build", "skin", "eyes", "expression", "distinguishing_features", "luminosity"], "required_fields": [], "optional_fields": ["voice", "accessories", "posture"]},
    {"id": "reptile", "name": "Reptile / Dinosaur / Amphibian", "category": "Animals & Anthro", "icon": "🦖", "hint": "Species, scale texture, crest/horns, tail length, eye slits", "required_physical": [], "optional_physical": ["height", "build", "skin", "eyes", "expression", "distinguishing_features", "scars"], "required_fields": [], "optional_fields": ["voice", "accessories", "posture", "gait"]},
    {"id": "insect", "name": "Insect / Bug", "category": "Animals & Anthro", "icon": "🦋", "hint": "Species, shell/carapace colors, antennae, wing pattern, leg count", "required_physical": [], "optional_physical": ["height", "build", "eyes", "wings", "distinguishing_features"], "required_fields": [], "optional_fields": ["voice", "accessories", "posture"]},
    {"id": "anthro_animal", "name": "Anthropomorphic Talking Animal", "category": "Animals & Anthro", "icon": "🐰", "hint": "Bipedal animal species, fur/feather palette, expressive face, full wardrobe", "required_physical": [], "optional_physical": ["age", "height", "build", "skin", "eyes", "expression", "distinguishing_features"], "required_fields": [], "optional_fields": ["voice", "clothing", "accessories", "posture", "gait"]},
    {"id": "creature", "name": "Creature / Fantasy Beast", "category": "Animals & Anthro", "icon": "🐾", "hint": "General animal, monster, or fantasy creature traits", "required_physical": [], "optional_physical": ["height", "build", "skin", "eyes", "expression", "distinguishing_features", "scars"], "required_fields": [], "optional_fields": ["voice", "clothing", "accessories", "posture", "gait"]},

    # --- Toys, Dolls & Objects ---
    {"id": "rag_doll", "name": "Rag Doll / Plush Toy", "category": "Toys & Objects", "icon": "🪡", "hint": "Fabric skin, yarn hair, button eyes, stitched seams, soft floppy limbs", "required_physical": [], "optional_physical": ["height", "build", "skin", "hair", "eyes", "expression", "distinguishing_features"], "required_fields": [], "optional_fields": ["voice", "clothing", "accessories", "posture"]},
    {"id": "action_figure", "name": "Action Figure / Plastic Toy", "category": "Toys & Objects", "icon": "🎖️", "hint": "Molded plastic sheen, visible hinged joints, painted face, molded gear", "required_physical": [], "optional_physical": ["height", "build", "skin", "hair", "eyes", "expression", "distinguishing_features"], "required_fields": [], "optional_fields": ["voice", "clothing", "accessories", "weapons", "armor", "posture"]},
    {"id": "minifigure", "name": "Toy Brick Minifigure", "category": "Toys & Objects", "icon": "🧱", "hint": "Glossy ABS cylindrical head, snap-on hair/hat, printed face, C-hands, hinged legs", "required_physical": [], "optional_physical": ["hair", "eyes", "expression", "distinguishing_features"], "required_fields": [], "optional_fields": ["voice", "clothing", "accessories", "posture"]},
    {"id": "puppet", "name": "Puppet / Marionette", "category": "Toys & Objects", "icon": "🎭", "hint": "Fleece/wooden construction, hinged mouth or wooden strings, miniature costume", "required_physical": [], "optional_physical": ["height", "build", "hair", "eyes", "expression", "distinguishing_features"], "required_fields": [], "optional_fields": ["voice", "clothing", "accessories", "posture"]},
    {"id": "living_object", "name": "Living Object / Talking Vehicle", "category": "Toys & Objects", "icon": "🚂", "hint": "Object type (train, lamp, teapot, car), surface finish, expressive eyes/face placement", "required_physical": [], "optional_physical": ["height", "build", "eyes", "expression", "distinguishing_features"], "required_fields": [], "optional_fields": ["voice", "accessories", "posture"]},

    # --- Sci-Fi & Tech ---
    {"id": "robot", "name": "Robot / Cute Machine", "category": "Sci-Fi & Tech", "icon": "🤖", "hint": "Chassis material, paint color, glowing LED eyes/visor, joints, antennae", "required_physical": [], "optional_physical": ["height", "build", "eyes", "expression", "distinguishing_features"], "required_fields": [], "optional_fields": ["voice", "clothing", "accessories", "weapons", "armor", "posture", "gait"]},
    {"id": "android", "name": "Humanoid Android / Cyborg", "category": "Sci-Fi & Tech", "icon": "🦾", "hint": "Synthetic skin + visible chrome seams/cybernetics, glowing eyes, sleek suit", "required_physical": [], "optional_physical": ["age", "height", "build", "skin", "hair", "eyes", "expression", "distinguishing_features"], "required_fields": [], "optional_fields": ["voice", "clothing", "accessories", "armor", "weapons"]},
    {"id": "mecha", "name": "Giant Mecha / Mech Suit", "category": "Sci-Fi & Tech", "icon": "🦿", "hint": "Armor plating palette, cockpit/visor, thrusters, scale, weathered metal", "required_physical": [], "optional_physical": ["height", "build", "eyes", "distinguishing_features"], "required_fields": [], "optional_fields": ["voice", "armor", "weapons", "accessories", "posture"]},
    {"id": "alien", "name": "Alien / Extraterrestrial", "category": "Sci-Fi & Tech", "icon": "👽", "hint": "Skin color/texture, head shape, eye/limb count, antennae, alien attire", "required_physical": [], "optional_physical": ["height", "build", "skin", "eyes", "expression", "distinguishing_features", "luminosity"], "required_fields": [], "optional_fields": ["voice", "clothing", "accessories", "posture"]},
    {"id": "hologram", "name": "Hologram / AI Avatar", "category": "Sci-Fi & Tech", "icon": "💠", "hint": "Translucent cyan/gold scanlines, glowing silhouette, floating geometry", "required_physical": [], "optional_physical": ["height", "build", "eyes", "expression", "luminosity", "distinguishing_features"], "required_fields": [], "optional_fields": ["voice", "clothing", "light_color", "aura"]},

    # --- Fantasy & Myth ---
    {"id": "winged_dragon", "name": "Dragon / Winged Beast", "category": "Fantasy & Myth", "icon": "🐉", "hint": "Scale color, horn shape, bat/feathered wings, tail, breath element", "required_physical": [], "optional_physical": ["height", "build", "skin", "eyes", "wings", "expression", "distinguishing_features", "scars"], "required_fields": [], "optional_fields": ["voice", "fire_effects", "aura", "posture"]},
    {"id": "fairy", "name": "Fairy / Sprite", "category": "Fantasy & Myth", "icon": "🧚", "hint": "Tiny scale, iridescent insect/butterfly wings, petal/leaf wardrobe, soft glow", "required_physical": [], "optional_physical": ["height", "hair", "eyes", "wings", "skin", "luminosity", "expression"], "required_fields": [], "optional_fields": ["voice", "clothing", "accessories", "light_color", "aura"]},
    {"id": "elf_dwarf_orc", "name": "Elf / Dwarf / Orc / Fantasy Folk", "category": "Fantasy & Myth", "icon": "🧝", "hint": "Pointed ears/tusks/braided beard, build, fantasy clothing or armor", "required_physical": [], "optional_physical": ["age", "height", "build", "skin", "hair", "eyes", "facial_hair", "expression", "distinguishing_features"], "required_fields": [], "optional_fields": ["voice", "clothing", "weapons", "armor", "accessories"]},
    {"id": "merfolk", "name": "Merfolk / Sea Spirit", "category": "Fantasy & Myth", "icon": "🧜", "hint": "Iridescent fish tail scales, fins, flowing aquatic hair, sea-shell accents", "required_physical": [], "optional_physical": ["age", "height", "build", "skin", "hair", "eyes", "expression", "distinguishing_features"], "required_fields": [], "optional_fields": ["voice", "clothing", "accessories", "aura"]},
    {"id": "elemental", "name": "Elemental / Golem (Stone / Fire / Ice)", "category": "Fantasy & Myth", "icon": "🪨", "hint": "Primary material (rock, magma, crystal, water, wood), glowing core, massive silhouette", "required_physical": [], "optional_physical": ["height", "build", "eyes", "luminosity", "distinguishing_features"], "required_fields": [], "optional_fields": ["voice", "fire_effects", "light_color", "aura", "posture"]},
    {"id": "ghost_spirit", "name": "Ghost / Spirit / Undead", "category": "Fantasy & Myth", "icon": "👻", "hint": "Translucent misty form, spectral glow, floating posture, era-specific attire", "required_physical": [], "optional_physical": ["age", "height", "hair", "eyes", "luminosity", "expression", "distinguishing_features"], "required_fields": [], "optional_fields": ["voice", "clothing", "light_color", "aura", "posture"]},
    {"id": "kaiju", "name": "Giant Monster / Kaiju", "category": "Fantasy & Myth", "icon": "🦖", "hint": "Colossal scale, dorsal plates/spines, textured hide, glowing energy veins", "required_physical": [], "optional_physical": ["height", "build", "skin", "eyes", "distinguishing_features", "luminosity"], "required_fields": [], "optional_fields": ["voice", "fire_effects", "aura", "posture"]},
    {"id": "shapeshifter", "name": "Shapeshifter / Chimera", "category": "Fantasy & Myth", "icon": "🦋", "hint": "Primary form, signature eyes/marking that persists across transformations", "required_physical": [], "optional_physical": ["height", "build", "skin", "hair", "eyes", "expression", "shifting_features", "distinguishing_features"], "required_fields": [], "optional_fields": ["voice", "clothing", "aura"]},
    {"id": "supernatural", "name": "Supernatural / Magical Being", "category": "Fantasy & Myth", "icon": "🔮", "hint": "Mystical traits, aura, luminosity, magical attire", "required_physical": [], "optional_physical": ["age", "height", "build", "skin", "hair", "eyes", "expression", "distinguishing_features", "luminosity"], "required_fields": [], "optional_fields": ["voice", "clothing", "accessories", "posture", "gait", "aura"]},

    # --- Biblical & Epic (original Studio archetypes preserved 100%) ---
    {"id": "human_pre_fall", "name": "Pre-Fall Human", "category": "Biblical & Epic", "icon": "🌿", "hint": "Unashamed Eden state, radiant natural dignity", "required_physical": ["age", "height", "build", "skin", "hair", "eyes", "expression"], "optional_physical": ["facial_hair", "distinguishing_features"], "required_fields": ["clothing"], "optional_fields": ["voice", "posture", "gait"]},
    {"id": "human_prophet", "name": "Prophet", "category": "Biblical & Epic", "icon": "📜", "hint": "Weathered robe, mantle, staff, intense prophetic presence", "required_physical": ["age", "height", "build", "skin", "hair", "eyes", "expression"], "optional_physical": ["facial_hair", "distinguishing_features", "scars"], "required_fields": ["clothing", "voice"], "optional_fields": ["accessories", "posture", "gait", "aura"]},
    {"id": "human_patriarch", "name": "Patriarch", "category": "Biblical & Epic", "icon": "👑", "hint": "Beard, weathered dignity, authority markers, shepherd/tribal mantle", "required_physical": ["age", "height", "build", "skin", "hair", "eyes", "facial_hair"], "optional_physical": ["expression", "distinguishing_features", "scars"], "required_fields": ["clothing", "voice"], "optional_fields": ["accessories", "weapons", "posture", "gait", "authority_markers"]},
    {"id": "human_warrior", "name": "Epic Warrior / King", "category": "Biblical & Epic", "icon": "⚔️", "hint": "Armor, weaponry, battle-worn traits, commanding posture", "required_physical": ["age", "height", "build", "skin", "hair", "eyes"], "optional_physical": ["facial_hair", "expression", "distinguishing_features", "scars", "musculature"], "required_fields": ["clothing", "voice"], "optional_fields": ["weapons", "armor", "accessories", "posture", "gait", "battle_worn"]},
    {"id": "angel_messenger", "name": "Messenger Angel", "category": "Biblical & Epic", "icon": "🪽", "hint": "Radiant wings, luminous garments, serene presence", "required_physical": ["height", "build", "eyes", "wings"], "optional_physical": ["hair", "skin", "expression", "face_covering", "luminosity"], "required_fields": ["clothing", "voice"], "optional_fields": ["accessories", "posture", "light_color", "aura"]},
    {"id": "angel_warrior", "name": "Warrior Angel", "category": "Biblical & Epic", "icon": "🛡️", "hint": "Celestial armor, radiant wings, flaming sword", "required_physical": ["height", "build", "eyes", "wings"], "optional_physical": ["hair", "skin", "expression", "face_covering", "luminosity", "musculature", "scars"], "required_fields": ["clothing", "voice"], "optional_fields": ["armor", "accessories", "posture", "light_color", "aura", "weapons"]},
    {"id": "angel_guardian", "name": "Guardian Cherubim", "category": "Biblical & Epic", "icon": "✨", "hint": "Multiple wings and faces, radiant authority", "required_physical": ["height", "build", "eyes", "wings", "faces"], "optional_physical": ["hair", "skin", "expression", "luminosity"], "required_fields": ["clothing"], "optional_fields": ["voice", "accessories", "posture", "light_color", "aura"]},
    {"id": "angel_seraphim", "name": "Seraphim", "category": "Biblical & Epic", "icon": "🔥", "hint": "Six fiery luminous wings", "required_physical": ["height", "wings"], "optional_physical": ["build", "eyes", "expression", "luminosity", "faces"], "required_fields": [], "optional_fields": ["voice", "clothing", "posture", "light_color", "fire_effects", "aura"]},
    {"id": "angel_living_creature", "name": "Living Creature", "category": "Biblical & Epic", "icon": "👁️", "hint": "Four faces, wings full of eyes, radiant form", "required_physical": ["faces", "wings"], "optional_physical": ["eyes_covered_in_wings", "form", "luminosity", "expression"], "required_fields": [], "optional_fields": ["voice", "posture", "light_color", "aura"]},
    {"id": "divine_presence", "name": "Divine Presence", "category": "Biblical & Epic", "icon": "☀️", "hint": "Overwhelming light, cloud, fire, accompanying phenomena", "required_physical": [], "optional_physical": ["luminosity", "formlessness", "manifestation", "eyes", "voice_quality"], "required_fields": [], "optional_fields": ["clothing", "light_color", "accompanying_phenomena", "aura"]},
    {"id": "fallen_angel", "name": "Fallen Angel", "category": "Biblical & Epic", "icon": "🌑", "hint": "Shadowed or charred wings, scars, dark aura", "required_physical": ["height", "build", "skin", "eyes", "wings"], "optional_physical": ["hair", "expression", "scars", "chains", "corruption"], "required_fields": ["clothing", "voice"], "optional_fields": ["weapons", "accessories", "posture", "light_color", "fire_effects", "aura"]},
    {"id": "fallen_disguised", "name": "Disguised Adversary", "category": "Biblical & Epic", "icon": "🎭", "hint": "Uncanny perfection, subtle shifting features", "required_physical": ["height", "build", "skin", "eyes", "expression"], "optional_physical": ["hair", "shifting_features", "unsettling_quality", "perfection"], "required_fields": ["clothing", "voice"], "optional_fields": ["accessories", "posture", "light_color", "aura"]},

    # --- 2D Hybrid, Story & Graphic Character Types (24+ more archetypes) ---
    {"id": "vintage_cartoon_sidekick", "name": "Vintage 2D Cartoon Sidekick", "category": "Hybrid & Cartoon", "icon": "🎞️", "hint": "1940s hand-drawn cel proportions, clean dark ink outlines, expressive muzzle/eyes, cozy coat or overalls", "required_physical": [], "optional_physical": ["height", "build", "skin", "eyes", "expression", "distinguishing_features"], "required_fields": [], "optional_fields": ["voice", "clothing", "accessories", "posture"]},
    {"id": "woodland_critter", "name": "Woodland Critter (Bear / Otter / Badger)", "category": "Animals & Anthro", "icon": "🐻", "hint": "Friendly storybook bear, otter, fox, or badger in knitted scarf, wool coat, or felt hat", "required_physical": [], "optional_physical": ["height", "build", "skin", "eyes", "expression", "distinguishing_features"], "required_fields": [], "optional_fields": ["voice", "clothing", "accessories", "posture"]},
    {"id": "talking_songbird", "name": "Talking Songbird / Companion Bird", "category": "Animals & Anthro", "icon": "🐦", "hint": "Small perched/flying bluebird, robin, or owl with expressive eyes, beak, and wing plumage", "required_physical": [], "optional_physical": ["height", "eyes", "wings", "expression", "distinguishing_features"], "required_fields": [], "optional_fields": ["voice", "accessories", "posture"]},
    {"id": "drawn_prop", "name": "Animated Drawn Prop / Living Relic", "category": "Hybrid & Cartoon", "icon": "☂️", "hint": "Hand-drawn umbrella, lantern, magic book, sword, or teacup rendered in matching 2D ink style", "required_physical": [], "optional_physical": ["height", "eyes", "expression", "distinguishing_features"], "required_fields": [], "optional_fields": ["voice", "accessories", "aura"]},
    {"id": "chalkboard_mascot", "name": "Chalkboard Doodle Mascot", "category": "Hybrid & Cartoon", "icon": "🖍️", "hint": "Hand-drawn chalk figure with rough dusty white outlines and bright accent chalk accessories", "required_physical": [], "optional_physical": ["height", "eyes", "expression", "distinguishing_features"], "required_fields": [], "optional_fields": ["voice", "accessories", "posture"]},
    {"id": "line_figure", "name": "Minimal Line-Diagram Figure", "category": "Hybrid & Cartoon", "icon": "📏", "hint": "Clean articulated hairline silhouette with dot joints and geometric halo rings", "required_physical": [], "optional_physical": ["height", "build", "expression", "distinguishing_features"], "required_fields": [], "optional_fields": ["voice", "accessories", "posture"]},
    {"id": "pixel_hero", "name": "Pixel-Art RPG / Arcade Hero", "category": "Hybrid & Cartoon", "icon": "🕹️", "hint": "Iconic crisp sprite silhouette, bold readable color blocks, cape/pack, signature item", "required_physical": [], "optional_physical": ["height", "hair", "eyes", "expression", "distinguishing_features"], "required_fields": [], "optional_fields": ["voice", "clothing", "weapons", "accessories"]},
    {"id": "shadow_silhouette", "name": "Shadow-Puppet Silhouette", "category": "Hybrid & Cartoon", "icon": "🏮", "hint": "Distinctive dramatic profile silhouette, ornate cloak/hat cutout, luminous backlit eyes", "required_physical": [], "optional_physical": ["height", "build", "eyes", "distinguishing_features"], "required_fields": [], "optional_fields": ["voice", "clothing", "accessories", "posture"]},
    {"id": "paper_doll", "name": "Paper-Cutout Character", "category": "Toys & Objects", "icon": "✂️", "hint": "Layered colored construction-paper body parts, crisp scissor edges, visible paper grain", "required_physical": [], "optional_physical": ["height", "hair", "eyes", "expression", "distinguishing_features"], "required_fields": [], "optional_fields": ["voice", "clothing", "accessories"]},
    {"id": "clockwork_automaton", "name": "Clockwork / Steampunk Automaton", "category": "Sci-Fi & Tech", "icon": "⚙️", "hint": "Riveted brass plating, visible gears, glowing amber lens eyes, wind-up key", "required_physical": [], "optional_physical": ["height", "build", "eyes", "expression", "distinguishing_features"], "required_fields": [], "optional_fields": ["voice", "clothing", "accessories", "posture"]},
    {"id": "noir_detective", "name": "Noir Detective / Sleuth", "category": "Humans", "icon": "🕵️", "hint": "Trench coat, fedora, sharp gaze, weathered jawline, atmospheric shadow lighting", "required_physical": ["age", "hair", "eyes"], "optional_physical": ["height", "build", "skin", "facial_hair", "expression", "scars"], "required_fields": ["clothing"], "optional_fields": ["voice", "accessories", "posture"]},
    {"id": "space_pilot", "name": "Starship Captain / Pilot", "category": "Sci-Fi & Tech", "icon": "🚀", "hint": "Flight jacket or captain's uniform, insignia badges, headset/visor, confident stance", "required_physical": ["age", "hair", "eyes"], "optional_physical": ["height", "build", "skin", "expression", "distinguishing_features"], "required_fields": ["clothing"], "optional_fields": ["voice", "accessories", "posture"]},
    {"id": "pirate_adventurer", "name": "Pirate / Sea Explorer", "category": "Humans", "icon": "🏴‍☠️", "hint": "Weathered coat, tricorn or bandana, brass spyglass, boots, salty adventurous charm", "required_physical": ["age", "hair", "eyes"], "optional_physical": ["height", "build", "skin", "facial_hair", "scars", "expression"], "required_fields": ["clothing"], "optional_fields": ["voice", "weapons", "accessories", "posture"]},
    {"id": "wizard_mage", "name": "Wizard / Sorcerer / Alchemist", "category": "Fantasy & Myth", "icon": "🔮", "hint": "Pointed hat or hooded cloak, rune-embroidered robes, glowing staff, arcane pouches", "required_physical": ["age", "hair", "eyes"], "optional_physical": ["height", "build", "skin", "facial_hair", "expression", "luminosity"], "required_fields": ["clothing"], "optional_fields": ["voice", "accessories", "aura", "light_color"]},
    {"id": "royal_monarch", "name": "Royal Monarch (King / Queen / Prince)", "category": "Humans", "icon": "👑", "hint": "Crown or circlet, velvet mantle, brocade garments, regal bearing", "required_physical": ["age", "hair", "eyes"], "optional_physical": ["height", "build", "skin", "facial_hair", "expression"], "required_fields": ["clothing"], "optional_fields": ["voice", "accessories", "authority_markers", "posture"]},
    {"id": "steampunk_inventor", "name": "Steampunk / Gadget Inventor", "category": "Humans", "icon": "🥽", "hint": "Brass goggles on forehead, leather apron, rolled sleeves, pocket tools, soot smudge", "required_physical": ["age", "hair", "eyes"], "optional_physical": ["height", "build", "skin", "expression", "distinguishing_features"], "required_fields": ["clothing"], "optional_fields": ["voice", "accessories", "posture"]},
    {"id": "chef_innkeeper", "name": "Cozy Chef / Tavern Innkeeper", "category": "Humans", "icon": "🍲", "hint": "Warm apron, rolled sleeves, wooden spoon or lantern, welcoming smile", "required_physical": ["age", "hair", "eyes"], "optional_physical": ["height", "build", "skin", "facial_hair", "expression"], "required_fields": ["clothing"], "optional_fields": ["voice", "accessories", "posture"]},
    {"id": "villain_mastermind", "name": "Villain / Dramatic Mastermind", "category": "Humans", "icon": "🦹", "hint": "Angular silhouette, high-collar cloak or sharp suit, intense gaze, signature scar or emblem", "required_physical": ["age", "hair", "eyes"], "optional_physical": ["height", "build", "skin", "facial_hair", "scars", "expression"], "required_fields": ["clothing"], "optional_fields": ["voice", "accessories", "weapons", "aura"]},
    {"id": "superhero_sidekick", "name": "Hero Sidekick / Junior Apprentice", "category": "Humans", "icon": "⚡", "hint": "Youthful energetic build, bright accent scarf/cape, nimble stance, expressive grin", "required_physical": ["age", "hair", "eyes"], "optional_physical": ["height", "build", "skin", "expression", "distinguishing_features"], "required_fields": ["clothing"], "optional_fields": ["voice", "accessories", "posture"]},
    {"id": "cowboy_western", "name": "Frontier Cowboy / Ranger", "category": "Humans", "icon": "🤠", "hint": "Wide-brim hat, dusty duster coat, bandana, leather boots, sun-weathered face", "required_physical": ["age", "hair", "eyes"], "optional_physical": ["height", "build", "skin", "facial_hair", "scars", "expression"], "required_fields": ["clothing"], "optional_fields": ["voice", "accessories", "weapons", "posture"]},
    {"id": "samurai_ninja", "name": "Samurai / Martial Artist", "category": "Humans", "icon": "🥷", "hint": "Layered kimono or lacquered armor, headband/obi, disciplined martial posture", "required_physical": ["age", "hair", "eyes"], "optional_physical": ["height", "build", "skin", "scars", "expression"], "required_fields": ["clothing"], "optional_fields": ["voice", "weapons", "armor", "posture"]},
    {"id": "knight_paladin", "name": "Armored Knight / Paladin", "category": "Fantasy & Myth", "icon": "🛡️", "hint": "Engraved plate armor, heraldic tabard, shield, noble visor or plumed helm", "required_physical": ["age", "eyes"], "optional_physical": ["height", "build", "hair", "skin", "scars", "expression"], "required_fields": ["clothing"], "optional_fields": ["voice", "armor", "weapons", "accessories"]},
    {"id": "friendly_giant", "name": "Gentle Giant / Colossal Friend", "category": "Fantasy & Myth", "icon": "🏔️", "hint": "Towering warm silhouette, patched oversized coat, kind expressive eyes, heavy gentle steps", "required_physical": ["height", "build", "eyes"], "optional_physical": ["age", "skin", "hair", "facial_hair", "expression"], "required_fields": [], "optional_fields": ["voice", "clothing", "accessories", "posture"]},
    {"id": "musical_mascot", "name": "Animated Musical / Storybook Mascot", "category": "Toys & Objects", "icon": "🎺", "hint": "Expressive cartoon emblem or living instrument with bright eyes and buoyant rhythm", "required_physical": [], "optional_physical": ["height", "eyes", "expression", "distinguishing_features"], "required_fields": [], "optional_fields": ["voice", "accessories", "posture"]},
]


def load_custom_registry(path: Path = CUSTOM_REGISTRY_PATH) -> dict[str, list[dict[str, Any]]]:
    """Load user-added custom visual styles and character archetypes from JSON."""
    if not path.is_file():
        return {"styles": [], "archetypes": []}
    try:
        data = json.loads(path.read_text(encoding="utf-8")) or {}
        return {
            "styles": [x for x in (data.get("styles") or []) if isinstance(x, dict) and x.get("id")],
            "archetypes": [x for x in (data.get("archetypes") or []) if isinstance(x, dict) and x.get("id")],
        }
    except (OSError, ValueError):
        return {"styles": [], "archetypes": []}


def _save_custom_registry(data: dict[str, list[dict[str, Any]]], path: Path = CUSTOM_REGISTRY_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def list_styles(custom_path: Path = CUSTOM_REGISTRY_PATH) -> list[dict[str, str]]:
    """Return all built-in + custom visual styles (custom overrides built-in by ID)."""
    samples_dir = ROOT / "web" / "static" / "img" / "style_samples"
    by_id: dict[str, dict[str, str]] = {s["id"]: dict(s) for s in BUILTIN_STYLES}
    for cs in load_custom_registry(custom_path)["styles"]:
        sid = str(cs["id"]).strip().lower()
        if sid:
            by_id[sid] = {
                "id": sid,
                "name": str(cs.get("name") or sid),
                "icon": str(cs.get("icon") or "🎨"),
                "category": str(cs.get("category") or "Custom"),
                "summary": str(cs.get("summary") or cs.get("positives") or "")[:180],
                "positives": str(cs.get("positives") or ""),
                "negatives": str(cs.get("negatives") or ""),
                "motion_cadence": str(cs.get("motion_cadence") or ""),
                "restyle_prompt": str(cs.get("restyle_prompt") or f"Turn this image into {cs.get('name') or sid} style: {cs.get('positives') or ''}"),
                "custom": "true",
            }
    out: list[dict[str, str]] = []
    for sid, entry in by_id.items():
        gif_file = samples_dir / f"{sid}.gif"
        png_file = samples_dir / f"{sid}.png"
        if gif_file.is_file():
            entry["sample_url"] = f"/static/img/style_samples/{sid}.gif"
        elif png_file.is_file():
            entry["sample_url"] = f"/static/img/style_samples/{sid}.png"
        else:
            entry["sample_url"] = ""
        out.append(entry)
    return out


def get_style(style_id: str, custom_path: Path = CUSTOM_REGISTRY_PATH) -> dict[str, str] | None:
    """Lookup one style by ID (resolving legacy aliases like `realistic` -> `live_action`)."""
    raw = str(style_id or "").strip().lower()
    if not raw:
        return None
    target = STYLE_ALIASES.get(raw, raw)
    for st in list_styles(custom_path):
        if st["id"] == target:
            return st
    return None


def list_archetypes(custom_path: Path = CUSTOM_REGISTRY_PATH) -> list[dict[str, Any]]:
    """Return all built-in + custom character archetypes."""
    by_id: dict[str, dict[str, Any]] = {a["id"]: dict(a) for a in BUILTIN_ARCHETYPES}
    for ca in load_custom_registry(custom_path)["archetypes"]:
        aid = str(ca["id"]).strip().lower()
        if aid:
            by_id[aid] = {
                "id": aid,
                "name": str(ca.get("name") or aid),
                "category": str(ca.get("category") or "Custom"),
                "icon": str(ca.get("icon") or "✨"),
                "hint": str(ca.get("hint") or ""),
                "required_physical": list(ca.get("required_physical") or []),
                "optional_physical": list(ca.get("optional_physical") or ["height", "build", "eyes", "expression", "distinguishing_features"]),
                "required_fields": list(ca.get("required_fields") or []),
                "optional_fields": list(ca.get("optional_fields") or ["voice", "clothing", "accessories", "posture"]),
                "custom": True,
            }
    return list(by_id.values())


def save_custom_style(payload: dict[str, Any], custom_path: Path = CUSTOM_REGISTRY_PATH) -> dict[str, str]:
    """Create or update a custom visual style in `config/custom_character_types.json`."""
    name = str(payload.get("name") or payload.get("label") or "").strip()
    positives = str(payload.get("positives") or "").strip()
    if not name or not positives:
        raise ValueError("Custom style requires a name and positive style keywords.")
    sid = _clean_id(str(payload.get("id") or name), prefix="style")
    entry: dict[str, str] = {
        "id": sid,
        "name": name[:60],
        "icon": str(payload.get("icon") or "🎨")[:4],
        "category": str(payload.get("category") or "Custom")[:40],
        "summary": str(payload.get("summary") or positives)[:180],
        "positives": positives[:1200],
        "negatives": str(payload.get("negatives") or "")[:800],
        "motion_cadence": str(payload.get("motion_cadence") or "")[:600],
        "restyle_prompt": str(payload.get("restyle_prompt") or f"Turn this image into {name} style: {positives}")[:1000],
    }
    reg = load_custom_registry(custom_path)
    reg["styles"] = [s for s in reg["styles"] if s.get("id") != sid] + [entry]
    _save_custom_registry(reg, custom_path)
    return entry


def save_custom_archetype(payload: dict[str, Any], custom_path: Path = CUSTOM_REGISTRY_PATH) -> dict[str, Any]:
    """Create or update a custom character archetype in `config/custom_character_types.json`."""
    name = str(payload.get("name") or payload.get("label") or "").strip()
    if not name:
        raise ValueError("Custom character type requires a name.")
    aid = _clean_id(str(payload.get("id") or name), prefix="char")
    entry: dict[str, Any] = {
        "id": aid,
        "name": name[:60],
        "icon": str(payload.get("icon") or "✨")[:4],
        "category": str(payload.get("category") or "Custom")[:40],
        "hint": str(payload.get("hint") or "")[:240],
        "required_physical": [],
        "optional_physical": ["height", "build", "skin", "hair", "eyes", "expression", "distinguishing_features"],
        "required_fields": [],
        "optional_fields": ["voice", "clothing", "accessories", "posture"],
    }
    reg = load_custom_registry(custom_path)
    reg["archetypes"] = [a for a in reg["archetypes"] if a.get("id") != aid] + [entry]
    _save_custom_registry(reg, custom_path)
    return entry


def production_styles_dict(custom_path: Path = CUSTOM_REGISTRY_PATH) -> dict[str, tuple[str, str]]:
    """Export `{style_id: (display_name, positives_description)}` compatible with `production.STYLES`."""
    out: dict[str, tuple[str, str]] = {}
    for st in list_styles(custom_path):
        out[st["id"]] = (st["name"], st["positives"])
    # Preserve legacy `"realistic"` alias alongside `"live_action"`
    if "live_action" in out and "realistic" not in out:
        out["realistic"] = ("Realistic live action", out["live_action"][1])
    return out


def registry_payload(custom_path: Path = CUSTOM_REGISTRY_PATH) -> dict[str, Any]:
    """Full JSON payload for `GET /api/character_types`."""
    styles = list_styles(custom_path)
    archetypes = list_archetypes(custom_path)
    style_cats = list(dict.fromkeys(s["category"] for s in styles))
    arch_cats = list(dict.fromkeys(a["category"] for a in archetypes))
    return {
        "styles": styles,
        "archetypes": archetypes,
        "style_categories": style_cats,
        "archetype_categories": arch_cats,
    }
