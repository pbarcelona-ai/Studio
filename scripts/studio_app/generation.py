"""Turns the chosen options into the generation steps (keyframes, video, audio, merge, mix) and the "Make my film" plan."""
import os
import re
import sys
from pathlib import Path
from bookkit import ASPECTS, continuity_file, SLUG_RE, read_json
import character_tokens
import layout
import model_advisor
from layout import project_dir as pdir     # a name -> its folder (books/, characters/ or prompts/); see layout.py

from .common import PlanError, num
from .config import AUDIO_KINDS, GPUS, I2V_MODELS, IMAGE_MODELS, MODEL_DEFAULTS, REF_IMAGE_MODELS, SYNC_MODES, VIDEO_MODELS, get_character_series
from .gpus import check_models, gpu_blocker
from .projects import read_csv_rows
from .steps import FILM_KEYFRAMES, FILM_SPACE, FILM_VIDEO, PEOPLE_WORDS, chunks, make_runner


def film_options(opt):
    """Fill in a Make my film request: everything from the book to the film, and only what is not done yet. Changes opt, which later steps read too."""
    slug = str(opt.get("project") or "")
    if not SLUG_RE.match(slug):
        raise PlanError("choose a book in Read book first, or paste some text")
    d = layout.find_dir(slug)
    opt["steps"] = {"ingest": not (d and (d / "chapters.json").exists()), "continuity": not (d and continuity_file(d).exists()), "write": True, "build": True,
                    "keyframes": True, "video": True, "audio": True, "mix": True}
    opt["force_write"] = False
    opt["sync"] = opt.get("sync") or "gentle"
    opt["aspect"] = opt.get("aspect") or "16:9"
    opt["scenes"] = True
    opt["music_bed"] = True
    opt["credits"] = bool(d and (d / "credits.json").exists())             # credits filled in on the Export card roll after the end title
    opt["grade"] = bool(d and (d / "grading.json").exists())               # colour grades set in the Film plan card
    opt["music_scenes"] = bool(d and (d / "adaptation" / "adaptation.json").exists())          # a book with a film plan gets music that follows its scenes
    return opt


def chunks_of(numbers):
    """[1, 2, 3, 7] -> [(1, 3), (7, 7)]: runs of neighbouring numbers."""
    runs: list = []
    for n in numbers:
        if runs and runs[-1][1] == n - 1:
            runs[-1][1] = n
        else:
            runs.append([n, n])
    return [tuple(r) for r in runs]


def pictures_missing(folder, lo, hi):
    """The rows lo..hi with no keyframe picture in this folder now, as runs of neighbours. A shot whose picture was re-rolled (kept as a take)
    has none, so it is made again."""
    runs: list = []
    for n in range(lo, hi + 1):
        if (Path(folder) / f"image-{n:04d}.png").is_file():
            continue
        if runs and runs[-1][1] == n - 1:
            runs[-1][1] = n
        else:
            runs.append([n, n])
    return [tuple(r) for r in runs]


def rows_missing(lo, hi, *patterns):
    """The rows lo..hi with no file in any of these patterns ("folder/shot-{:04d}.mp4"), as runs of neighbours: [(lo, hi), ...]."""
    runs: list = []
    for n in range(lo, hi + 1):
        if any(Path(str(p).format(n)).is_file() or next(Path(str(p).format(n)).parent.glob(f"takes/{Path(str(p).format(n)).stem}-t*"), None) for p in patterns):
            continue
        if runs and runs[-1][1] == n - 1:
            runs[-1][1] = n
        else:
            runs.append([n, n])
    return [tuple(r) for r in runs]


def is_people_shot(row):
    return bool((row.get("characters") or "").strip()) or bool(PEOPLE_WORDS.search(row.get("prompt") or ""))


def local_audio_step(slug, kind):
    pins = ["--with", "numpy<2", "--with", "pip"]
    if sys.platform == "darwin" and os.uname().machine == "x86_64":
        pins += ["--with", "torch==2.2.2", "--with", "transformers<4.50"]      # the last PyTorch for Intel Macs, and the last transformers that accepts it
    extra = ["--with", "kokoro", "--with", "soundfile"] if kind in ("kokoro", "audiobook") else ["--with", "transformers<4.50", "--with", "scipy", "--with", "accelerate"]
    title = {"kokoro": "narration", "audiobook": "the audiobook narration"}.get(kind, "one music cue per chapter")
    return {"label": f"Make {title} on this computer", "env": {}, "argv": ["uv", "run", "--quiet", "--python", "3.11"] + pins + extra + ["python", "local_audio.py", slug, kind]}


def film_video_steps(opt, slug):
    """Clips still missing, with the T4-sized model. Decided when the step is reached, after Pika's quota has done what it can."""
    d, runner = pdir(slug), make_runner(opt["service"], opt["gpu"], (opt.get("kaggle_user") or "").strip(), slug)
    out = []
    for mv in read_json(d / "movies.json", {}).get("shots", []):
        for s, e in rows_missing(mv["rows"][0], mv["rows"][1], d / "videos" / FILM_VIDEO / "shot-{:04d}.mp4", d / "videos" / FILM_SPACE / "shot-{:04d}.mp4"):
            argv, env = runner(FILM_VIDEO, s, e, "all_shots.csv")
            env["KEYFRAME_MODEL"] = FILM_KEYFRAMES
            out.append({"label": f"Movie {mv['id']} video {FILM_VIDEO}: rows {s}-{e}", "argv": argv, "env": env})
    return out


def film_steps(opt, slug):
    """Everything after the book's CSVs, for each movie, skipping what exists: running it again carries on after a quota stop."""
    service, gpu = opt.get("service"), opt.get("gpu")
    if service not in ("kaggle", "computer"):
        raise PlanError("Make my film makes its keyframes on Kaggle or this computer: choose one in the Models tab, Where to run")
    if gpu not in [g for g, _ in GPUS[service]]:
        raise PlanError(f"gpu {gpu!r} is not an option for {service}")
    if gpu_blocker(service, gpu):
        raise PlanError(gpu_blocker(service, gpu))
    user = (opt.get("kaggle_user") or "").strip()
    if service == "kaggle" and not re.fullmatch(r"[A-Za-z0-9_-]{2,40}", user):
        raise PlanError("enter your Kaggle username (letters, digits, - and _), Models tab")
    d = pdir(slug)
    movies = read_json(d / "movies.json", {}).get("shots", [])
    if not movies:
        raise PlanError("no movies planned: the book's steps made no shots")
    shots = read_csv_rows(d / "all_shots.csv")
    kw, kh = keyframe_size(FILM_KEYFRAMES, FILM_VIDEO, opt["aspect"])
    series = opt.get("keyframe_series") or get_character_series(slug)
    refs = ["--refs", series] if series in character_tokens.list_series() else []
    look = opt.get("look") if opt.get("look") in model_advisor.LOOKS else ""
    runner = make_runner(service, gpu, user, slug)
    steps: list[dict] = [{"label": f"Film format: {opt['aspect']}", "env": {}, "argv": ["python3", "film_format.py", slug, "--aspect", opt["aspect"], "--chain", "off"]},
             {"label": f"Write keyframes.csv ({kw}x{kh})", "env": {},
              "argv": ["python3", "make_keyframes_csv.py", slug, "--width", str(kw), "--height", str(kh)] + refs + (["--look", look] if look else [])}]
    kf = d / "images" / f"{FILM_KEYFRAMES}_keyframes"
    use_space = bool(opt.get("film_space"))
    for mv in movies:
        lo, hi = mv["rows"]
        for s, e in rows_missing(lo, hi, kf / "image-{:04d}.png"):
            argv, env = runner(f"image_{FILM_KEYFRAMES}", s, e, "keyframes.csv")
            steps.append({"label": f"Movie {mv['id']} keyframes: rows {s}-{e}", "argv": argv, "env": env})
        if use_space:                                    # shots with people on the Space; its quota running out is expected, not a failure
            people = [n for n in range(lo, hi + 1) if n <= len(shots) and is_people_shot(shots[n - 1])]
            done = lambda n: (d / "videos" / FILM_SPACE / f"shot-{n:04d}.mp4").is_file() or (d / "videos" / FILM_VIDEO / f"shot-{n:04d}.mp4").is_file()
            runs: list = []
            todo = [n for n in people if not done(n)]
            for n in todo:
                if runs and runs[-1][1] == n - 1:
                    runs[-1][1] = n
                else:
                    runs.append([n, n])
            for s, e in runs:
                env = {"PROJECT": slug, "SHOTS_CSV": "all_shots.csv", "KEYFRAME_MODEL": FILM_KEYFRAMES}
                steps.append({"label": f"Movie {mv['id']} shots with people on Pika's Space: rows {s}-{e}", "env": env, "ok_codes": (0, 1),
                              "argv": ["scripts/run_hf_space.sh", FILM_SPACE, str(s), str(e)]})
    steps.append({"label": "clips still missing", "expand": "film_video"})
    scene_music = bool(opt.get("music_scenes")) and (d / "audio_scenes.csv").exists()
    if opt.get("local_audio"):
        steps += [local_audio_step(slug, "kokoro"), local_audio_step(slug, "musicgen_scenes" if scene_music else "musicgen")]
    else:
        narr, cue = d / "audio" / "kokoro" / "narration-{:04d}.wav", d / "audio" / ("musicgen_scenes" if scene_music else "musicgen_chapters") / "music-{:04d}.wav"
        for mv in movies:
            for s, e in rows_missing(mv["rows"][0], mv["rows"][1], narr):
                argv, env = runner("audio_kokoro", s, e, "audio_shots.csv")
                steps.append({"label": f"Movie {mv['id']} narration: rows {s}-{e}", "argv": argv, "env": env})
        cues_csv = "audio_scenes.csv" if scene_music else "audio_chapters.csv"
        chapters = len(read_csv_rows(d / cues_csv))
        for s, e in rows_missing(1, chapters, cue):
            argv, env = runner("audio_musicgen", s, e, cues_csv)
            steps.append({"label": f"Music cues: {'scenes' if scene_music else 'chapters'} {s}-{e}", "argv": argv, "env": env})
    vols = {k: num(opt.get("vol", {}), k, v, float, 0, 5) for k, v in (("narration", 1.0), ("sfx", 0.5), ("music", 0.25))}
    for mv in movies:
        lo, hi = mv["rows"]
        steps.append({"label": f"Movie {mv['id']} final film", "env": {},
                      "argv": ["uv", "run", "--with", "imageio-ffmpeg", "python", "mix_film.py", "--project", slug, "--models", f"{FILM_SPACE},{FILM_VIDEO}", "--start", str(lo), "--end", str(hi),
                               "--sync", opt["sync"] if opt["sync"] in SYNC_MODES else "gentle", "--music-scenes" if scene_music else "--music-bed", *(["--grade"] if opt.get("grade") else []), *(["--credits"] if opt.get("credits") else []), "--out", f"{slug}-movie-{mv['id']:02d}.mp4",
                               "--vol-narration", str(vols["narration"]), "--vol-sfx", str(vols["sfx"]), "--vol-music", str(vols["music"])]})
    return steps


def film_status(slug):
    """How far a book has come, for the Make my film card: a count for each stage, and its finished films newest first."""
    if not SLUG_RE.match(slug or ""):
        raise PlanError("bad book name")
    d = layout.find_dir(slug)
    if d is None:
        return {"exists": False}
    count = lambda folder, pattern: len(list((d / folder).glob(pattern))) if (d / folder).is_dir() else 0
    clips = {p.name for sub in (FILM_SPACE, FILM_VIDEO) for p in (d / "videos" / sub).glob("shot-*.mp4")} if (d / "videos").is_dir() else set()
    films = sorted((d / "films").glob("*.mp4"), key=lambda p: p.stat().st_mtime, reverse=True) if (d / "films").is_dir() else []
    return {"exists": True, "chapters": len(read_json(d / "chapters.json", {}).get("chapters", [])) if (d / "chapters.json").exists() else 0,
            "continuity": continuity_file(d).exists(), "scripts": count("scripts", "chapter-*.json"), "shots": len(read_csv_rows(d / "all_shots.csv")),
            "keyframes": count(f"images/{FILM_KEYFRAMES}_keyframes", "image-*.png"), "clips": len(clips), "narration": count("audio/kokoro", "narration-*.wav"),
            "cues": count("audio/musicgen_chapters", "music-*.wav"), "cues_wanted": len(read_csv_rows(d / "audio_chapters.csv")),
            "films": [f"{slug}/films/{p.name}" for p in films]}


def generation_steps(opt, slug):
    """Video/audio/merge/mix steps for the chosen movies. Needs movies.json, so it may run after the book steps."""
    if opt.get("film"):
        return film_steps(opt, slug)
    service = opt.get("service")
    if service not in GPUS:
        raise PlanError("choose where the models run: Kaggle, Colab, Hugging Face or this computer")
    gpu = opt.get("gpu")
    if gpu not in [g for g, _ in GPUS[service]]:
        raise PlanError(f"gpu {gpu!r} is not an option for {service}")
    if gpu_blocker(service, gpu):
        raise PlanError(gpu_blocker(service, gpu))
    st = opt.get("steps", {})
    chapters_mode = opt.get("granularity") == "chapters"
    vmodels = [m for m in opt.get("video_models", []) if m in VIDEO_MODELS]
    akinds = [k for k in opt.get("audio", []) if k in AUDIO_KINDS]
    user = (opt.get("kaggle_user") or "").strip()
    if service == "kaggle" and (st.get("video") or st.get("audio") or st.get("keyframes")) and not re.fullmatch(r"[A-Za-z0-9_-]{2,40}", user):
        raise PlanError("enter your Kaggle username (letters, digits, - and _)")
    kmodel = opt.get("keyframe_model") or ""
    if st.get("keyframes") and kmodel not in IMAGE_MODELS:
        raise PlanError("choose the image model that makes the keyframes")
    if kmodel and kmodel not in IMAGE_MODELS:
        raise PlanError("unknown keyframe image model")
    refs = bool(opt.get("keyframe_refs")) and bool(st.get("keyframes"))
    look = str(opt.get("look") or "")
    if look and look not in model_advisor.LOOKS:
        raise PlanError("unknown look")
    if refs and kmodel not in REF_IMAGE_MODELS:
        raise PlanError(f"character pictures steer only {', '.join(sorted(REF_IMAGE_MODELS))} keyframes: pick it, or untick 'Steer keyframes with character pictures'")
    if st.get("keyframes") and service not in ("kaggle", "computer"):
        raise PlanError("keyframes are made on Kaggle or this computer (the Colab and Hugging Face runners do not keep them apart from other images): choose one of those")
    i2v = [m for m in vmodels if m in I2V_MODELS] if st.get("video") else []
    if (st.get("keyframes") or i2v) and chapters_mode:
        raise PlanError("keyframes and the 'from keyframes' video models work per shot: choose 'Every shot'")
    check_models(service, gpu, (vmodels if st.get("video") else []) + (akinds if st.get("audio") else []) + ([kmodel] if st.get("keyframes") else []))
    batch = num(opt, "batch", 0, int, 0, 100000)
    sync = opt.get("sync", "stretch")
    if sync not in SYNC_MODES:
        raise PlanError("bad sync mode")
    vols = {k: num(opt.get("vol", {}), k, d, float, 0, 5) for k, d in (("narration", 1.0), ("sfx", 0.5), ("music", 0.25))}
    aspect = str(opt.get("aspect") or "")
    if aspect and aspect not in ASPECTS:
        raise PlanError("unknown film shape")
    music_scenes = bool(opt.get("music_scenes")) and not chapters_mode      # music that follows the scenes of the film plan (audio_scenes.csv)
    if music_scenes and not (pdir(slug) / "audio_scenes.csv").exists():
        raise PlanError("this book has no scene music list: plan the film, approve its screenplay, then run 'Build CSVs' (it writes audio_scenes.csv)")
    music_bed = (bool(opt.get("music_bed")) or music_scenes) and not chapters_mode      # in chapter mode each chapter already has one cue

    plan = read_json(pdir(slug) / "movies.json", {})
    movies = plan.get("chapters" if chapters_mode else "shots", [])
    if not movies:
        raise PlanError("no movies planned yet for this book and mode: run the 'Build CSVs and plan movies' step first")
    sel = opt.get("movies", {})
    if sel.get("mode") == "all":
        chosen = movies
    elif sel.get("mode") == "first":
        chosen = movies[: num(sel, "n", 1, int, 1, 1000)]
    else:
        ids = {int(i) for i in sel.get("ids", [])}
        chosen = [m for m in movies if m["id"] in ids]
    if not chosen:
        raise PlanError("tick at least one movie")
    lo_o = num(opt, "range_start", 0, int, 0) or None
    hi_o = num(opt, "range_end", 0, int, 0) or None

    suf = "_chapters" if chapters_mode else ""
    vcsv = "all_chapters.csv" if chapters_mode else "all_shots.csv"
    acsv = "audio_chapters.csv" if chapters_mode else "audio_shots.csv"
    steps = []

    runner = make_runner(service, gpu, user, slug)
    if st.get("keyframes") or st.get("video"):
        fixed = [m for m in vmodels if "width" in (MODEL_DEFAULTS.get(m, {}).get("locked") or [])] if aspect else []
        steps.append({"label": f"Film format: {aspect or 'each model its own shape'}" + (f" ({', '.join(fixed)} keep their own shape)" if fixed else ""), "env": {},
                      "argv": ["python3", "film_format.py", slug, "--aspect", aspect or "model", "--chain", "on" if opt.get("chain") else "off"]})
    if st.get("keyframes"):
        kw, kh = keyframe_size(kmodel, (i2v or vmodels or ["ltx_video"])[0], aspect)
        series = opt.get("keyframe_series") or get_character_series(slug)     # the pictures can come from any series (Characters tab)
        if refs and series not in character_tokens.list_series():
            raise PlanError(f"no character series named {series!r}: choose one on the Characters tab")
        steps.append({"label": f"Write keyframes.csv ({kw}x{kh}" + (f", character pictures from '{series}')" if refs else ")"), "env": {},
                      "argv": ["python3", "make_keyframes_csv.py", slug, "--width", str(kw), "--height", str(kh)] + (["--refs", series] if refs else [])
                              + (["--look", look] if look else [])})

    done = set()
    kf_dir, kf_steps = pdir(slug) / "images" / f"{kmodel}_keyframes", 0
    for mv in chosen:
        lo, hi = mv["rows"]
        lo, hi = max(lo, lo_o or lo), min(hi, hi_o or hi)
        for s, e in (chunks(lo, hi, batch) if lo <= hi else []):
            if st.get("keyframes") and ("kf", s, e) not in done:      # stills first, so the video steps after them can animate them
                done.add(("kf", s, e))
                for a, b in pictures_missing(kf_dir, s, e):     # only the rows with no picture yet (a re-rolled one has none): no GPU time for the rest
                    argv, env = runner(f"image_{kmodel}", a, b, "keyframes.csv")
                    steps.append({"label": f"Movie {mv['id']} keyframes {kmodel}: rows {a}-{b}", "argv": argv, "env": env})
                    kf_steps += 1
            if st.get("video"):
                for m in vmodels:
                    if (m, s, e) not in done:
                        done.add((m, s, e)); argv, env = runner(m, s, e, vcsv)
                        if m in I2V_MODELS and kmodel:
                            env["KEYFRAME_MODEL"] = kmodel           # else the run script uses the newest keyframe set
                        steps.append({"label": f"Movie {mv['id']} video {m}: rows {s}-{e}", "argv": argv, "env": env})
            if st.get("audio"):
                for k in akinds:
                    if k == "musicgen" and music_bed:         # one cue per chapter (or scene) instead, below
                        continue
                    if (k, s, e) not in done:
                        done.add((k, s, e)); argv, env = runner(f"audio_{k}", s, e, acsv)
                        steps.append({"label": f"Movie {mv['id']} audio {k}: rows {s}-{e}", "argv": argv, "env": env})
    if st.get("audio") and music_scenes and "musicgen" in akinds:
        scene_labels = [r.get("chapter", "") for r in read_csv_rows(pdir(slug) / "audio_scenes.csv")]
        shot_scene = [r.get("scene", "") for r in read_csv_rows(pdir(slug) / "audio_shots.csv")]
        for mv in chosen:
            need = sorted({scene_labels.index(x) + 1 for x in shot_scene[mv["rows"][0] - 1: mv["rows"][1]] if x in scene_labels})
            for s, e in chunks_of(need):
                if ("scene", s, e) not in done:
                    done.add(("scene", s, e)); argv, env = runner("audio_musicgen", s, e, "audio_scenes.csv")
                    steps.append({"label": f"Movie {mv['id']} music, one cue per scene: scenes {s}-{e}", "argv": argv, "env": env})
    elif st.get("audio") and music_bed and "musicgen" in akinds:
        labels = [r.get("chapter", "") for r in read_csv_rows(pdir(slug) / "audio_chapters.csv")]
        for mv in chosen:
            if mv["first_chapter"] in labels and mv["last_chapter"] in labels:
                s, e = labels.index(mv["first_chapter"]) + 1, labels.index(mv["last_chapter"]) + 1
                if ("cue", s, e) not in done:
                    done.add(("cue", s, e)); argv, env = runner("audio_musicgen", s, e, "audio_chapters.csv")
                    steps.append({"label": f"Movie {mv['id']} music, one cue per chapter: chapters {s}-{e}", "argv": argv, "env": env})
    uv = ["uv", "run", "--with", "imageio-ffmpeg", "python"]
    for mv in chosen:
        lo, hi = mv["rows"]
        name = f"{slug}-movie-{mv['id']:02d}{suf}"
        for m in vmodels:
            if st.get("merge"):
                steps.append({"label": f"Movie {mv['id']} silent film ({m})", "env": {},
                              "argv": uv + ["merge_videos.py", f"videos/{m}{suf}", f"{name}_{m}_silent.mp4", "--project", slug,
                                            "--start", str(lo), "--end", str(hi)]})
            if st.get("mix"):
                steps.append({"label": f"Movie {mv['id']} final film with audio ({m})", "env": {},
                              "argv": uv + ["mix_film.py", "--project", slug, "--model", m, "--start", str(lo), "--end", str(hi),
                                            "--sync", sync, "--out", f"{name}_{m}.mp4",
                                            "--vol-narration", str(vols["narration"]), "--vol-sfx", str(vols["sfx"]),
                                            "--vol-music", str(vols["music"])] + (["--chapters"] if chapters_mode else []) + sound_flags(opt, music_bed, music_scenes)})
    if st.get("keyframes") and not kf_steps and not any(st.get(k) for k in ("video", "audio", "merge", "mix")):
        raise PlanError(f"every shot of the chosen movies already has a picture from {kmodel}: nothing to make "
                        "(say no to a picture on the storyboard and re-roll it to make it again)")
    return steps


def clean_stages(stages):
    """A character's life stages from the page: a list of {"label", "chapters", "token"}. PlanError says what is wrong with one."""
    out = []
    for st in stages or []:
        label, chapters, token = (str((st or {}).get(k) or "").strip() for k in ("label", "chapters", "token"))
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9 _-]{0,39}", label):
            raise PlanError(f"life stage {label!r}: give it a short name with letters or digits")
        if not re.fullmatch(r"\d{1,4}(-\d{0,4})?", chapters):
            raise PlanError(f"life stage {label}: chapters must look like 5, 5-12 or 13-")
        if not token or len(token) > 400:
            raise PlanError(f"life stage {label}: the description must be 1-400 characters")
        out.append({"label": label, "chapters": chapters, "token": token})
    return out[:8]


def sound_flags(opt, music_bed, scenes=False):
    """mix_film.py options for the page's sound choices. Ducking and the loudness pass are on unless the page says no. scenes: music follows the scenes."""
    return (["--no-duck"] if opt.get("duck") is False else []) + (["--no-loudnorm"] if opt.get("loudnorm") is False else []) + (
        ["--music-scenes"] if scenes else ["--music-bed"] if music_bed else []) + (["--grade"] if opt.get("grade") else []) + (["--credits"] if opt.get("credits") else [])


def keyframe_size(image_model, video_model, aspect=""):
    """Keyframe size: the film's shape (else the video's) at about the image model's usual pixel count, in multiples of 64 (so it suits every image model)."""
    v, i = MODEL_DEFAULTS.get(video_model, MODEL_DEFAULTS["ltx_video"]), MODEL_DEFAULTS.get(image_model, {"width": 1024, "height": 1024})
    ratio, area = ASPECTS.get(aspect) or v["width"] / v["height"], i["width"] * i["height"]
    w = max(256, min(2048, round((area * ratio) ** 0.5 / 64) * 64))
    h = max(256, min(2048, round(w / ratio / 64) * 64))
    return w, h
