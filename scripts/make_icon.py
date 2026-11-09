#!/usr/bin/env python3
"""Draw the Pistachio's Studio app icon: a bright P and S on a dark rounded square, placed so the top-left of the S touches the bottom-right of the P's curve.

  python3 scripts/make_icon.py [OUT_DIR]            writes icon_1024.png and icon.icns into OUT_DIR (default: a temp folder, printed)
  python3 scripts/make_icon.py --favicon web/index.html  also (re)writes the favicon <link> tags between the favicon markers in that page

create_app_bundle.sh runs this and copies icon.icns into the app. Needs Pillow and macOS (iconutil) for the .icns step.
"""
import base64
import io
import re
import subprocess
import sys
import tempfile
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont

FONT = "/System/Library/Fonts/Supplemental/Arial Black.ttf"
SIZE = 1024
BG_TOP, BG_BOTTOM = (22, 14, 64), (70, 24, 120)          # deep indigo to violet
P_COLOUR = (185, 245, 60)                                # pistachio / lime
S_COLOUR = (255, 84, 110)                                # hot coral pink
GLYPH_PX = 640
TOUCH = (8, 4)                                           # nudge: the S overlaps the P's curve just a little


def glyph_mask(ch):
    font = ImageFont.truetype(FONT, GLYPH_PX)
    m = Image.new("L", (GLYPH_PX * 2, GLYPH_PX * 2), 0)
    ImageDraw.Draw(m).text((GLYPH_PX // 2, GLYPH_PX // 4), ch, font=font, fill=255)
    return m.crop(m.getbbox())


def p_bowl_corner(m):
    """The bottom-right of the P's curve: where the bowl's right edge turns back in."""
    w, h = m.size
    px = m.load()
    right = []
    for y in range(h):
        xs = [x for x in range(w) if px[x, y] > 127]
        right.append(max(xs) if xs else -1)
    xmax = max(right[: int(h * 0.7)])
    y0 = right.index(xmax)
    y = y0
    while y < h and right[y] >= xmax - int(w * 0.12):
        y += 1
    y = min(y, int(h * 0.7))
    return right[y - 1], y - 1


def s_top_left(m):
    """The top-left of the S: the leftmost point of its upper curve."""
    w, h = m.size
    px = m.load()
    best = (w, 0)
    for y in range(int(h * 0.04), int(h * 0.30)):
        xs = [x for x in range(w) if px[x, y] > 127]
        if xs and min(xs) < best[0]:
            best = (min(xs), y)
    return best


def build():
    p, s = glyph_mask("P"), glyph_mask("S")
    px_, py_ = p_bowl_corner(p)
    sx, sy = s_top_left(s)
    # canvas big enough for both, with S moved so its top-left lands on the P's bowl corner
    ox, oy = px_ - sx + TOUCH[0], py_ - sy + TOUCH[1]        # where the S's own origin sits relative to the P's
    minx, miny = min(0, ox), min(0, oy)
    W = max(p.width, ox + s.width) - minx
    H = max(p.height, oy + s.height) - miny
    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    layer.paste(Image.new("RGBA", p.size, P_COLOUR + (255,)), (-minx, -miny), p)
    layer.paste(Image.new("RGBA", s.size, S_COLOUR + (255,)), (ox - minx, oy - miny), s)
    return layer


def make(out_dir):
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    bg = Image.new("RGBA", (SIZE, SIZE))
    d = ImageDraw.Draw(bg)
    for y in range(SIZE):
        t = y / (SIZE - 1)
        d.line([(0, y), (SIZE, y)], fill=tuple(int(BG_TOP[i] + (BG_BOTTOM[i] - BG_TOP[i]) * t) for i in range(3)) + (255,))
    mask = Image.new("L", (SIZE, SIZE), 0)
    ImageDraw.Draw(mask).rounded_rectangle([40, 40, SIZE - 40, SIZE - 40], radius=210, fill=255)    # the macOS icon grid leaves a margin
    icon = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    icon.paste(bg, (0, 0), mask)

    letters = build()
    scale = min(SIZE * 0.62 / letters.width, SIZE * 0.62 / letters.height)
    letters = letters.resize((int(letters.width * scale), int(letters.height * scale)), Image.Resampling.LANCZOS)
    pos = ((SIZE - letters.width) // 2, (SIZE - letters.height) // 2)
    shadow = Image.new("RGBA", icon.size, (0, 0, 0, 0))
    shadow.paste((0, 0, 0, 150), (pos[0] + 10, pos[1] + 14), letters.split()[3])
    icon = Image.alpha_composite(icon, shadow.filter(ImageFilter.GaussianBlur(14)))
    icon.alpha_composite(letters, pos)
    icon = Image.composite(icon, Image.new("RGBA", icon.size, (0, 0, 0, 0)), ImageChops.lighter(mask, icon.split()[3]))
    png = out / "icon_1024.png"
    icon.save(png)

    iconset = out / "icon.iconset"
    iconset.mkdir(exist_ok=True)
    for base in (16, 32, 128, 256, 512):
        for factor in (1, 2):
            px = base * factor
            icon.resize((px, px), Image.Resampling.LANCZOS).save(iconset / f"icon_{base}x{base}{'@2x' if factor == 2 else ''}.png")
    subprocess.run(["iconutil", "-c", "icns", str(iconset), "-o", str(out / "icon.icns")], check=True)
    return png, out / "icon.icns"


def data_uri(img, px):
    buf = io.BytesIO()
    img.resize((px, px), Image.Resampling.LANCZOS).save(buf, "PNG", optimize=True)
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


def favicon_block(png):
    """<link> tags with the icon embedded (no extra file to serve). The 40 px margin of the app icon is cropped so the letters stay big at 16-32 px."""
    full = Image.open(png).convert("RGBA")
    tight = full.crop((40, 40, SIZE - 40, SIZE - 40))
    apple = Image.new("RGBA", tight.size, BG_TOP + (255,))     # iOS wants a filled square and rounds the corners itself
    ad = ImageDraw.Draw(apple)
    for y in range(apple.height):                              # same gradient as the icon, so the cropped-off corners are filled with it
        t = y / (apple.height - 1)
        ad.line([(0, y), (apple.width, y)], fill=tuple(int(BG_TOP[i] + (BG_BOTTOM[i] - BG_TOP[i]) * t) for i in range(3)) + (255,))
    apple.alpha_composite(tight)
    return ("<!-- favicon:start (written by scripts/make_icon.py --favicon) -->\n"
            f'<link rel="icon" type="image/png" sizes="32x32" href="{data_uri(tight, 32)}">\n'
            f'<link rel="icon" type="image/png" sizes="64x64" href="{data_uri(tight, 64)}">\n'
            f'<link rel="apple-touch-icon" sizes="180x180" href="{data_uri(apple, 180)}">\n'
            "<!-- favicon:end -->")


def write_favicon(page, png):
    path = Path(page)
    html = path.read_text(encoding="utf-8")
    block = favicon_block(png)
    pat = re.compile(r"<!-- favicon:start.*?<!-- favicon:end -->", re.S)
    if pat.search(html):
        html = pat.sub(lambda m: block, html, count=1)
    else:
        html = html.replace("</head>", block + "\n</head>", 1)     # first run: add the block just before </head>
    path.write_text(html, encoding="utf-8")


if __name__ == "__main__":
    args = sys.argv[1:]
    page = args[args.index("--favicon") + 1] if "--favicon" in args else None
    rest = [a for i, a in enumerate(args) if a != "--favicon" and (i == 0 or args[i - 1] != "--favicon")]
    folder = rest[0] if rest else tempfile.mkdtemp(prefix="studio_icon_")
    png, icns = make(folder)
    print(f"wrote {png}\nwrote {icns}")
    if page:
        write_favicon(page, png)
        print(f"wrote favicon tags into {page}")
