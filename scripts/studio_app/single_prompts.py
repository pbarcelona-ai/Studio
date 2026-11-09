"""studio_app.single_prompts"""
import csv
import json
import re
import shutil
import subprocess
import sys
from bookkit import NEG_TAIL, SLUG_RE, llm_json
import character_tokens
import prompt_guides
import model_advisor
from layout import project_dir as pdir     # a name -> its folder (books/, characters/ or prompts/); see layout.py

from .common import PlanError, num
from .config import GPUS, I2V_MODELS, IMAGE_MODELS, MODEL_DEFAULTS, REF_IMAGE_MODELS, ROOT, VIDEO_MODELS
from .gpus import check_models, gpu_blocker, local_gpu_label
from .projects import is_promptset, load_global_params, read_csv_rows
from .steps import chunks, engine_args, make_runner


# ---------------------------------------------------------------- single prompts (text to video / text to image)
VIDEO_COLS = ["chapter", "shot", "prompt", "negative", "width", "height", "frames", "steps", "guidance", "seed"]
IMAGE_COLS = ["chapter", "shot", "prompt", "negative", "width", "height", "steps", "guidance", "seed"]


def snap(value, multiple, lo, hi):
    """Round a size/frame count to what the model accepts and keep it in range."""
    v = int(round(value / multiple)) * multiple
    return max(lo, min(hi, v))


def prompt_set_slug(opt, create_ok):
    slug = (opt.get("set") or "").strip().lower()
    if not SLUG_RE.match(slug):
        raise PlanError("name the prompt set: 2-40 lowercase letters, digits or underscores")
    d = pdir(slug, "prompts")
    if d.exists() and not is_promptset(slug):
        raise PlanError(f"{slug} is a book, not a prompt set; pick another name")
    return slug


def prompt_rows(opt, slug, kind, model, first_row):
    prompts = [ln.strip() for ln in str(opt.get("prompts", "")).splitlines() if ln.strip()]
    if not prompts:
        raise PlanError("type at least one prompt (one per line)")
    if len(prompts) > 100 or any(len(p) > 2000 for p in prompts):
        raise PlanError("up to 100 prompts at a time, 2000 characters each")
    o = opt.get("opts", {}) or {}
    variations = num(o, "variations", 1, int, 1, 8)
    w = num(o, "width", 0, int, 0, 4096) or None
    h = num(o, "height", 0, int, 0, 4096) or None
    frames = num(o, "frames", 0, int, 0, 400) or None
    steps = num(o, "steps", 0, int, 0, 150) or None
    guidance = o.get("guidance")
    guidance = None if guidance in (None, "") else num(o, "guidance", 0, float, 0, 30)
    seed = o.get("seed")
    seed = None if seed in (None, "") else num(o, "seed", 0, int, 0, 2**31 - 1)
    negative = str(o.get("negative") or "").strip()[:500]
    if kind == "video":
        if model == "ltx_video":
            w = snap(w, 32, 256, 1280) if w else None; h = snap(h, 32, 256, 1280) if h else None
            frames = snap(frames - 1, 8, 8, 160) + 1 if frames else None          # 8*k+1
        elif model in ("wan", "wan22_t2v_a14b", "wan22_t2v_a14b_lora", "wan22_t2v_a14b_lightning"):
            w = snap(w, 16, 256, 1280) if w else None; h = snap(h, 16, 256, 1280) if h else None
            frames = snap(frames - 1, 4, 4, 120) + 1 if frames else None          # 4*k+1
        elif model == "wan22_ti2v_5b":
            w = snap(w, 32, 256, 1280) if w else None; h = snap(h, 32, 256, 1280) if h else None
            frames = snap(frames - 1, 4, 4, 120) + 1 if frames else None
        elif model in ("hunyuan_video", "hunyuan_video_lora"):
            w = snap(w, 16, 256, 1280) if w else None; h = snap(h, 16, 256, 1280) if h else None
            frames = snap(frames - 1, 4, 4, 128) + 1 if frames else None
            negative = ""                                                           # HunyuanVideo has no negative prompt
        else:                                                                       # cogvideox (2B and 5B): fixed size and length
            w = h = frames = None
    elif model == "tpu_mage_flow":                    # the author's runner makes square 512, 768 or 1024 images in 4 steps
        size = max(w or 0, h or 0)
        w = h = min((512, 768, 1024), key=lambda r: abs(r - size)) if size else None
        steps = guidance = None
        negative = ""
    elif model == "tpu_flux_jax":
        w = snap(w, 16, 256, 1024) if w else None; h = snap(h, 16, 256, 1024) if h else None
        negative = ""
    else:
        w = snap(w, 16, 256, 1536) if w else None; h = snap(h, 16, 256, 1536) if h else None
    rows, n = [], first_row
    for p in prompts:
        for v in range(variations):
            row = {"chapter": slug, "shot": n, "prompt": p, "negative": negative, "width": w or "", "height": h or "",
                   "steps": steps or "", "guidance": "" if guidance is None else guidance,
                   "seed": "" if seed is None else seed + v}
            if kind == "video":
                row["frames"] = frames or ""
            rows.append(row)
            n += 1
    return rows


def append_rows(path, cols, new_rows):
    old = read_csv_rows(path)
    fields = list(cols) + [c for r in old for c in r if c not in cols]
    fields = list(dict.fromkeys(fields))
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        w.writerows(old + new_rows)


WAN_HEADS = {"wan": 12, "wan22_ti2v_5b": 24, "wan22_t2v_a14b": 40, "wan22_t2v_a14b_lora": 40, "wan22_t2v_a14b_lightning": 40, "hunyuan_video": 24, "hunyuan_video_lora": 24}      # attention heads per model
WAN_ATTN_CAP_GIB = {"wan": 2.5, "wan22_ti2v_5b": 2.5, "wan22_t2v_a14b": 1.8, "wan22_t2v_a14b_lora": 1.8, "wan22_t2v_a14b_lightning": 1.8, "hunyuan_video": 2.5, "hunyuan_video_lora": 2.5}   # what is left on a 14.5 GiB T4 next to the weights


def wan_t4_check(gpu, w, h, frames, model="wan"):
    """Wan on a T4 runs plain attention in fp32: one matrix is 4 x heads x tokens^2 bytes (the 14B model has 40 heads: 512x288x33 asked for 4.01 GiB
    with 2.2 GiB free and crashed). Refuse sizes that cannot fit."""
    if "T4" not in gpu:
        return
    d = MODEL_DEFAULTS[model]
    w, h, frames = w or d["width"], h or d["height"], frames or d["frames"]
    div = 32 if model == "wan22_ti2v_5b" else 16                  # the 5B model's VAE is 2x more compact per side
    per_token2 = 4 * WAN_HEADS[model]
    tokens = ((frames - 1) // 4 + 1) * (h // div) * (w // div)
    need = per_token2 * tokens * tokens / 2**30
    cap = WAN_ATTN_CAP_GIB[model]
    if need > cap:
        limit = int((cap * 2**30 / per_token2) ** 0.5)
        raise PlanError(f"{model} at {w}x{h} with {frames} frames needs about {need:.1f} GiB for one attention matrix on a T4 (only about {cap:.1f} GiB is free next to the model); "
                        f"keep ((frames-1)//4+1) x (height/{div}) x (width/{div}) under about {limit:,} (now {tokens:,}), for example "
                        f"{'448x256 with 25 frames' if WAN_HEADS[model] == 40 else '480x272 with 33 frames' if model.startswith('hunyuan') else '512x288 with 33 frames'}, or use an L4/A100")


# Image models whose attention matrix can overflow a T4: (heads, images per pass, GiB free next to the weights, text tokens). The T4 runs plain fp32 attention:
# one matrix is 4 x heads x batch x tokens^2 bytes (SD 3.5 Large at 1024x1024 with guidance asked for 5.55 GiB and crashed).
IMAGE_ATTN = {"sd35_large": (38, 2, 3.0, 333), "sd35_large_turbo": (38, 1, 3.0, 333)}


def image_t4_check(gpu, w, h, model):
    if "T4" not in gpu or model not in IMAGE_ATTN:
        return
    d = MODEL_DEFAULTS[model]
    w, h = w or d["width"], h or d["height"]
    heads, batch, cap, text = IMAGE_ATTN[model]
    tokens = (w // 16) * (h // 16) + text
    need = 4 * heads * batch * tokens * tokens / 2**30
    if need > cap:
        limit = int((cap * 2**30 / (4 * heads * batch)) ** 0.5) - text
        side = int((limit ** 0.5) * 16)
        raise PlanError(f"{model} at {w}x{h} needs about {need:.1f} GiB for one attention matrix on a T4 (only about {cap:.1f} GiB is free next to the model); "
                        f"keep it to about {side}x{side} or smaller, or use an L4/A100")


CHARACTER_REF_NAME = "ref-character.png"
SAME_PERSON = "The same person as in the reference picture, same face and features: "


def character_reference(opt, model, service):
    """The picture that steers this run on the Characters tab, or None. Only a model that takes pictures, on a service that uploads them."""
    ref = (opt.get("opts") or {}).get("reference") or {}
    series, name = str(ref.get("series") or ""), str(ref.get("name") or "")
    if not series or not name or model not in REF_IMAGE_MODELS or service not in ("kaggle", "computer"):
        return None
    if not SLUG_RE.match(series):
        raise PlanError("bad series name")
    return character_tokens.first_reference(series, name)


def save_small_picture(src, dst, side=448):
    """A copy of a reference picture, at most side pixels long. A plain copy if Pillow is missing or cannot read it; the notebook shrinks it then."""
    try:
        from PIL import Image
        img = Image.open(src).convert("RGB")
        img.thumbnail((side, side))
        img.save(dst, "PNG")
    except Exception:
        shutil.copyfile(src, dst)


def open_folder(series, name):
    """Open the character's reference folder in Finder or the file manager (it is made if needed). Returns its path from the repository root."""
    if not SLUG_RE.match(str(series)) or not str(name).strip():
        raise PlanError("pick a series and a character first")
    folder = character_tokens.ensure_reference_dir(series, name)
    opener = "open" if sys.platform == "darwin" else "xdg-open"
    if not shutil.which(opener):
        raise PlanError(f"cannot open folders here; it is at {folder}")
    subprocess.run([opener, str(folder)], check=True, timeout=10)
    return str(folder.relative_to(ROOT))


FACE_CHECK_FILE = "face_check.json"


def face_check_step(opt):
    """The job step for scripts/face_check.py."""
    slug, series = str(opt.get("project") or ""), str(opt.get("series") or "")
    if not SLUG_RE.match(slug) or not pdir(slug).is_dir():
        raise PlanError("pick a book first")
    if not SLUG_RE.match(series):
        raise PlanError("choose the character series whose pictures to compare with")
    start, end = num(opt, "start", 1, int, 1), num(opt, "end", 10**6, int, 1)
    look = str(opt.get("look") or "")
    return {"label": f"Check faces, shots {start}-{end}", "env": {},
            "argv": ["uv", "run", "--with", "opencv-python-headless", "--with", "numpy", "python", "face_check.py", slug, "--series", series, "--start", str(start), "--end", str(end)]
                    + (["--look", look] if look in model_advisor.LOOKS else [])}


def prompt_plan(opt, commit):
    slug = prompt_set_slug(opt, True)
    kind = opt.get("kind")
    if kind not in ("video", "image"):
        raise PlanError("choose video or image")
    model = opt.get("model")
    if model not in (VIDEO_MODELS if kind == "video" else IMAGE_MODELS):
        raise PlanError("unknown model for that kind")
    if model in I2V_MODELS:
        raise PlanError(f"{model} animates a book's keyframes; for single prompts use {model.removesuffix('_i2v')}")
    service = opt.get("service")
    if service not in GPUS:
        raise PlanError("choose where the models run: Kaggle, Colab, Hugging Face or this computer")
    gpu = opt.get("gpu")
    if gpu not in [g for g, _ in GPUS[service]]:
        raise PlanError(f"gpu {gpu!r} is not an option for {service}")
    if gpu_blocker(service, gpu):
        raise PlanError(gpu_blocker(service, gpu))
    user = (opt.get("kaggle_user") or "").strip()
    if service == "kaggle" and not re.fullmatch(r"[A-Za-z0-9_-]{2,40}", user):
        raise PlanError("enter your Kaggle username (letters, digits, - and _)")
    check_models(service, gpu, [model])
    batch = num(opt, "batch", 0, int, 0, 100000)
    d = pdir(slug, "prompts")
    csv_name, cols = ("all_shots.csv", VIDEO_COLS) if kind == "video" else ("all_images.csv", IMAGE_COLS)

    # Check if we should overwrite the CSV (for single image generation)
    overwrite = opt.get("opts", {}).get("overwrite", False)
    if overwrite and (d / csv_name).exists():
        (d / csv_name).unlink()

    first = len(read_csv_rows(d / csv_name)) + 1
    rows = prompt_rows(opt, slug, kind, model, first)
    look = str(opt.get("look") or "")
    if look:
        if look not in model_advisor.LOOKS:
            raise PlanError("unknown look")
        takes_neg = "negative" not in (MODEL_DEFAULTS.get(model, {}).get("locked") or []) and model not in ("hunyuan_video", "hunyuan_video_lora", "tpu_mage_flow", "tpu_flux_jax")
        for r in rows:
            r["prompt"], r["negative"] = model_advisor.apply_look(r["prompt"], r["negative"], look, takes_neg)
            r["prompt"] = r["prompt"][:2000]; r["negative"] = r["negative"][:700]
    gname = local_gpu_label() if service == "computer" else gpu      # the T4 limits below also apply to a T4 in this computer
    if model in WAN_HEADS:
        for r in rows:
            wan_t4_check(gname, int(r["width"] or 0), int(r["height"] or 0), int(r.get("frames") or 0), model)
    if kind == "image" and model in IMAGE_ATTN:
        for r in rows:
            image_t4_check(gname, int(r["width"] or 0), int(r["height"] or 0), model)
    last = first + len(rows) - 1
    ref_src = character_reference(opt, model, service) if kind == "image" else None
    if ref_src:
        cols = cols + ["refs"]
        for r in rows:
            r["refs"] = CHARACTER_REF_NAME
            r["prompt"] = f"{SAME_PERSON}{r['prompt']}"[:2000]
    if commit:
        d.mkdir(parents=True, exist_ok=True)
        (d / "promptset.json").write_text(json.dumps({"type": "prompts"}))
        append_rows(d / csv_name, cols, rows)
        if kind == "image" and "reference" in (opt.get("opts") or {}):     # the Characters tab: this run's picture only, so an old one is never uploaded
            shutil.rmtree(d / "keyframe_refs", ignore_errors=True)
        if ref_src:
            (d / "keyframe_refs").mkdir(parents=True, exist_ok=True)
            save_small_picture(ref_src, d / "keyframe_refs" / CHARACTER_REF_NAME)
    runner = make_runner(service, gpu, user, slug)
    runner_model = model if kind == "video" else f"image_{model}"
    steps = []
    for s_, e_ in chunks(first, last, batch):
        argv, env = runner(runner_model, s_, e_, csv_name)
        steps.append({"label": f"{kind} {model}: rows {s_}-{e_}", "argv": argv, "env": env})
    return steps


def expand_idea(opt):
    kind = opt.get("kind")
    if kind not in ("video", "image"):
        raise PlanError("choose video or image")
    idea = str(opt.get("idea") or "").strip()
    if not idea or len(idea) > 1000:
        raise PlanError("write a short idea (up to 1000 characters)")
    count = num(opt, "count", 3, int, 1, 4)
    args = engine_args(opt)
    engine = args[1]
    model = args[3] if len(args) > 3 else None

    # Load global parameters for the project
    project = opt.get("project", "")
    global_positives = ""
    global_negatives = ""
    if project:
        global_params = load_global_params(project)
        global_positives = global_params.get("positives", "")
        global_negatives = global_params.get("negatives", "")

    target = str(opt.get("target") or "").strip()
    if not re.fullmatch(r"[A-Za-z0-9_.-]{1,60}", target):
        target = ""
    _, words = prompt_guides.guide_for(kind, target)
    what = (f"a text-to-video model. Each prompt is one 4-6 second clip, {words}.") if kind == "video" else (
            f"a text-to-image model. Each prompt is one picture, {words}.")

    global_section = ""
    if global_positives or global_negatives:
        global_section = "\nGLOBAL PROMPT PARAMETERS (apply to ALL prompts):\n"
        if global_positives:
            global_section += f"  Always include: {global_positives}\n"
        if global_negatives:
            global_section += f"  Always avoid: {global_negatives}\n"

    prompt = (f'Idea: "{idea}"\n{global_section}\n\nWrite {count} different, vivid prompts for {what} No on-screen text, no logos, nothing '
              f'that depends on previous prompts. Reply with one JSON object: {{"prompts": ["...", ...]}} with exactly {count} strings.')

    def check(d):
        ps = d.get("prompts")
        if not isinstance(ps, list) or len(ps) != count or not all(isinstance(x, str) and len(x) > 20 for x in ps):
            raise ValueError(f"'prompts' must be a list of exactly {count} strings")

    data = llm_json(prompt, prompt_guides.writer_system(kind, target), model=model, engine=engine, validate=check)

    # Append global parameters to each generated prompt
    prompts = [x.strip() for x in data["prompts"]]
    if global_positives or global_negatives:
        final_prompts = []
        for p in prompts:
            parts = [p]
            if global_positives:
                parts.append(global_positives)
            parts.append(NEG_TAIL)      # style-free; negatives are not added: words in the prompt ask the model FOR them
            final_prompts.append(", ".join(parts))
        return final_prompts
    return prompts
