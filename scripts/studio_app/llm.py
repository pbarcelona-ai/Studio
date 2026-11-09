"""studio_app.llm"""
import csv
import io
import json
import os
import re
import shutil
import subprocess
import time
from pathlib import Path
from bookkit import NEG_TAIL, continuity_file, LOCAL_LLM_URL, SLUG_RE, hf_json, llm_json, local_chat
import prompt_guides
from layout import project_dir as pdir     # a name -> its folder (books/, characters/ or prompts/); see layout.py

from .common import PlanError
from .config import MODEL_RE
from .log import get_logger
from .gallery import load_rgb
from .projects import load_global_params, read_csv_rows
from .steps import ENGINES, HF_VISION_MODELS, engine_args


log = get_logger("llm")
_LOCAL_CACHE = {"at": 0.0, "value": None}


def local_llm_status(force=False):
    """Can this computer run the prompt writer on a local language model? {"ready", "reason", "url", "models"}. The checkbox in the Studio is greyed out
    (with this reason) until the computer qualifies: Apple Silicon or an NVIDIA GPU, 16 GB of memory or more, and a model server answering on
    LOCAL_LLM_URL (Ollama, LM Studio or llama.cpp). STUDIO_LOCAL_LLM=1 in the environment skips the hardware checks. Cached for 30 seconds."""
    if not force and _LOCAL_CACHE["value"] is not None and time.time() - _LOCAL_CACHE["at"] < 30:
        return _LOCAL_CACHE["value"]
    import platform
    reasons, models = [], []
    try:
        if platform.system() == "Darwin":
            gb = int(subprocess.run(["sysctl", "-n", "hw.memsize"], capture_output=True, text=True, timeout=3).stdout.strip() or 0) / 2**30
        else:
            gb = os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES") / 2**30
    except (OSError, ValueError, subprocess.SubprocessError):
        gb = 0
    if os.environ.get("STUDIO_LOCAL_LLM") != "1":
        if gb and gb < 16:
            reasons.append(f"this computer has {gb:.0f} GB of memory and a useful language model needs 16 GB or more")
        if platform.system() == "Darwin" and platform.machine() != "arm64":
            reasons.append("this is an Intel Mac; local models need Apple Silicon (M-series)")
        elif platform.system() != "Darwin" and not shutil.which("nvidia-smi"):
            reasons.append("no NVIDIA GPU was found")
    if not reasons:                                           # only look for a model server on a computer that could use one
        try:
            import urllib.request
            with urllib.request.urlopen(LOCAL_LLM_URL.rsplit("/chat/completions", 1)[0] + "/models", timeout=1.5) as r:
                models = [m.get("id") for m in json.loads(r.read()).get("data", []) if m.get("id")]
            if not models:
                reasons.append("the local model server has no models yet (for Ollama: ollama pull <model>)")
        except (OSError, ValueError, AttributeError):
            reasons.append(f"no local model server answered at {LOCAL_LLM_URL.rsplit('/chat/completions', 1)[0]} (install Ollama or LM Studio and start it)")
    value = {"ready": not reasons, "reason": "; ".join(reasons), "url": LOCAL_LLM_URL, "models": models, "memory_gb": round(gb)}
    _LOCAL_CACHE.update(at=time.time(), value=value)
    return value


def result_file(file):
    """Resolve "<project>/<path under it>" (as the Compare tab names a result) to a real picture or clip inside projects/<project>/."""
    parts = str(file or "").split("/", 1)
    if len(parts) != 2 or not SLUG_RE.match(parts[0]):
        raise PlanError("bad file name")
    base = pdir(parts[0]).resolve()
    target = (base / parts[1]).resolve()
    if base not in target.parents or target.suffix.lower() not in (".png", ".jpg", ".mp4") or not target.is_file():
        raise PlanError("that file was not found")
    return target


def image_data_url(path, px=1024):
    """The picture (or one frame of a clip) as a small JPEG data URL, to send to a vision model."""
    import base64
    im = load_rgb(path)
    im.thumbnail((px, px))
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=85)
    return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()


def vision_model(opt):
    model = str(opt.get("claude_model") or "").strip()
    if model and not MODEL_RE.match(model):
        raise PlanError("model name may only use letters, digits and . _ : / [ ] -")
    if (opt.get("engine") or "claude") == "hf":
        return model or HF_VISION_MODELS[0]
    return model                                              # claude / codex: blank = the tool's own default; local: the local server decides


def vision_json(opt, system, text, check):
    """Show one result picture (or a frame of a clip) to a model and get a JSON reply. Engines: claude / fcc-claude (the Read tool on a private copy),
    codex / fcc-codex (-i), hf (Hugging Face vision model) and local (a vision model on this computer's model server)."""
    engine = opt.get("engine") or "claude"
    if engine not in ENGINES:
        raise PlanError("unknown engine")
    path, model = result_file(opt.get("file")), vision_model(opt)
    if engine in ("hf", "local"):
        messages = [{"role": "system", "content": system},
                    {"role": "user", "content": [{"type": "text", "text": text}, {"type": "image_url", "image_url": {"url": image_data_url(path)}}]}]
        return hf_json(messages, model, check, chat=local_chat if engine == "local" else None)
    import tempfile
    fd, jpeg = tempfile.mkstemp(suffix=".jpg")
    os.close(fd)
    try:
        im = load_rgb(path)
        im.thumbnail((1024, 1024))
        im.save(jpeg, "JPEG", quality=85)
        return llm_json(text, system, model or None, engine, check, image=jpeg)
    finally:
        Path(jpeg).unlink(missing_ok=True)


def describe_image(opt):
    """Look at a picture and write a prompt for it: kind "video" = a prompt that brings it to life (image-to-video), "image" = a prompt that recreates it."""
    kind = opt.get("kind") if opt.get("kind") in ("video", "image") else "video"
    target = str(opt.get("target") or "").strip()
    if not re.fullmatch(r"[A-Za-z0-9_.-]{1,60}", target):
        target = ""
    rules, words = prompt_guides.guide_for(kind, target)
    extra = str(opt.get("note") or "").strip()[:400]
    task = ("Write ONE prompt for an image-to-video model that brings this exact picture to life: keep the subject, setting and look you can see, "
            f"then add natural motion and a camera move. {words}.") if kind == "video" else (
            f"Write ONE prompt for a text-to-image model that would recreate this picture closely. {words}.")
    text = f"{task}\n\nRules: {rules}" + (f"\n\nAlso follow this instruction from the user: {extra}" if extra else "") + '\n\nReply with {"prompt": "..."}'

    def check(d):
        if not isinstance(d.get("prompt"), str) or len(d["prompt"]) < 20:
            raise ValueError("'prompt' must be a string of at least 20 characters")
    return {"prompt": vision_json(opt, prompt_guides.writer_system(kind, target), text, check)["prompt"].strip()}


def review_result(opt):
    """Compare a result with the prompt that made it: a score from 1 to 10, a one-line summary and up to three problems."""
    prompt = " ".join(str(opt.get("prompt") or "").split())[:1500]
    if not prompt:
        raise PlanError("no prompt to compare with")
    text = (f'This picture (or frame of a clip) was made from this prompt:\n"{prompt}"\n\nJudge how well it matches the prompt and how good it looks: '
            "anatomy and faces, hands, objects, text artefacts, blur, composition, lighting. Score 1-10 (10 = excellent, 5 = usable but flawed, 1 = unusable). "
            'Reply with {"score": 7, "summary": "one sentence", "problems": ["up to three short items; empty if none"]}')

    def check(d):
        sc = d.get("score")
        if isinstance(sc, str) and sc.strip().isdigit():
            d["score"] = sc = int(sc)
        if not isinstance(sc, (int, float)) or not 1 <= sc <= 10 or not isinstance(d.get("summary"), str):
            raise ValueError("need a numeric 'score' from 1 to 10 and a 'summary' string")
        d["problems"] = [str(x)[:160] for x in (d.get("problems") or [])][:3] if isinstance(d.get("problems"), list) else []
    d = vision_json(opt, prompt_guides.review_system(), text, check)
    return {"score": round(float(d["score"])), "summary": d["summary"].strip(), "problems": d["problems"]}


def clip_prompt(slug, row):
    """Get the original prompt for a specific clip/row in a project."""
    if not SLUG_RE.match(slug):
        raise PlanError("bad project name")
    d = pdir(slug)
    if not d.is_dir():
        raise PlanError("project not found")

    # Try to find the prompt from all_shots.csv or all_chapters.csv
    for csv_name in ("all_shots.csv", "all_chapters.csv", "all_images.csv"):
        rows = read_csv_rows(d / csv_name)
        if 0 < row <= len(rows):
            return {"prompt": rows[row - 1].get("prompt", "")}
    return {"prompt": ""}


def enhance_prompt(opt):
    """Enhance a prompt based on user instruction."""
    project = opt.get("project", "")
    row = opt.get("row", 0)
    original_prompt = opt.get("original_prompt", "")
    instruction = opt.get("instruction", "").strip()
    preview_only = opt.get("preview_only", False)

    if not SLUG_RE.match(project):
        raise PlanError("bad project name")
    if not original_prompt:
        raise PlanError("no original prompt provided")
    if not instruction:
        raise PlanError("no enhancement instruction provided")

    d = pdir(project)
    if not d.is_dir():
        raise PlanError("project not found")

    # Load global parameters for the project
    global_params = load_global_params(project)
    global_positives = global_params.get("positives", "")
    global_negatives = global_params.get("negatives", "")

    # The continuity book, for context
    continuity = {}
    book_path = continuity_file(d)
    if book_path.exists():
        try:
            continuity = json.loads(book_path.read_text())
        except (OSError, ValueError) as e:
            log.warning("continuity book %s is unreadable: %s", book_path.name, e)

    # Get the engine and model
    args = engine_args(opt)
    engine = args[1]
    model = args[3] if len(args) > 3 else None

    # Build the enhancement prompt
    book_context = ""
    if continuity:
        style = continuity.get("style", {})
        visual = style.get("visual", "")
        if visual:
            book_context += f"\nVisual style: {visual}"
        characters = continuity.get("characters", {})
        if characters:
            char_desc = ", ".join(f"{k}: {v.get('visual_token', '')}" for k, v in characters.items() if v.get('visual_token'))
            book_context += f"\nCharacters: {char_desc}"

    # Include global parameters in the enhancement prompt
    global_section = ""
    if global_positives or global_negatives:
        global_section = "\nGLOBAL PROMPT PARAMETERS (must be preserved in the enhanced prompt):\n"
        if global_positives:
            global_section += f"  Always include: {global_positives}\n"
        if global_negatives:
            global_section += f"  Always avoid: {global_negatives}\n"

    preview_text = "Preview only - do NOT save the updated prompt, just show what it would look like." if preview_only else "Provide the updated prompt ready to use."

    prompt = (f'Original prompt:\n{original_prompt}\n\n'
              f'Continuity book:{book_context}\n'
              f'{global_section}\n'
              f'User instruction: {instruction}\n\n'
              f'Rewrite the prompt incorporating the instruction. Keep the same format and length. '
              f'{preview_text} Reply with JSON: {{"updated_prompt": "...", "feedback": "..."}}')

    def check(d):
        if "updated_prompt" not in d or not isinstance(d["updated_prompt"], str) or len(d["updated_prompt"]) < 10:
            raise ValueError("missing or invalid updated_prompt")

    data = llm_json(prompt, "You are a prompt engineer enhancing prompts for video/image generation models. "
                        "Reply with a single JSON object and nothing else.",
                    model=model, engine=engine, validate=check)

    updated_prompt = data.get("updated_prompt", original_prompt)

    # Ensure global parameters are included in the updated prompt
    if global_positives and global_positives not in updated_prompt:
        updated_prompt = updated_prompt + ", " + global_positives
    # Add the style-free tail if not present; negatives are not added: words in the prompt ask the model FOR them
    if NEG_TAIL not in updated_prompt:
        updated_prompt = updated_prompt + ", " + NEG_TAIL

    result = {
        "updated_prompt": updated_prompt,
        "feedback": data.get("feedback", "Updated" if not preview_only else "Preview ready")
    }

    if not preview_only:
        # Update the CSV file with the new prompt
        updated = False
        for csv_name in ("all_shots.csv", "all_chapters.csv", "all_images.csv"):
            csv_path = d / csv_name
            if csv_path.exists():
                rows = read_csv_rows(csv_path)
                if 0 < row <= len(rows):
                    rows[row - 1]["prompt"] = data["updated_prompt"]
                    # Write back the CSV
                    with open(csv_path, "w", newline="") as f:
                        if rows:
                            writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
                            writer.writeheader()
                            writer.writerows(rows)
                    updated = True
                    break
        if updated:
            result["feedback"] = "Prompt updated and saved to CSV"

    return result


def gallery(slug, limit=60):
    """Newest results of a project: clips, images and films, each with the prompt that made it."""
    d = pdir(slug)
    if not d.is_dir():
        return []
    prompts = {name: read_csv_rows(d / name) for name in ("all_shots.csv", "all_chapters.csv", "all_images.csv")}
    items = []
    for sub, pattern, kind in (("videos", "*/shot-*.mp4", "video"), ("images", "*/image-*.png", "image"), ("films", "*.mp4", "film")):
        for f in (d / sub).glob(pattern) if (d / sub).exists() else []:
            model = f.parent.name if kind != "film" else ""
            n = int(re.search(r"(\d+)", f.stem).group(1)) if kind != "film" else 0
            csv_name = "all_images.csv" if kind == "image" else "all_chapters.csv" if model.endswith("_chapters") else "all_shots.csv"
            rows = prompts.get(csv_name, [])
            text = rows[n - 1]["prompt"] if kind != "film" and 0 < n <= len(rows) else ""
            items.append({"kind": kind, "model": model, "row": n, "name": f.name, "prompt": text[:600],
                          "path": f.relative_to(d).as_posix(), "mtime": f.stat().st_mtime})
    items.sort(key=lambda x: -x["mtime"])
    return items[:limit]
