"""Pictures of the results: thumbnails, depth maps, ratings, the Compare wall, the showcase and the prompt library."""
import re
import threading
from bookkit import read_json, write_json
from layout import project_dir as pdir     # a name -> its folder (books/, characters/ or prompts/); see layout.py

from .common import PlanError
from .config import PROJECTS, ROOT
from .projects import read_csv_rows


# ---------------------------------------------------------------- Compare wall, showcase art and the prompt library
REG_LANES = ("regtest_a", "regtest_b", "regtest_i")        # the two lanes of scripts/regress_kaggle.py, and regtest_i: results collected by hand (the regression never writes there)
RATINGS_FILE = PROJECTS / "regression" / "regtest_ratings.json"
ZOMBIE_PROMPT = "a young woman running towards the camera, zombies are chasing her down a city street. not blurry, no cartoon."   # the built-in prompt of the first regression


THUMB_PX = 480


def load_rgb(src):
    """A picture, or one frame from a clip, as an RGB PIL image."""
    from PIL import Image
    if src.suffix.lower() == ".mp4":
        import cv2
        cap = cv2.VideoCapture(str(src))
        total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 1)
        cap.set(cv2.CAP_PROP_POS_FRAMES, max(0, total // 3))
        ok, frame = cap.read()
        cap.release()
        if not ok:
            raise OSError("cannot read a frame")
        return Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
    return Image.open(src).convert("RGB")


def make_thumb(src, dest):
    """A small JPEG of a picture, or of a frame from a clip, so the grids do not load the full files."""
    im = load_rgb(src)
    im.thumbnail((THUMB_PX, THUMB_PX))
    dest.parent.mkdir(exist_ok=True)
    tmp = dest.with_suffix(".tmp")
    im.save(tmp, "JPEG", quality=82)
    tmp.replace(dest)


DEPTH_MODEL = "depth-anything/Depth-Anything-V2-Small-hf"      # Apache-2.0, about 100 MB; downloaded once on first use
_DEPTH: dict = {}
DEPTH_LOCK = threading.Lock()


def make_depth(src, dest):
    """A grey depth map (white = near) for the Studio's 3D view, made on this computer by Depth Anything V2 Small."""
    import numpy as np
    from PIL import Image
    im = load_rgb(src)
    im.thumbnail((1024, 1024))
    with DEPTH_LOCK:                                          # one at a time: the model is loaded once and shared
        if "pipe" not in _DEPTH:
            from transformers import pipeline
            _DEPTH["pipe"] = pipeline("depth-estimation", model=DEPTH_MODEL, device="cpu")
        depth = _DEPTH["pipe"](im)["depth"]
    arr = np.asarray(depth.resize(im.size), dtype="float32")
    lo, hi = np.percentile(arr, 1), np.percentile(arr, 99)
    arr = np.clip((arr - lo) / max(hi - lo, 1e-6), 0, 1)
    dest.parent.mkdir(exist_ok=True)
    tmp = dest.with_suffix(".tmp")
    Image.fromarray((arr * 255).astype("uint8")).save(tmp, "PNG")
    tmp.replace(dest)


def load_ratings():
    return read_json(RATINGS_FILE, {}) if RATINGS_FILE.exists() else {}


def save_rating(key, stars, keep):
    """Remember your stars (0-5) and Keep tick for one regression result; the key is "<lane>/<path under it>"."""
    if not re.fullmatch(r"regtest_[abi]/[A-Za-z0-9_./-]+", str(key)) or ".." in str(key):
        raise PlanError("bad result name")
    try:
        stars = max(0, min(5, int(stars)))
    except (TypeError, ValueError):
        raise PlanError("stars must be a number from 0 to 5") from None
    ratings = load_ratings()
    ratings[key] = {"stars": stars, "keep": bool(keep)}
    write_json(RATINGS_FILE, ratings)
    return ratings[key]


def regression_minutes():
    """{(model, prompt text): minutes} from the regression reports (the zombie report has no prompt field)."""
    out = {}
    for name in ("regression_kaggle_report.zombie.json", "regression_kaggle_report.json"):
        rep = read_json(ROOT / name, {}) if (ROOT / name).exists() else {}
        for model, v in rep.items():
            if isinstance(v, dict) and v.get("result") == "PASS":
                out[(model, " ".join(str(v.get("prompt", ZOMBIE_PROMPT)).split()))] = v.get("minutes")
    return out


def compare_data():
    """Every regression picture and clip, grouped by the prompt that made it, with your ratings: {"prompts": [{"text", "items": [...]}]}."""
    ratings, minutes, groups = load_ratings(), regression_minutes(), {}
    for lane in REG_LANES:
        d = pdir(lane)
        if not d.is_dir():
            continue
        csvs = {n: read_csv_rows(d / n) for n in ("all_images.csv", "all_shots.csv")}
        for sub, pattern, kind, csv_name in (("images", "*/image-*.png", "image", "all_images.csv"), ("videos", "*/shot-*.mp4", "video", "all_shots.csv")):
            for f in (d / sub).glob(pattern) if (d / sub).exists() else []:
                n = int(re.search(r"(\d+)", f.stem).group(1))
                rows = csvs[csv_name]
                text = " ".join((rows[n - 1].get("prompt") or "").split()) if 0 < n <= len(rows) else ""
                if not text:
                    continue
                key = f"{lane}/{f.relative_to(d).as_posix()}"
                r = ratings.get(key, {})
                groups.setdefault(text, []).append({"model": f.parent.name, "kind": kind, "file": key, "row": n, "size": f.stat().st_size, "mtime": f.stat().st_mtime,
                                                    "stars": r.get("stars", 0), "keep": bool(r.get("keep")), "minutes": minutes.get((f.parent.name, text))})
    out = []
    for text, items in groups.items():
        latest = {}
        for it in sorted(items, key=lambda x: x["mtime"]):         # one result per model: the newest
            latest[(it["model"], it["kind"])] = it
        items = sorted(latest.values(), key=lambda x: (x["kind"], x["model"]))
        out.append({"text": text, "newest": max(i["mtime"] for i in items), "items": items})
    out.sort(key=lambda g: -g["newest"])
    return {"prompts": out}


def showcase():
    """Pictures and one clip made by your own models, used as the Studio's own artwork: {"hero": file or None, "art": [files]}.
    Only results you rated 4 stars or more, plus results of the built-in street-chase prompt, are used: unfiltered models can make
    unsuitable pictures, and nothing should reach the page header without you choosing it."""
    items = []
    for g in compare_data()["prompts"]:
        for it in g["items"]:
            if it["stars"] >= 4 or g["text"] == ZOMBIE_PROMPT:
                items.append(it)
    vids = sorted((i for i in items if i["kind"] == "video" and i["size"] > 60_000), key=lambda i: (-i["stars"], -i["mtime"]))
    imgs = sorted((i for i in items if i["kind"] == "image" and i["size"] > 150_000), key=lambda i: (-i["stars"], -i["mtime"]))
    seen, art = set(), []
    for i in imgs:                                            # at most one picture per model, so the artwork is varied
        if i["model"] not in seen:
            seen.add(i["model"]); art.append(i["file"])
    return {"hero": vids[0]["file"] if vids else None, "art": art[:12]}


def library():
    """The prompt library, each template with a sample from your results when the same prompt was run."""
    import templates
    results = {}
    for g in compare_data()["prompts"]:
        results[g["text"]] = sorted(g["items"], key=lambda i: (-i["stars"], i["kind"] != "video", -i["size"]))
    out = []
    for t in templates.TEMPLATES:
        items = results.get(" ".join(t["prompt"].split()), [])
        want = [i for i in items if i["kind"] == t["kind"]] or items
        out.append({**t, "sample": ({"file": want[0]["file"], "kind": want[0]["kind"], "model": want[0]["model"]} if want else None)})
    return {"templates": out}
