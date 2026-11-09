"""Creative direction, voice casting, new scenes, the animatic and the upscale step."""
from typing import Any
import csv
import json
import os
import re
from pathlib import Path
from bookkit import KOKORO_VOICE_RE, KOKORO_VOICES, VOICE_CAST_FILE, apply_voice_cast, read_voice_cast, voice_id, continuity_file, SLUG_RE, llm_json, read_json, write_json
import character_tokens
import layout
from layout import project_dir as pdir     # a name -> its folder (books/, characters/ or prompts/); see layout.py

from .cleanup import move_to_trash
from .common import PlanError, num
from .config import GPUS, LEGACY, LIPSYNC_MODEL, UPSCALE_MODELS, UPSCALE_SUFFIXES
from .gpus import gpu_blocker, model_blocker
from .media import media_inventory
from .projects import read_csv_rows
from .scenes import _scene_tables
from .steps import engine_args


CD_SYSTEM = ("You are a film director's creative partner helping to set the look, tone, sound and pacing of a film adapted from a book. "
             "You reply with a single JSON object and nothing else.")


def _direction_book(slug):
    if not SLUG_RE.match(slug or "") or slug in LEGACY:
        raise PlanError("pick a book made from a PDF or text")
    d = pdir(slug)
    if not d.is_dir():
        raise PlanError("pick a book first")
    return d


def creative_direction_get(opt):
    """The saved direction conversation of a book and the direction the writing steps use (continuity book field creative_direction)."""
    d = _direction_book(str(opt.get("project", "")))
    conv = read_json(d / "creative_direction.json", {})
    msgs = conv.get("messages") if isinstance(conv, dict) else None
    return {"messages": msgs if isinstance(msgs, list) else [], "direction": (read_json(continuity_file(d), {}) or {}).get("creative_direction", "")}


def creative_direction(opt):
    """One turn of the direction chat. The AI answers and, when the director is happy, also returns the finished direction; that text is
    saved in the continuity book as creative_direction, which book_write.py passes to every chapter it writes."""
    d = _direction_book(str(opt.get("project", "")))
    msgs = opt.get("messages")
    if not isinstance(msgs, list) or not msgs or len(msgs) > 60:
        raise PlanError("write something first")
    clean = []
    for m in msgs:
        if not isinstance(m, dict) or m.get("role") not in ("user", "assistant") or not isinstance(m.get("content"), str):
            raise PlanError("bad conversation")
        clean.append({"role": m["role"], "content": m["content"][:4000], **({"finalized": True} if m.get("finalized") else {})})
    if clean[-1]["role"] != "user" or not clean[-1]["content"].strip():
        raise PlanError("write something first")
    book = read_json(continuity_file(d), {}) or {}
    chars = "; ".join(f"{c.get('name')}: {c.get('token')}" for c in book.get("characters", []))[:1500]
    transcript = "\n\n".join(f"{'DIRECTOR' if m['role'] == 'user' else 'YOU'}: {m['content']}" for m in clean)
    prompt = (f"Book: {d.name}.\n" + (f"Characters: {chars}\n" if chars else "") + (f"Current direction: {book['creative_direction']}\n" if book.get("creative_direction") else "")
              + f"\nTHE CONVERSATION SO FAR:\n{transcript}\n\n"
              "Reply to the director's last message in a few sentences: react, suggest concrete choices (camera, light, colour, sound, pacing), ask at most one question. "
              "If they have given enough to write a complete direction, also fill \"direction\" with the finished direction, a paragraph of at most 120 words "
              "that a screenwriter and a prompt writer can follow; otherwise leave it as an empty string.\n"
              'Reply with one JSON object: {"reply": "...", "direction": "..."}')

    def check(data):
        if not isinstance(data.get("reply"), str) or not data["reply"].strip() or not isinstance(data.get("direction", ""), str):
            raise ValueError("'reply' must be text and 'direction' text or empty")
        if len(data["direction"]) > 1200:
            raise ValueError("'direction' must be at most 120 words")

    args = engine_args(opt)
    data = llm_json(prompt, CD_SYSTEM, model=(args[3] if len(args) > 3 else None), engine=args[1], validate=check)
    direction = data.get("direction", "").strip()
    clean.append({"role": "assistant", "content": data["reply"].strip() + (f"\n\nDIRECTION:\n{direction}" if direction else ""),
                  **({"finalized": True} if direction else {})})
    write_json(d / "creative_direction.json", {"messages": clean})
    if direction:
        book["creative_direction"] = direction
        if continuity_file(d).exists():          # only a book that already has its continuity book; never invent one here
            write_json(continuity_file(d), book)
    return {"messages": clean, "status": "direction saved: the writing steps will use it" if direction and continuity_file(d).exists()
            else ("direction ready; read the book first so it can be saved" if direction else "")}


def _write_rows(path, rows):
    fields = list(rows[0].keys())
    tmp = Path(str(path) + ".tmp")
    with open(tmp, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)
    os.replace(tmp, path)


def voice_cast(opt):
    """The voice cast of a book: every speaker in audio_shots.csv with its line count and the voice its lines use now.
    With "cast" ({speaker: Kokoro voice id, or "" to leave that speaker's lines as they are}) the cast is saved to voice_cast.json and applied to the
    audio CSVs; a character's voice overrides the narrator's for that character's lines. "move_old": the Kokoro narration files of the rows
    whose voice changed go to the Trash, so the next narration run remakes them. "series": suggest each speaker's voice from that
    character series (the Characters tab)."""
    d = _direction_book(str(opt.get("project", "")))
    if not (d / "audio_shots.csv").exists():
        raise PlanError("build the CSVs first (Build CSVs, Import tab)")
    result: dict[str, Any] = {"changed": [], "moved": 0}
    if opt.get("cast") is not None:
        cast = opt["cast"]
        if not isinstance(cast, dict) or len(cast) > 200:
            raise PlanError("cast must be {speaker: voice}")
        clean = {}
        for k, v in cast.items():
            k, v = str(k).strip()[:60], str(v or "").strip()
            if not k:
                continue
            if v and not KOKORO_VOICE_RE.match(v):
                raise PlanError(f"{v!r} is not a Kokoro voice (for example bm_george or af_bella)")
            if v:
                clean[k] = v
        write_json(d / VOICE_CAST_FILE, {"cast": clean})
        result["changed"] = apply_voice_cast(d, clean)
        if opt.get("move_old") and result["changed"]:
            rel = layout.rel(d.name)
            old = [f"{rel}/audio/kokoro/narration-{n:04d}.wav" for n in result["changed"] if (d / "audio" / "kokoro" / f"narration-{n:04d}.wav").exists()]
            result["moved"] = move_to_trash(old, "pistachio-old-voice")["moved"] if old else 0
    series = str(opt.get("series") or "")
    if series and not SLUG_RE.match(series):
        raise PlanError("bad series name")
    cast = read_voice_cast(d)
    cast_lc = {k.lower(): v for k, v in cast.items()}
    book_voice = {str(c.get("name", "")).lower(): voice_id(c.get("voice")) for c in (read_json(continuity_file(d), {}) or {}).get("characters", []) or []
                  if isinstance(c, dict)}
    speakers: dict = {}
    for r in read_csv_rows(d / "audio_shots.csv"):
        try:
            lines = json.loads(r.get("lines_json") or "[]")
        except ValueError:
            continue
        for ln in lines if isinstance(lines, list) else []:
            if not (isinstance(ln, list) and len(ln) >= 2):
                continue
            name = str(ln[0]).strip() or "NARRATOR"
            sp = speakers.setdefault(name.lower(), {"name": name, "lines": 0, "voices": {}})
            sp["lines"] += 1
            v = str(ln[2]) if len(ln) > 2 else ""
            sp["voices"][v] = sp["voices"].get(v, 0) + 1
    out = []
    for key, sp in speakers.items():
        now = max(sp["voices"], key=sp["voices"].get) if sp["voices"] else ""
        suggest = ""
        if series:
            try:
                ch = character_tokens.load_character(series, sp["name"]) if character_tokens.get_character_path(series, sp["name"]).exists() else None
            except (OSError, ValueError):
                ch = None
            suggest = voice_id((ch or {}).get("voice"))
        out.append({"name": sp["name"], "lines": sp["lines"], "voice": now, "cast": cast_lc.get(key, ""),
                    "book": book_voice.get(key, ""), "suggest": suggest})
    out.sort(key=lambda x: (x["name"].upper() != "NARRATOR", -x["lines"], x["name"].lower()))
    result.update({"speakers": out, "voices": KOKORO_VOICES})
    return result


def new_scene(opt):
    """A new shot written by the AI before or after the chapter's shots. preview_only returns the text; applying inserts one row into
    all_shots.csv (and audio_shots.csv) and renumbers the chapter's shots. Applying is refused once clips, pictures or audio exist,
    because every later row would shift and the files would no longer match their shots."""
    slug = str(opt.get("project", ""))
    d, shots, audio = _scene_tables(slug)
    desc = " ".join(str(opt.get("description") or "").split())
    if not desc or len(desc) > 1500:
        raise PlanError("describe the new scene (up to 1500 characters)")
    ch = str(opt.get("chapter", ""))
    if not ch.isdigit():
        raise PlanError("choose a chapter")
    chapter = f"{slug}-{int(ch)}"
    pos = opt.get("position", "after")
    if pos not in ("before", "after"):
        raise PlanError("position must be before or after")
    idxs = [i for i, r in enumerate(shots) if r["chapter"] == chapter]
    if not idxs:
        raise PlanError(f"chapter {ch} has no shots")
    series = str(opt.get("series") or "")
    chars = ""
    if series:
        if series not in character_tokens.list_series():
            raise PlanError("unknown character series")
        chars = character_tokens.get_all_character_tokens(series)[:1800]
    near = shots[idxs[0]] if pos == "before" else shots[idxs[-1]]
    prompt = (f"A director wants to add ONE new shot {pos} the shot below, in a film adapted from a book.\n\nTHE NEIGHBOURING SHOT: {near['prompt'][:600]}\n"
              + (f"\nCHARACTERS (keep their descriptions unchanged): {chars}\n" if chars else "")
              + f"\nWHAT THE NEW SHOT SHOULD SHOW: {desc}\n\n"
              "Write a text-to-video prompt for one continuous shot of about 4 seconds (shot size, camera movement, subject, action, setting, light; no on-screen text) "
              "at most 900 characters, and one line of narration of at most 14 words.\n"
              'Reply with one JSON object: {"prompt": "...", "narration": "..."}')

    def check(data):
        if not all(isinstance(data.get(k), str) and 10 < len(data[k].strip()) <= 1000 for k in ("prompt", "narration")):
            raise ValueError("'prompt' and 'narration' must be text")

    if opt.get("preview_only"):
        args = engine_args(opt)
        data = llm_json(prompt, "You are a film director and prompt writer. You reply with a single JSON object and nothing else.",
                        model=(args[3] if len(args) > 3 else None), engine=args[1], validate=check)
        return {"preview": f"PROMPT: {data['prompt'].strip()}\nNARRATION: {data['narration'].strip()}", "prompt": data["prompt"].strip(), "narration": data["narration"].strip(),
                "feedback": "Preview ready. Click Apply & Insert to add it."}
    for top in ("videos", "audio", "images"):
        if (d / top).is_dir() and any(f.is_file() for f in (d / top).rglob("*") if f.suffix in (".mp4", ".wav", ".png")):
            raise PlanError("this book already has clips, pictures or audio: a new shot would shift their numbers. Add it before generating, or retake shots instead")
    text, narr = str(opt.get("prompt") or "").strip(), str(opt.get("narration") or "").strip()
    if not text or len(text) > 1000 or len(narr) > 1000:
        raise PlanError("preview the scene first")
    at = idxs[0] if pos == "before" else idxs[-1] + 1
    row = dict.fromkeys(shots[0], "")
    row.update(chapter=chapter, prompt=text)
    shots.insert(at, row)
    for n, i in enumerate((i for i, r in enumerate(shots) if r["chapter"] == chapter), 1):
        shots[i]["shot"] = str(n)
    _write_rows(d / "all_shots.csv", shots)
    if audio:
        arow = dict.fromkeys(audio[0], "")
        arow.update(chapter=chapter, narration=narr)
        a_at = next((i for i, r in enumerate(audio) if r["chapter"] == chapter), len(audio)) if pos == "before" else \
            (max((i for i, r in enumerate(audio) if r["chapter"] == chapter), default=len(audio) - 1) + 1)
        audio.insert(a_at, arow)
        for n, i in enumerate((i for i, r in enumerate(audio) if r["chapter"] == chapter), 1):
            audio[i]["shot"] = str(n)
        _write_rows(d / "audio_shots.csv", audio)
    return {"scene": f"Inserted as shot {shots[at]['shot']} of chapter {ch}"}


def animatic_step(body):
    """Step that makes films/animatic_<start>-<end>.mp4 from the keyframes (and narration, if made) of rows start..end."""
    slug = str(body.get("project", ""))
    if not SLUG_RE.match(slug) or not pdir(slug).is_dir():
        raise PlanError("pick a book first")
    start, end = num(body, "start", 1, int, 1, 100000), num(body, "end", 24, int, 1, 100000)
    if end < start:
        raise PlanError("end is before start")
    end = min(end, start + 199)
    argv = ["uv", "run", "--with", "imageio-ffmpeg", "python", "make_animatic.py", "--project", slug, "--start", str(start), "--end", str(end),
            "--out", f"animatic_{start}-{end}.mp4"]
    kf = str(body.get("keyframes") or "")
    if kf:
        if not re.fullmatch(r"[a-z0-9_]{2,60}", kf):
            raise PlanError("bad keyframe model name")
        argv += ["--keyframes", kf]
    return {"label": f"Make animatic for rows {start}-{end}", "argv": argv, "env": {}}


def upscale_step(body):
    """Step that upscales the clips of one video folder, rows start..end, with one of UPSCALE_MODELS on Kaggle or this computer: the result
    is videos/<source>_<model> (for example ltx_video_i2v_x2), which Make Film then offers as a video source."""
    slug = str(body.get("project", ""))
    if not SLUG_RE.match(slug) or not pdir(slug).is_dir():
        raise PlanError("pick a book or prompt set first")
    model = str(body.get("model") or "upscale_x2")
    lipsync = model == LIPSYNC_MODEL
    if model not in UPSCALE_MODELS and not lipsync:
        raise PlanError("choose an upscaler")
    inv = media_inventory(slug)
    key = str(body.get("source") or "")                       # as Make Film names it: videos/<folder>
    src = key.split("/", 1)[1] if key.startswith("videos/") else ""
    if key not in inv["videos"] or not re.fullmatch(r"[a-z0-9_]{2,60}", src):
        raise PlanError("choose the video folder to upscale")
    if lipsync and src.endswith("_lipsync"):
        raise PlanError("these clips are already lip-synced")
    if not lipsync and src.endswith(UPSCALE_SUFFIXES):
        raise PlanError("these clips are already upscaled")
    start, end = num(body, "start", 1, int, 1, 100000), num(body, "end", 1, int, 1, 100000)
    if end < start:
        raise PlanError("end is before start")
    have = set(inv["videos"][key])
    missing = [n for n in range(start, end + 1) if n not in have]
    if missing:
        raise PlanError(f"no clip in {src} for row(s) {', '.join(map(str, missing[:10]))}{' ...' if len(missing) > 10 else ''}")
    if lipsync and not any((pdir(slug) / "audio" / "kokoro" / f"narration-{n:04d}.wav").is_file() for n in range(start, end + 1)):
        raise PlanError("lip-sync follows the Kokoro narration, and these rows have none yet")
    service = body.get("service") or "kaggle"
    if service not in ("kaggle", "computer"):
        raise PlanError("upscaling runs on Kaggle or this computer: choose one of them in the Models tab")
    gpu = body.get("gpu") or ("local" if service == "computer" else "NvidiaTeslaT4")
    if gpu not in [g for g, _ in GPUS[service]] or gpu.startswith("Tpu"):
        raise PlanError("choose a GPU in the Models tab")
    why = gpu_blocker(service, gpu) or model_blocker(model, service, gpu)
    if why:
        raise PlanError(why)
    what = f"Lip-sync {src} rows {start}-{end}" if lipsync else f"Upscale {src} rows {start}-{end} 2x with {UPSCALE_MODELS[model][0]}"
    env = {"PROJECT": slug, "SHOTS_CSV": "all_shots.csv", "UPSCALE_SOURCE": src}
    if service == "computer":
        return {"label": f"{what} on this computer", "env": env,
                "argv": ["python3", "scripts/run_local_model.py", model, str(start), str(end)]}
    user = (body.get("kaggle_user") or "").strip()
    if not re.fullmatch(r"[A-Za-z0-9_-]{2,40}", user):
        raise PlanError("enter your Kaggle username (letters, digits, - and _), Models tab")
    env.update({"KAGGLE_USER": user, "KAGGLE_ACCELERATOR": gpu})
    return {"label": f"{what} on Kaggle", "argv": ["scripts/run_kaggle_model.sh", model, str(start), str(end)], "env": env}
