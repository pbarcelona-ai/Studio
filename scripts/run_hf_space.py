#!/usr/bin/env python3
"""Make pictures or clips for rows of a project's prompt CSV by calling a public Hugging Face Space (ZeroGPU), and save them where the Kaggle and
Colab runs save theirs, so the gallery and the rest of the Studio work unchanged.

  scripts/run_hf_space.sh MODEL START END          (PROJECT=<set> [SHOTS_CSV=all_images.csv] [HF_TOKEN=...] in the environment)

MODEL is a Studio model name (image models may be written image_<name>, as for the Kaggle script); see hf_spaces.py for the ones that have a Space.
HF_TOKEN is optional: with it the free daily ZeroGPU quota is the one of your account (about 3.5 GPU minutes for a free account), without it the quota is
shared by network address and runs out sooner. The token is read from the environment only and is never printed or written anywhere.
When the quota is used up the run stops and says so; the rows already made are kept.
"""
import re
import csv
import inspect
import os
import random
import shutil
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import hf_spaces                    # noqa: E402
import layout                       # noqa: E402


def snap(v, multiple, lo, hi):
    return max(lo, min(hi, int(round(v / multiple)) * multiple))


def num(row, key, default, cast=float):
    v = (row.get(key) or "").strip()
    return cast(v) if v else default


PIKA_ASPECTS = ("21:9", "16:9", "3:2", "4:3", "5:4", "1:1", "4:5", "3:4", "2:3", "9:16", "9:21")


def keyframe_folder(pd):
    """The keyframes to animate: KEYFRAME_MODEL's, or the newest set."""
    named = os.environ.get("KEYFRAME_MODEL", "").strip()
    if named:
        return pd / "images" / f"{named}_keyframes"
    sets = sorted((p for p in (pd / "images").glob("*_keyframes") if p.is_dir()), key=lambda p: p.stat().st_mtime) if (pd / "images").is_dir() else []
    return sets[-1] if sets else pd / "images" / "none_keyframes"


def build_call(model, spec, row):
    """(api_name, kwargs) for this model and CSV row."""
    d = spec["defaults"]
    prompt = row["prompt"]
    seed = num(row, "seed", None, int)
    base_seed = {"seed": seed if seed is not None else random.randint(0, 2**31 - 1), "randomize_seed": False}
    w = snap(num(row, "width", d.get("width", 1024), int), 32, 256, 2048) if d.get("width") else None
    h = snap(num(row, "height", d.get("height", 1024), int), 32, 256, 2048) if d.get("height") else None
    steps = num(row, "steps", d.get("steps"), int) if d.get("steps") else None
    guid = num(row, "guidance", d.get("guidance"), float) if d.get("guidance") is not None else None
    style = spec["style"]
    if style == "flux":
        kw = {"prompt": prompt, **base_seed, "width": w, "height": h, "num_inference_steps": steps}
        if guid is not None:
            kw["guidance_scale"] = guid
        return spec["api"], kw
    if style == "sd35":
        return spec["api"], {"prompt": prompt, "negative_prompt": (row.get("negative") or "").strip(), **base_seed, "width": w, "height": h,
                             "guidance_scale": guid, "num_inference_steps": steps}
    if style == "klein":
        return spec["api"], {"prompt": prompt, "input_images": [], "mode_choice": "Distilled (4 steps)", **base_seed, "width": w, "height": h,
                             "num_inference_steps": steps, "guidance_scale": guid, "prompt_upsampling": False}
    if style == "qwen_aio":
        want = (w or 1024) / (h or 1024)
        size = min(hf_spaces.QWEN_AIO_SIZES, key=lambda k: abs(hf_spaces.QWEN_AIO_SIZES[k][0] / hf_spaces.QWEN_AIO_SIZES[k][1] - want))
        return spec["api"], {"prompt": prompt, "mode": "Text to Image", "lora_adapter": "None (Base Uncensored)", "lora_strength": 1.0,
                             "custom_repo": "", "custom_file": "",
                             "aspect_ratio": size, "steps": max(4, min(40, steps or 30)), "seed": base_seed["seed"], "randomize_seed": False}
    if style == "pika":                    # Frames mode: starts from the shot's keyframe (main() finds it)
        from gradio_client import handle_file
        return spec["api"], {"prompt": prompt, "mode": "Frames", "first_image": handle_file(row["_keyframe"]), "last_image": None, "reference_files": [],
                             "resolution": d["resolution"], "aspect": row.get("aspect") if row.get("aspect") in PIKA_ASPECTS else "16:9",
                             "seconds": num(row, "seconds", d["seconds"], float), "seed": base_seed["seed"], "randomize": False}
    if style == "cogvideox":
        return spec["api"], {"prompt": prompt, "seed_value": base_seed["seed"], "scale_status": False, "rife_status": False}
    raise SystemExit(f"no call style {style!r} for {model}")


def as_path(x):
    """The file a Space returned: a path string, or a dict with 'path' / 'video'."""
    if isinstance(x, (list, tuple)):
        x = x[0]
    if isinstance(x, dict):
        for k in ("path", "video", "value", "name"):
            if x.get(k):
                return as_path(x[k])
        raise ValueError(f"no file in {x}")
    return str(x)


def main():
    if len(sys.argv) != 4:
        sys.exit(__doc__)
    model, start, end = sys.argv[1].removeprefix("image_"), int(sys.argv[2]), int(sys.argv[3])
    spec = hf_spaces.SPACES.get(model)
    if not spec:
        sys.exit(f"!! {model} has no Hugging Face Space in hf_spaces.py")
    project = os.environ.get("PROJECT") or sys.exit("!! set PROJECT to the prompt set name")
    csv_name = os.environ.get("SHOTS_CSV") or ("all_images.csv" if spec["kind"] == "image" else "all_shots.csv")
    pd = layout.find_dir(project)
    if not pd:
        sys.exit(f"!! no such project: {project}")
    rows = list(csv.DictReader(open(pd / csv_name, newline="")))
    sub = "images" if spec["kind"] == "image" else "videos"
    out = pd / sub / model
    if "chapters" in csv_name:
        out = Path(str(out) + "_chapters")
    out.mkdir(parents=True, exist_ok=True)

    from gradio_client import Client
    token = os.environ.get("HF_TOKEN", "").strip() or None
    kw = {}
    if token:
        kw["token" if "token" in inspect.signature(Client.__init__).parameters else "hf_token"] = token
    print(f"== Hugging Face Space {spec['space']} ({'with' if token else 'without'} your HF_TOKEN; free daily GPU quota applies)", flush=True)
    client = Client(spec["space"], verbose=False, **kw)

    made = failed = 0
    for i in range(start, min(end, len(rows)) + 1):
        row = rows[i - 1]
        dest = out / (f"image-{i:04d}.png" if spec["kind"] == "image" else f"shot-{i:04d}.mp4")
        if dest.exists():
            print(f"[{i}/{end}] already there: {dest.name}", flush=True)
            continue
        t0 = time.time()
        try:
            if spec["style"] == "pika":
                row = dict(row, _keyframe=str(keyframe_folder(pd) / f"image-{i:04d}.png"))
                if not Path(row["_keyframe"]).is_file():
                    raise FileNotFoundError(f"no keyframe {row['_keyframe']}: make keyframes for this row first")
            api, kwargs = build_call(model, spec, row)
            res = client.predict(**kwargs, api_name=api)
            src = as_path(res[0] if isinstance(res, (list, tuple)) else res)
            if spec["kind"] == "image":
                from PIL import Image
                Image.open(src).convert("RGB").save(dest, "PNG")
            else:
                shutil.copy(src, dest)
            made += 1
            print(f"[{i}/{end}] ok ({time.time() - t0:.0f}s) -> {dest.name}", flush=True)
        except Exception as e:      # the Space client raises many kinds of error; one failed shot must not stop the others
            msg = str(e)
            failed += 1
            print(f"[{i}/{end}] FAILED: {msg[:400]}", flush=True)
            if "quota" in msg.lower() or "zerogpu" in msg.lower():
                wait = re.search(r"Try again in ([\d:]+)", msg)
                print("!! The Hugging Face GPU quota is used up" + (f"; it comes back in {wait.group(1)}" if wait else " for now") + ". "
                      + ("A paid Hugging Face PRO account has a larger daily quota." if token else "Set HF_TOKEN to use your own account's quota.") + " Rows already made are kept.", flush=True)
                break
    print(f"✅ {len(list(out.glob('*.png' if spec['kind'] == 'image' else '*.mp4')))} files now in {out}", flush=True)
    if made == 0 and failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
