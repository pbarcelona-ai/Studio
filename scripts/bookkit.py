"""Shared helpers for the new-book pipeline (book_ingest.py, book_continuity.py, book_write.py, book_build.py).

Everything for a book lives in projects/<slug>/ :
  source/<name>.pdf      the uploaded PDF
  source_text.txt        extracted text
  chapters/chapter-NNN.txt, chapters.json
  <book name>.json       style, characters (visual tokens + voice), locations
  overrides.json         optional {"5": {"shots": 10}}  per-chapter shot counts
  scripts/chapter-NNN.json   what Claude wrote for each chapter
  all_shots.csv, all_chapters.csv, audio_shots.csv, audio_chapters.csv, movies.json   (built from the above)
  videos/, audio/, films/
"""
import csv
import json
import math
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PROJECTS = ROOT / "projects"
import layout        # where books, characters and prompt sets live (projects/books, projects/characters, projects/prompts)
SLUG_RE = re.compile(r"^[a-z0-9_]{2,40}$")

# Kokoro voices by role, used when a character needs a voice of its own.
VOICE_MAP = {"narrator": "bm_george", "male": "am_michael", "female": "af_bella", "elder": "bm_lewis",
             "deity": "bm_lewis", "child": "af_sky", "villain": "am_adam"}
WORDS_PER_SECOND = 2.5          # spoken narration
CLIP_SECONDS = 4.0              # LTX-Video clip (97 frames at 24 fps)
NEG_TAIL = "no text, no subtitles, no logos, no watermark"    # says nothing about style: the film's look comes from Global Parameters and visual_style
ASPECTS = {"16:9": 16 / 9, "2.39:1": 2.39, "4:3": 4 / 3, "1:1": 1.0, "9:16": 9 / 16}   # "" or a missing one = each model's own shape
FILM_FORMAT_FILE = "film_format.json"
VIDEO_NEGATIVE = "worst quality, inconsistent motion, blurry, jittery, distorted, text, subtitles, watermark, logo"   # with the look's own negatives, the negative column of all_shots.csv
AGING_LOOKS = ("", "live_action")   # stylised looks keep one design for a character for the whole film; only a realistic film ages people


def slugify(s):
    return re.sub(r"[^a-z0-9]+", "_", s.lower()).strip("_")[:40] or "book"


def project_dir(slug):
    if not SLUG_RE.match(slug):
        raise ValueError(f"bad project name {slug!r}: use 2-40 lowercase letters, digits or underscores")
    return layout.project_dir(slug, "book")


def continuity_file(pdir):
    """The continuity-book file of a book: <book name>.json inside the book's folder."""
    pdir = Path(pdir)
    return pdir / f"{pdir.name}.json"


def words(text):
    return len(text.split())


def strip_verse_numbers(text):
    """Drop inline verse/section numbers ("1 And it was ... 2 And in ...") that a voice would read aloud."""
    text = re.sub(r"^\s*\d{1,3}[.:]?\s+(?=[A-Z“\"'‘(])", "", text)
    return re.sub(r"(?<=[.!?;:”\"'’])\s+\d{1,3}[.:]?\s+(?=[A-Z“\"'‘(])", " ", text)


def sentences(text):
    # split after . ! ? and after any closing quote or bracket that follows it, but keep those closing marks in the sentence
    # (dropping them loses where a spoken quote ends)
    parts = re.split(r"(?<=[.!?])\s+|(?<=[.!?][\"'”’)])\s+|(?<=[.!?][\"'”’)][\"'”’)])\s+", text.strip())
    return [p.strip() for p in parts if p.strip()]


def read_json(path, default=None):
    path = Path(path)
    return json.loads(path.read_text()) if path.exists() else default


def write_json(path, data):
    Path(path).write_text(json.dumps(data, indent=1, ensure_ascii=False))


# ------------------------------------------------------------------ Claude Code, headless
_CLEAN_DROP = ("PYTHONHOME", "PYTHONPATH", "PYTHONEXECUTABLE", "VIRTUAL_ENV", "__PYVENV_LAUNCHER__")
COST = {"usd": 0.0, "calls": 0}


def _env():
    env = {k: v for k, v in os.environ.items() if k not in _CLEAN_DROP}
    parts = [d for d in env.get("PATH", "").split(":") if d and "oss-cad-suite" not in d]
    env["PATH"] = ":".join([str(Path.home() / ".local/bin"), "/usr/local/bin", "/opt/homebrew/bin"] + parts)
    return env


def extract_json(text):
    """First balanced JSON object in text (Claude sometimes wraps it in a code fence or adds a sentence)."""
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip())
    start = text.find("{")
    if start < 0:
        raise ValueError("no JSON object in the reply")
    depth, in_str, esc = 0, False, False
    for i in range(start, len(text)):
        c = text[i]
        if in_str:
            esc = (c == "\\") and not esc
            if c == '"' and not esc:
                in_str = False
            elif c != "\\":
                esc = False
        elif c == '"':
            in_str = True
        elif c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return json.loads(text[start:i + 1])
    raise ValueError("JSON object is cut off")


# engine name -> (command, family). `claude` and `fcc-claude` are the same CLI (fcc- routes it through the Free Claude
# Code proxy); `codex` and `fcc-codex` are the Codex CLI the same way.
ENGINES = {"claude": ("claude", "claude"), "fcc-claude": ("fcc-claude", "claude"),
           "codex": ("codex", "codex"), "fcc-codex": ("fcc-codex", "codex"),
           "hf": ("", "hf"),                     # hf = open models through Hugging Face Inference Providers (HF_TOKEN in the environment)
           "local": ("", "local")}               # local = a model server on this computer (Ollama, LM Studio, llama.cpp: any OpenAI-style endpoint)

HF_ROUTER_URL = os.environ.get("HF_ROUTER_URL", "https://router.huggingface.co/v1/chat/completions")
HF_DEFAULT_MODEL = "Qwen/Qwen3.8-27B"


def _chat(url, headers, messages, model, max_tokens, temperature, timeout, who):
    """One OpenAI-style chat call. Returns the reply text with any <think>...</think> reasoning removed."""
    import urllib.error
    import urllib.request
    body = json.dumps({"model": model, "messages": messages, "max_tokens": max_tokens, "temperature": temperature}).encode()
    req = urllib.request.Request(url, data=body, method="POST", headers={"Content-Type": "application/json", **headers})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            data = json.loads(r.read())
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "replace")[:300]
        hint = {401: "the token was refused (check HF_TOKEN)", 402: "no Inference Providers credit left on this account",
                403: "the token lacks the 'Make calls to Inference Providers' permission", 404: "that model is not served",
                429: "rate limit: wait a moment and try again"}.get(e.code, "") if who == "Hugging Face" else ""
        raise RuntimeError(f"{who} answered {e.code}" + (f" ({hint})" if hint else "") + f": {detail}") from e
    except (urllib.error.URLError, TimeoutError) as e:
        raise RuntimeError(f"could not reach {who}: {getattr(e, 'reason', e)}") from e
    try:
        text = data["choices"][0]["message"]["content"] or ""
    except (KeyError, IndexError, TypeError):
        raise RuntimeError(f"unexpected answer from {who}: {str(data)[:200]}") from None
    return re.sub(r"<think>.*?</think>", "", text, flags=re.S).strip()


def hf_chat(messages, model=None, max_tokens=1500, temperature=0.8, timeout=180):
    """One chat call to Hugging Face Inference Providers. The token is read from HF_TOKEN in the environment only and is never printed or
    written anywhere. `messages` may contain images ({"type": "image_url", ...} parts) for vision models."""
    token = (os.environ.get("HF_TOKEN") or "").strip()
    if not token:
        raise RuntimeError("HF_TOKEN is not set. Create a token at huggingface.co/settings/tokens with the permission "
                           "'Make calls to Inference Providers', add  export HF_TOKEN=...  to ~/.zshrc, and restart the Studio.")
    return _chat(HF_ROUTER_URL, {"Authorization": "Bearer " + token}, messages, model or HF_DEFAULT_MODEL, max_tokens, temperature, timeout, "Hugging Face")


LOCAL_LLM_URL = os.environ.get("LOCAL_LLM_URL", "http://127.0.0.1:11434/v1/chat/completions")     # Ollama's default; LM Studio is :1234, llama-server :8080


def local_chat(messages, model=None, max_tokens=1500, temperature=0.8, timeout=600):
    """One chat call to a model server running on THIS computer (any OpenAI-style endpoint, set with LOCAL_LLM_URL). No token, nothing leaves the machine."""
    if not (model or "").strip():
        raise RuntimeError("choose a local model name (the model box lists the ones your local server has)")
    return _chat(LOCAL_LLM_URL, {}, messages, model.strip(), max_tokens, temperature, timeout, "the local model server")


def llm_json(prompt, system, model=None, engine="claude", validate=None, retries=2, image=None):
    """One non-interactive call to a coding-agent CLI that must return a JSON object.

    claude / fcc-claude: `claude -p` with a tiny custom system prompt, no tools, no MCP servers and no settings files,
    which keeps each call at a few hundred tokens of overhead instead of ~30,000.
    codex / fcc-codex: `codex exec` in an empty temp folder with a read-only sandbox; the reply is read from the
    --output-last-message file.
    `model` blank/None/"default" means the tool's own default (for `claude` itself that is sonnet).
    `validate(data)` may raise ValueError; the error text is sent back for a corrected reply.
    `image` is the path of a picture for the model to look at (claude: it may use only the Read tool, on a copy in a private temp folder;
    codex: passed with -i). hf and local take pictures through hf_json messages instead, not through this argument.
    """
    if engine not in ENGINES:
        raise RuntimeError(f"unknown engine {engine!r}; use one of {sorted(ENGINES)}")
    cmd_name, family = ENGINES[engine]
    exe = shutil.which(cmd_name, path=_env()["PATH"]) if family not in ("hf", "local") else None
    if not exe and family not in ("hf", "local"):
        raise RuntimeError(f"the `{cmd_name}` command was not found")
    model = (model or "").strip()
    if model.lower() == "default":
        model = ""
    if engine == "claude" and not model:
        model = "sonnet"
    if image and family in ("hf", "local"):
        raise RuntimeError("pictures go to the hf and local engines through hf_json, not llm_json")
    feedback, last = "", None
    img_dir = tempfile.TemporaryDirectory() if image else None
    img_name = None
    if image:
        img_name = "picture" + (Path(image).suffix.lower() or ".jpg")
        shutil.copyfile(image, Path(img_dir.name) / img_name)
        if family == "claude":
            prompt = f"First use the Read tool to look at the picture file {img_name} in the current folder. Then do this:\n\n{prompt}"
    for _ in range(retries + 1):
        if family == "claude":
            cmd = [exe, "-p"] + (["--model", model] if model else []) + [
                "--tools", "Read" if image else "", "--no-session-persistence"] + (["--allowedTools", "Read"] if image else []) + [ "--output-format", "json", "--system-prompt", system,
                "--strict-mcp-config", "--mcp-config", '{"mcpServers":{}}', "--setting-sources", "", "--disable-slash-commands"]
            r = subprocess.run(cmd, input=prompt + feedback, text=True, capture_output=True, env=_env(), timeout=900, cwd=img_dir.name if image else None)
            if r.returncode != 0:
                last = RuntimeError(f"{cmd_name} exited {r.returncode}: {(r.stderr or r.stdout)[:300]}")
                feedback = ""
                continue
            outer = json.loads(r.stdout)
            COST["usd"] += float(outer.get("total_cost_usd") or 0); COST["calls"] += 1
            if outer.get("is_error"):
                last = RuntimeError(f"{cmd_name} error: {str(outer.get('result'))[:300]}")
                continue
            text = outer.get("result", "")
        elif family in ("hf", "local"):
            chat = hf_chat if family == "hf" else local_chat
            try:
                text = chat([{"role": "system", "content": system}, {"role": "user", "content": prompt + feedback}], model or (HF_DEFAULT_MODEL if family == "hf" else ""))
            except RuntimeError as e:
                if "HF_TOKEN is not set" in str(e) or "choose a local model" in str(e) or "could not reach" in str(e) or "refused" in str(e):
                    raise                                    # retrying cannot fix a missing token, a missing model name or a server that is not there
                last = e
                feedback = ""
                continue
            COST["calls"] += 1
        else:
            with tempfile.TemporaryDirectory() as tmp:
                out = Path(tmp) / "last.txt"
                cmd = [exe, "exec", "--skip-git-repo-check", "--ephemeral", "-s", "read-only", "-o", str(out)] + \
                      (["-m", model] if model else []) + (["-i", str(Path(img_dir.name) / img_name)] if image else []) + ["-"]
                r = subprocess.run(cmd, input=f"{system}\n\n{prompt}{feedback}", text=True, capture_output=True,
                                   env=_env(), cwd=tmp, timeout=900)
                text = out.read_text() if out.exists() else ""
            COST["calls"] += 1
            if r.returncode != 0 or not text.strip():
                last = RuntimeError(f"{cmd_name} exec failed ({r.returncode}): {(r.stderr or r.stdout)[-300:]}")
                feedback = ""
                continue
        try:
            data = extract_json(text)
            if validate:
                validate(data)
            if img_dir:
                img_dir.cleanup()
            return data
        except (ValueError, json.JSONDecodeError) as e:
            last = e
            feedback = f"\n\nYour previous reply was rejected: {e}. Reply again with ONLY the corrected JSON object."
    if img_dir:
        img_dir.cleanup()
    raise RuntimeError(f"{engine} did not return usable JSON after {retries + 1} tries: {last}")


def hf_json(messages, model=None, validate=None, retries=1, chat=None):
    """A chat call (Hugging Face by default, or `chat=local_chat`) that must return a JSON object (retries once with the error text if it does not)."""
    last, msgs = None, list(messages)
    for _ in range(retries + 1):
        text = (chat or hf_chat)(msgs, model)
        try:
            data = extract_json(text)
            if validate:
                validate(data)
            return data
        except (ValueError, json.JSONDecodeError) as e:
            last = e
            msgs = list(messages) + [{"role": "assistant", "content": text},
                                     {"role": "user", "content": f"That reply was rejected: {e}. Reply again with ONLY the corrected JSON object."}]
    raise RuntimeError(f"the model did not return usable JSON after {retries + 1} tries: {last}")


claude_json = llm_json          # old name, kept for any script that still imports it


def cost_note():
    """', $0.05 at list price' when the engine reports a cost (claude does; codex does not), else ''."""
    return f", ${COST['usd']:.2f} at list price" if COST["usd"] else ""


# ------------------------------------------------------------------ shot allocation and prompt text
def shot_count(chapter_words, words_per_shot, lo, hi, override=None):
    if override:
        return max(1, int(override))
    return max(lo, min(hi, math.ceil(chapter_words / max(words_per_shot, 1))))


def slice_text(text, n):
    """Cut text into n contiguous slices at sentence boundaries with roughly equal word counts."""
    sents = sentences(text)
    n = max(1, min(n, len(sents)))
    total = sum(words(s) for s in sents)
    out, cur, acc, target = [], [], 0, total / n
    for i, s in enumerate(sents):
        cur.append(s); acc += words(s)
        left_sents = len(sents) - i - 1
        left_slices = n - len(out) - 1
        if len(out) < n - 1 and (acc >= target or left_sents == left_slices):
            out.append(" ".join(cur)); cur, acc = [], 0
    if cur:
        out.append(" ".join(cur))
    return out


def chapter_in(spec, chapter):
    """Is this chapter number inside a range like "5", "5-12" or "5-" (to the end)? Anything unreadable is False."""
    m = re.fullmatch(r"\s*(\d+)\s*(?:(-)\s*(\d*)\s*)?", str(spec or ""))
    if not m or chapter is None:
        return False
    lo = int(m.group(1))
    hi = lo if not m.group(2) else (int(m.group(3)) if m.group(3) else 10**9)
    return lo <= chapter <= hi


def stage_for(character, chapter, look=""):
    """The life stage of a character in this chapter: {"label", "chapters", "token"}, or None (no stage covers it, or a stylised look)."""
    if look not in AGING_LOOKS:
        return None
    for st in character.get("stages") or []:
        if isinstance(st, dict) and str(st.get("token") or "").strip() and chapter_in(st.get("chapters"), chapter):
            return st
    return None


def character_token(character, chapter=None, look=""):
    """The description of a character to use in this chapter: the token of its life stage if it has one, else its one fixed token."""
    st = stage_for(character, chapter, look)
    return str(st["token"]).strip() if st else character.get("token", "")


def shot_negative(global_negatives=""):
    """What a shot must not look like, for the notebooks' negative prompt."""
    return ", ".join(x for x in (str(global_negatives or "").strip(" ,"), VIDEO_NEGATIVE) if x)


def compose_prompt(visual, characters, continuity, limit=1000, global_positives="", global_negatives="", chapter=None, look="", location=""):
    """Visual description + the continuity book's exact character tokens (for this chapter's life stage) + the location's token + style + global
    params, kept under the model's prompt window. When it does not fit, the location goes first, then characters from the end."""
    known = {c["name"].lower(): c for c in continuity.get("characters", [])}
    tokens = []
    for n in characters:
        c = known.get(str(n).lower())
        if c:
            tok = re.sub(rf"^{re.escape(c['name'])}\s*[:,-]\s*", "", character_token(c, chapter, look), flags=re.I)   # don't repeat the name
            tokens.append(f"{c['name'].upper()}: {tok}")
    place = next((p for p in continuity.get("locations", []) if str(p.get("name", "")).lower() == str(location or "").strip().lower()), None)
    if place and place.get("token"):
        tokens.append(f"SETTING: {place['token']}")
    base = visual.strip().rstrip(".")
    style = (continuity.get("visual_style") or "").strip().rstrip(".")

    # global_negatives are not added here: words in this text would ask the model FOR them. They go in the shot's negative column (shot_negative).
    neg_tail = NEG_TAIL

    # Build the positive parts with global positives
    def build_positive_parts(token_list):
        parts = []
        if global_positives:
            parts.append(global_positives)
        parts.append(base)
        parts.extend(token_list)
        if style:
            parts.append(style)
        return parts

    positive_parts = build_positive_parts(tokens)

    # Try combinations to fit within limit
    for tail in (neg_tail, NEG_TAIL, ""):
        parts = positive_parts + ([tail] if tail else [])
        text = ", ".join(parts)
        if len(text) <= limit:
            return text

    # If still too long, trim tokens from the end
    while tokens and len(", ".join(build_positive_parts(tokens))) > limit:
        tokens.pop()

    # Final attempt with trimmed tokens
    for tail in (neg_tail, NEG_TAIL, ""):
        parts = build_positive_parts(tokens) + ([tail] if tail else [])
        text = ", ".join(parts)
        if len(text) <= limit:
            return text

    # Last resort: truncate the whole thing
    return (", ".join(build_positive_parts(tokens) + ([neg_tail] if neg_tail else [])))[:limit].rsplit(" ", 1)[0]


# ------------------------------------------------------------------ movies: ~N minutes each, always ending on a chapter end
def read_csv(path):
    return list(csv.DictReader(open(path, newline=""))) if Path(path).exists() else []


def estimate_seconds(narration):
    """Length of a shot once narration is stretched to fit: the clip, or the speech plus padding if that is longer."""
    return max(CLIP_SECONDS, words(narration or "") / WORDS_PER_SECOND + 0.4)


def group_chapters(chapters, target_seconds):
    """chapters: [{label, rows:(first,last), seconds}] in order -> list of movies (lists of chapters).

    Each movie ends at a chapter end. Among the possible end points it takes the one whose total is closest to the
    target (never ending a movie early at a point more than 25% over target unless one chapter alone is longer than
    that). A short tail (< 40% of target) is folded into the previous movie.
    """
    movies, i = [], 0
    while i < len(chapters):
        total, best, j = 0.0, None, i
        while j < len(chapters):
            total += chapters[j]["seconds"]
            if best is None or abs(total - target_seconds) < abs(best[1] - target_seconds):
                best = (j, total)
            if total > target_seconds * 1.25:
                break
            j += 1
        movies.append(chapters[i:best[0] + 1])
        i = best[0] + 1
    if len(movies) > 1 and sum(c["seconds"] for c in movies[-1]) < 0.4 * target_seconds:
        tail = movies.pop()                   # (not `movies[-2] += movies.pop()`: the target index is read before the pop, so the wrong movie was replaced)
        movies[-1] += tail
    return movies


def build_movies(pdir, minutes=10.0):
    """Write movies.json for a project: one plan for 'shots' mode and one for 'chapters' mode."""
    pdir = Path(pdir)
    plan = {"minutes": minutes}
    for mode, shots_csv, audio_csv in (("shots", "all_shots.csv", "audio_shots.csv"),
                                       ("chapters", "all_chapters.csv", "audio_chapters.csv")):
        prompts, audio = read_csv(pdir / shots_csv), read_csv(pdir / audio_csv)
        if not prompts:
            continue
        chapters, order = {}, []
        for i, row in enumerate(prompts, start=1):
            narr = audio[i - 1]["narration"] if i - 1 < len(audio) else ""
            c = chapters.setdefault(row["chapter"], {"label": row["chapter"], "rows": [i, i], "seconds": 0.0})
            c["rows"][1] = i
            c["seconds"] += estimate_seconds(narr)
            if row["chapter"] not in order:
                order.append(row["chapter"])
        groups = group_chapters([chapters[k] for k in order], minutes * 60)
        plan[mode] = [{"id": n, "chapters": [c["label"] for c in g],
                       "first_chapter": g[0]["label"], "last_chapter": g[-1]["label"],
                       "rows": [g[0]["rows"][0], g[-1]["rows"][1]],
                       "clips": g[-1]["rows"][1] - g[0]["rows"][0] + 1,
                       "est_seconds": round(sum(c["seconds"] for c in g))}
                      for n, g in enumerate(groups, start=1)]
    write_json(pdir / "movies.json", plan)
    return plan


# ------------------------------------------------------------------ your own edits to a scene's prompts
# projects/<name>/prompt_edits.json:  {"<chapter>#<shot>": {"chapter":..., "shot":..., "updated":...,
#     "fields": {"prompt": {"original": "...", "edited": "..."}, "narration": {...}, "sfx": {...}, "music": {...}}}}
# The CSVs are rebuilt from the book text/markdown whenever the prompts are rebuilt, so edits live here and are re-applied after each
# rebuild (legacy_extract.py and book_build.py call apply_prompt_edits at the end).
EDIT_FIELDS = {"prompt": ("all_shots.csv", "all_chapters.csv"), "narration": ("audio_shots.csv", "audio_chapters.csv"),
               "sfx": ("audio_shots.csv", "audio_chapters.csv"), "music": ("audio_shots.csv", "audio_chapters.csv")}


def _write_csv(path, rows):
    if not rows:
        return
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)


def _narration_lines(row, text):
    """Replace the spoken text of a row; the first line's speaker (and voice) is kept."""
    try:
        old = json.loads(row.get("lines_json") or "[]")
    except ValueError:
        old = []
    first = old[0] if old else ["NARRATOR"]
    return json.dumps([[first[0], text] + ([first[2]] if len(first) > 2 else [])], ensure_ascii=False)


def set_scene_field(pdir, chapter, shot, field, value):
    """Write one field of one scene into every CSV that carries it. Returns how many rows were changed."""
    pdir, changed = Path(pdir), 0
    for name in EDIT_FIELDS[field]:
        rows = read_csv(pdir / name)
        hit = False
        for r in rows:
            if r.get("chapter") == chapter and str(r.get("shot")) == str(shot) and r.get(field) != value:
                r[field] = value
                if field == "narration" and "lines_json" in r:
                    r["lines_json"] = _narration_lines(r, value)
                hit = True; changed += 1
        if hit:
            _write_csv(pdir / name, rows)
    return changed


def apply_prompt_edits(pdir):
    """Re-apply every saved edit (after the CSVs were rebuilt). Returns the number of rows changed."""
    pdir = Path(pdir)
    edits = read_json(pdir / "prompt_edits.json", {})
    n = 0
    for e in edits.values():
        for field, v in e.get("fields", {}).items():
            n += set_scene_field(pdir, e["chapter"], e["shot"], field, v["edited"])
    return n


# ------------------------------------------------------------------ voice cast: which voice speaks each speaker's lines
# projects/<name>/voice_cast.json: {"cast": {"NARRATOR": "bm_george", "Eve": "af_bella", ...}}
# Each line of audio_shots.csv's lines_json is [speaker, text, (voice)]. The cast gives every line of a speaker that speaker's voice, so a
# character's own voice overrides the narrator's. A speaker the cast leaves blank keeps the voice its lines have now (the writing step's
# choice, an earlier cast, or none: then the narration step's default). Kept in its own file and re-applied after each rebuild (book_build.py), like prompt_edits.json.
KOKORO_VOICE_RE = re.compile(r"^[ab][fm]_[a-z]{2,16}$")       # a = American, b = British English (the two Kokoro pipelines the narration step loads)
KOKORO_VOICES = ["af_heart", "af_bella", "af_nicole", "af_sarah", "af_sky", "af_nova", "af_river", "af_jessica", "af_kore", "af_aoede", "af_alloy",
                 "am_michael", "am_adam", "am_eric", "am_liam", "am_onyx", "am_echo", "am_fenrir", "am_puck",
                 "bf_emma", "bf_isabella", "bf_alice", "bf_lily", "bm_george", "bm_lewis", "bm_daniel", "bm_fable"]
VOICE_CAST_FILE = "voice_cast.json"


def read_film_format(pdir):
    """{"aspect": "16:9" or "", "chain": bool}: the shape of the book's clips and whether shots that continue the action start from the shot before."""
    d = read_json(Path(pdir) / FILM_FORMAT_FILE, {}) or {}
    aspect = d.get("aspect") if d.get("aspect") in ASPECTS else ""
    return {"aspect": aspect, "chain": bool(d.get("chain"))}


def apply_film_format(pdir, aspect=None, chain=None):
    """Save the film format if given, then write it into all_shots.csv and all_chapters.csv as the aspect and chain columns (the video notebooks read
    them row by row). Kept in its own file and re-applied after each rebuild (book_build.py). Returns the format now in force."""
    pdir = Path(pdir)
    fmt = read_film_format(pdir)
    if aspect is not None:
        if aspect and aspect not in ASPECTS:
            raise ValueError(f"unknown aspect {aspect!r}")
        fmt["aspect"] = aspect
    if chain is not None:
        fmt["chain"] = bool(chain)
    write_json(pdir / FILM_FORMAT_FILE, fmt)
    for name in ("all_shots.csv", "all_chapters.csv"):
        rows = read_csv(pdir / name)
        if not rows:
            continue
        for r in rows:
            r["aspect"] = fmt["aspect"]
            r["chain"] = "1" if fmt["chain"] and str(r.get("continues") or "") == "1" else ""
        _write_csv(pdir / name, rows)
    return fmt


def voice_id(word):
    """A continuity-book voice word (male, elder, ...) or a Kokoro voice id -> the Kokoro id, or "" if it is neither."""
    w = str(word or "").strip()
    return VOICE_MAP.get(w.lower()) or (w if KOKORO_VOICE_RE.match(w) else "")


def read_voice_cast(pdir):
    cast = read_json(Path(pdir) / VOICE_CAST_FILE, {}).get("cast")
    return {str(k): str(v) for k, v in cast.items() if KOKORO_VOICE_RE.match(str(v))} if isinstance(cast, dict) else {}


def apply_voice_cast(pdir, cast=None):
    """Re-voice every line of audio_shots.csv and audio_chapters.csv from the cast (default: the saved voice_cast.json).
    Returns the audio_shots.csv row numbers (1-based, the narration file numbers) whose voices changed."""
    pdir = Path(pdir)
    cast = read_voice_cast(pdir) if cast is None else cast
    by_speaker = {k.strip().lower(): v for k, v in cast.items() if v}
    changed_rows = []
    if not by_speaker:
        return changed_rows
    for name in ("audio_shots.csv", "audio_chapters.csv"):
        rows = read_csv(pdir / name)
        hit = False
        for i, r in enumerate(rows, start=1):
            try:
                lines = json.loads(r.get("lines_json") or "[]")
            except ValueError:
                continue
            if not isinstance(lines, list):
                continue
            new = []
            for ln in lines:
                if isinstance(ln, list) and len(ln) >= 2 and str(ln[0]).strip().lower() in by_speaker:
                    ln = [ln[0], ln[1], by_speaker[str(ln[0]).strip().lower()]]
                new.append(ln)
            if new != lines:
                r["lines_json"] = json.dumps(new, ensure_ascii=False)
                hit = True
                if name == "audio_shots.csv":
                    changed_rows.append(i)
        if hit:
            _write_csv(pdir / name, rows)
    return changed_rows
