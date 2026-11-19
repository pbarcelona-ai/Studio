"""The look of the film (live action, claymation, 3D animated, hybrid, vintage travel poster, cyberpunk neon 3D) and which models the Studio suggests for each step of making it.

The Studio page shows the looks as buttons (one at a time) and asks suggest() which model to use for every step: pictures, keyframes,
video clips (from keyframes or from text), narration, music and upscaling. A suggestion is the first model in the step's list that can run
where the person chose to run (Kaggle, Colab, Hugging Face or this computer) and fits that GPU's memory; the rest are offered as
alternatives. The reasons say what is known about each model here (tested on a Kaggle T4, takes character pictures, speed); they are
starting points, not measurements of how well a model draws each look.

Each look also has style words: STYLE[look]["positives"] / ["negatives"] go into the Global Parameters (every prompt written for a book and
every character picture), lead() starts each keyframe prompt, and apply_look() adds them to Single Prompts rows.
"""

LOOKS = {   # id -> label on the button, one-line description
    "live_action": ("Realistic live action", "Cinematic, as if filmed with a camera: real people, real places, natural light."),
    "claymation": ("Claymation", "Stop-motion with handmade clay figures and miniature sets."),
    "pixar_3d": ("3D Pixar", "A 3D animated feature: stylised characters, soft light, rich colour."),
    "pixar_disney": ("Pixar-Disney hybrid", "3D animation with a classic storybook, hand-drawn fairy-tale feel."),
    "travel_poster": ("Vintage travel poster", "Flat, bold shapes in a few printed colours, like a 1930s railway or airline poster."),
    "cyberpunk_3d": ("Cyberpunk neon 3D", "A 3D-rendered neon city at night: glowing signs, rain, fog and reflections."),
}
DEFAULT_LOOK = "live_action"

STYLE = {
    "live_action": {
        "lead": "Cinematic live-action film still, shot on a cinema camera",
        "positives": "cinematic live-action film still, shot on a cinema camera, 35mm anamorphic lens, natural film grain, realistic skin texture, practical lighting, shallow depth of field",
        "negatives": "cartoon, animated, 3d render, cgi, claymation, plasticine, illustration, anime, painting, drawing, doll-like, plastic skin",
    },
    "claymation": {
        "lead": "Claymation stop-motion film still, handmade plasticine figures on a miniature set",
        "positives": "claymation stop-motion film, handcrafted plasticine figures, visible fingerprints and tool marks in the clay, miniature handmade sets, soft studio lighting, tactile textures",
        "negatives": "photorealistic, live action, photograph, real people, smooth cgi, anime, 2d drawing, glossy plastic",
    },
    "pixar_3d": {
        "lead": "3D animated feature film still, stylised characters, soft global illumination",
        "positives": "3d animated feature film style, stylised characters with large expressive eyes, soft rounded shapes, subsurface scattering, warm global illumination, rich saturated colour",
        "negatives": "photorealistic, live action, photograph, real people, claymation, anime, flat 2d drawing, uncanny realistic skin",
    },
    "pixar_disney": {
        "lead": "3D animated fairy-tale film still with a hand-drawn storybook feel",
        "positives": "3d animated feature with a classic hand-drawn fairy-tale feel, painterly textures, storybook lighting, expressive faces, graceful character animation, lush colour",
        "negatives": "photorealistic, live action, photograph, real people, claymation, anime, gritty, uncanny realistic skin",
    },
    "travel_poster": {
        "lead": "Vintage travel poster illustration, flat bold shapes, limited printed colour palette",
        "positives": "vintage travel poster style, 1930s art deco lithograph, flat bold shapes, limited colour palette, screen-print grain, strong silhouettes, sweeping perspective, sunlit sky gradients",
        "negatives": "photorealistic, photograph, live action, 3d render, cgi, glossy, anime, cluttered detail, garbled lettering, watermark",
    },
    "cyberpunk_3d": {
        "lead": "Cyberpunk neon 3D render, glowing signs, night city",
        "positives": "cyberpunk neon 3d render, night city, glowing magenta and cyan neon signs, rain-slick reflective streets, volumetric fog, holographic displays, rim lighting, high contrast",
        "negatives": "daylight, pastoral, vintage, flat 2d drawing, watercolor, claymation, washed-out colours, low contrast",
    },
}

STEPS = {   # id -> (title, where it is chosen on the page)
    "screenplay": ("Screenplay & Story Beats", "Step 05: Screenplay Editor"),
    "image": ("Pictures & Turnarounds", "Step 11: Look Development"),
    "keyframe": ("Keyframe stills", "Step 15: Storyboard Keyframes"),
    "video_i2v": ("Video clips from keyframes", "Step 16: Motion & Video Synthesis"),
    "video_t2v": ("Video clips from text", "Models tab: Video Models"),
    "dialogue": ("Spoken Dialogue", "Step 12: Voice Casting & Step 13: Dialogue Delivery"),
    "narration": ("Narration", "Step 12: Voice Casting"),
    "foley": ("Sound FX & Foley", "Step 14: Score & Foley"),
    "music": ("Music Score", "Step 14: Score & Foley"),
    "upscale": ("Upscaling & Polish", "Step 17: Visual Polish & Step 20: Premiere"),
}

# Per step, in order of preference: (model, why, least GPU GB for this to be the pick or None). An entry with a GB figure is skipped
# when the chosen GPU is known to be smaller (it would be slow or swap), so a T4 gets the next one; unknown GPUs skip nothing.
_FLUX_DEV = ("flux1_dev", "FLUX.1-dev: State-of-the-art cinematic lighting, hands, and detail", None)
_FLUX2 = ("flux2_klein_4b", "FLUX.2 Klein: Fast 4-step FLUX with character reference support (tested on a T4)", None)
_SDXL_LIGHT = ("sdxl_lightning", "SDXL-Lightning: 4-step ultra-fast storyboard drafting", None)
_SDXL = ("sdxl", "SDXL: Reliable baseline, runs anywhere (tested on a T4)", None)

_KEYFRAMES = [
    _FLUX_DEV,
    _SDXL_LIGHT,
    _FLUX2,
    ("z_image_turbo", "good detail in few steps, no character pictures (tested on a T4, about 16 minutes)", None),
    ("flux1_schnell", "fast FLUX, no character pictures (tested on a T4)", None),
]

_I2V = [
    ("wan21_i2v_14b", "Wan 2.1 14B I2V: Best-in-class motion physics, cloth/hair dynamics and 720p native resolution", None),
    ("pika_h3_flex_i2v", "by far the best faces and motion we have seen, with 5 s clips; runs on public HF Space", None),
    ("ltx_video_fast_i2v", "tested on a T4: about 2 minutes a clip at 672x384, with cleaner faces than 40-step LTX", None),
    ("wan22_ti2v_5b_i2v", "for GPUs with room: on a T4 it took about 13 minutes for a 1.4 s clip and smeared small faces", 22),
    ("ltx_video_i2v", "tested on a T4: about 10 minutes a clip, opens exactly on its keyframe", None),
]

_STYLISED_T2V = [
    ("wan22_t2v_a14b_lightning", "Wan 2.2 14B in 4 steps: the best Wan quality at about 8 minutes (tested on a T4)", None),
    ("wan22_ti2v_5b", "Wan 2.2 5B at 24 fps (tested on a T4, about 20 minutes)", None),
    ("ltx_video", "fastest video model, for trying ideas", None),
]

_VOICE = {
    "screenplay": [("qwen25_72b", "Qwen 2.5 72B Instruct: Screenplay specialist with realistic dialogue banter", None),
                   ("llama33_70b", "Llama 3.3 70B: High coherence scene beat extraction", None)],
    "dialogue": [("kokoro", "Kokoro-82M: Dialogue-first default with American vs British dialect mapping", None),
                 ("f5_tts", "F5-TTS: Zero-shot voice cloning and expressive inflection", None),
                 ("qwen3_tts", "Qwen3 TTS: Natural multi-speaker voice delivery", None)],
    "narration": [("kokoro", "Kokoro-82M: Uses your Voice Cast (one voice per character); fast, tested", None),
                  ("chatterbox_turbo", "more natural single voice; ignores the Voice Cast", None),
                  ("qwen3_tts", "newer natural voices; ignores the Voice Cast", None)],
    "foley": [("mmaudio", "MMAudio: Synchronized video-to-audio foley effects and ambient sound", None),
              ("audioldm2", "AudioLDM2: Text-to-SFX sound effects", None)],
    "music": [("musicgen", "MusicGen: Background score from the shot's dramatic music cue (tested)", None),
              ("stable_audio", "Stable Audio Open: Atmospheric soundtracks", None)],
}

_UP_CLEAN = [
    ("upscale_seedvr2_3b", "diffusion upscaler: real detail for camera footage; wants 24 GB for full speed", 22),
    ("upscale_flashvsr", "near SeedVR2 detail, much faster; Ampere or newer GPU only", 16),
    ("upscale_x2", "Real-ESRGAN: quick and light, works on any GPU (tested on a T4)", None),
]
_UP_STYLISED = [
    ("upscale_x2", "Real-ESRGAN keeps flat colour and clean edges as they are (tested on a T4)", None),
    ("upscale_seedvr2_3b", "more detail, but a diffusion upscaler may add photo-like texture to a stylised look", 22),
]

SUGGEST: dict[str, dict[str, list[tuple]]] = {
    "live_action": {
        "image": [_FLUX2, ("z_image_turbo", "strong photographic detail (tested on a T4, about 16 minutes)", None),
                  ("realvisxl_v5", "photoreal SDXL, about 3 minutes on a T4", None)],
        "keyframe": _KEYFRAMES,
        "video_i2v": _I2V,
        "video_t2v": [("wan22_t2v_a14b_lightning", "Wan 2.2 14B in 4 steps: the best Wan quality at about 8 minutes (tested on a T4)", None),
                      ("hunyuan_video_15", "realistic motion (tested on a T4, about 30 minutes)", None),
                      ("ltx_video", "fastest video model, for trying ideas", None)],
        **_VOICE,
        "upscale": _UP_CLEAN,
    },
    "claymation": {
        "image": [_FLUX2, ("qwen_image_21", "follows long style descriptions closely; slow (about an hour a picture on a T4)", 22),
                  ("qwen_image_21_turbo", "Qwen-Image in fewer steps (tested on a T4, about 15 minutes)", None), _SDXL],
        "keyframe": _KEYFRAMES,
        "video_i2v": _I2V,
        "video_t2v": _STYLISED_T2V,
        **_VOICE,
        "upscale": _UP_STYLISED,
    },
    "pixar_3d": {
        "image": [("qwen_image_21", "follows long style descriptions closely; slow (about an hour a picture on a T4)", 22), _FLUX2,
                  ("qwen_image_21_turbo", "Qwen-Image in fewer steps (tested on a T4, about 15 minutes)", None), _SDXL],
        "keyframe": _KEYFRAMES,
        "video_i2v": _I2V,
        "video_t2v": _STYLISED_T2V,
        **_VOICE,
        "upscale": _UP_STYLISED,
    },
    "pixar_disney": {
        "image": [("qwen_image_21", "follows long style descriptions closely; slow (about an hour a picture on a T4)", 22), _FLUX2,
                  ("qwen_image_21_turbo", "Qwen-Image in fewer steps (tested on a T4, about 15 minutes)", None), _SDXL],
        "keyframe": _KEYFRAMES,
        "video_i2v": _I2V,
        "video_t2v": _STYLISED_T2V,
        **_VOICE,
        "upscale": _UP_STYLISED,
    },
}
# The two newer looks reuse the stylised lists above; their reasons stay true for any look.
SUGGEST["travel_poster"] = {
    "image": [("qwen_image_21", "follows long style descriptions closely and is good at graphic layouts; slow (about an hour a picture on a T4)", 22), _FLUX2,
              ("qwen_image_21_turbo", "Qwen-Image in fewer steps (tested on a T4, about 15 minutes)", None), _SDXL],
    "keyframe": _KEYFRAMES,
    "video_i2v": _I2V,
    "video_t2v": _STYLISED_T2V,
    **_VOICE,
    "upscale": _UP_STYLISED,
}
SUGGEST["cyberpunk_3d"] = {
    "image": [_FLUX2, ("qwen_image_21", "follows long style descriptions closely; slow (about an hour a picture on a T4)", 22),
              ("z_image_turbo", "fine detail in few steps (tested on a T4, about 16 minutes)", None), _SDXL],
    "keyframe": _KEYFRAMES,
    "video_i2v": _I2V,
    "video_t2v": _STYLISED_T2V,
    **_VOICE,
    "upscale": _UP_STYLISED,
}
GENERIC_NEGATIVE = "blurry, low quality, deformed, watermark, text"


def look_or_default(look):
    return look if look in LOOKS else DEFAULT_LOOK


def lead(look):
    """How a keyframe prompt starts for this look (make_keyframes_csv.py)."""
    return STYLE[look_or_default(look)]["lead"]


def apply_look(prompt, negative, look, takes_negative=True):
    """(prompt, negative) for a Single Prompts row with the look's style words added; nothing is added twice. look "" leaves both as typed."""
    if look not in LOOKS:
        return prompt, negative
    st = STYLE[look]
    if st["positives"].split(",")[0].strip().lower() not in prompt.lower():
        prompt = f"{prompt.rstrip(' ,.')}, {st['positives']}"
    if takes_negative:
        negative = ", ".join(x for x in (negative.strip(" ,"), st["negatives"], GENERIC_NEGATIVE if not negative.strip() else "") if x)
    return prompt, negative


def suggest(look, blocker=None, gpu_gb=None):
    """{step: {"title", "where", "pick": {model, why} or None, "alternatives": [{model, why, blocked}]}} for this look.
    blocker(model) -> reason or None (from the Studio's model_blocker for the chosen service and GPU); gpu_gb: that GPU's memory, or None."""
    blocker = blocker or (lambda m: None)
    out: dict = {}
    for step, (title, where) in STEPS.items():
        pick: dict | None = None
        alts: list[dict] = []
        for model, why, least in SUGGEST[look_or_default(look)][step]:
            why_not = blocker(model)
            small = least is not None and gpu_gb is not None and gpu_gb < least
            if pick is None and not why_not and not small:
                pick = {"model": model, "why": why}
            else:
                alts.append({"model": model, "why": why,
                             "blocked": why_not or (f"best with {least} GB of GPU memory or more; this GPU has {gpu_gb:g} GB" if small else "")})
        if pick is None:                         # everything is too big or blocked: fall back to the first one that can run at all
            ok = next((a for a in alts if not blocker(a["model"])), None)
            if ok:
                pick = {"model": ok["model"], "why": ok["why"] + " (slower on this GPU)"}
                alts = [a for a in alts if a is not ok]
        out[step] = {"title": title, "where": where, "pick": pick, "alternatives": alts}
    return out


def autopilot_recommend(look, step, shot_type=None, hardware=None):
    """Intelligent Autopilot model recommendation for any step, shot type, and hardware.

    Returns a dict with model, label, why, execution_target, dialect, and voice_mode.
    """
    look = look_or_default(look)
    shot_type = (shot_type or "").lower()
    hardware = (hardware or "auto").lower()

    # Step-specific autopilot rules
    if step in ("dialogue", "voice", "step_12", "step_13"):
        return {
            "model": "kokoro",
            "label": "Kokoro-82M (Dialogue-First)",
            "why": "Ultra-fast neural speech synthesis with American and British dialect switching per character.",
            "execution_target": "local",
            "dialect": "american",
            "voice_mode": "dialogue",
        }
    elif step in ("keyframe", "step_15"):
        if "close" in shot_type or "face" in shot_type:
            return {
                "model": "flux1_dev",
                "label": "FLUX.1-dev + InstantID",
                "why": "High-fidelity facial detail and character consistency for dialogue close-ups.",
                "execution_target": "huggingface" if hardware in ("auto", "mac", "cpu") else "local",
                "dialect": "american",
                "voice_mode": "dialogue",
            }
        return {
            "model": "flux1_dev",
            "label": "FLUX.1-dev (Cinematic)",
            "why": "Cinematic lighting, depth, and anatomical accuracy aligned to your style recipe.",
            "execution_target": "huggingface" if hardware in ("auto", "mac", "cpu") else "local",
            "dialect": "american",
            "voice_mode": "dialogue",
        }
    elif step in ("video", "video_i2v", "step_16"):
        if "fast" in hardware or "t4" in hardware:
            return {
                "model": "ltx_video_fast_i2v",
                "label": "LTX-Video (High Speed)",
                "why": "Rapid motion synthesis optimized for responsive preview on lightweight GPUs.",
                "execution_target": "kaggle" if "kaggle" in hardware else "huggingface",
                "dialect": "american",
                "voice_mode": "dialogue",
            }
        return {
            "model": "wan21_i2v_14b",
            "label": "Wan 2.1 14B I2V (720p Master)",
            "why": "Leading physical dynamics, cloth motion, and camera stability.",
            "execution_target": "huggingface" if hardware in ("auto", "mac", "cpu") else "cloud_api",
            "dialect": "american",
            "voice_mode": "dialogue",
        }
    elif step in ("foley", "sfx"):
        return {
            "model": "mmaudio",
            "label": "MMAudio (Video-Aligned Foley)",
            "why": "Synchronized footsteps, atmospheric ambiances, and movement effects keyed directly to video frames.",
            "execution_target": "local",
            "dialect": "american",
            "voice_mode": "dialogue",
        }
    elif step in ("music", "score"):
        return {
            "model": "musicgen",
            "label": "MusicGen Stereo (Cinematic Score)",
            "why": "Orchestral and thematic cues matched to scene emotion and pacing.",
            "execution_target": "local",
            "dialect": "american",
            "voice_mode": "dialogue",
        }
    elif step in ("screenplay", "step_05"):
        return {
            "model": "qwen25_72b",
            "label": "Qwen 2.5 72B Instruct (Screenplay Specialist)",
            "why": "Dialogue-first adaptation preserving story tone, character banter, and dramatic beats.",
            "execution_target": "cloud_api",
            "dialect": "american",
            "voice_mode": "dialogue",
        }
    elif step in ("upscale", "step_17", "step_20"):
        return {
            "model": "upscale_x2",
            "label": "Real-ESRGAN x2 (Clean Super-Resolution)",
            "why": "Fast artifact-free 2x super-resolution for final film mastering.",
            "execution_target": "local",
            "dialect": "american",
            "voice_mode": "dialogue",
        }

    # Default fallback to standard suggest()
    s = suggest(look)
    step_key = step if step in s else "keyframe"
    pick = s.get(step_key, {}).get("pick") or {"model": "flux1_dev", "why": "Default studio visual recommendation."}
    return {
        "model": pick["model"],
        "label": pick["model"].replace("_", " ").title(),
        "why": pick["why"],
        "execution_target": "local",
        "dialect": "american",
        "voice_mode": "dialogue",
    }
