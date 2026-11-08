"""How to write a good prompt for each generation model, used by the AI Prompt Writer.

Every model family likes a different style: some want one flowing paragraph, some want comma-separated tags, some read only about 200 words.
`guide_for(kind, model)` returns the rules for the model the prompts are written for; `writer_system(kind, model)` is the system prompt the
writing AI gets. A model name that is not listed gets the general rules for its kind. To teach the writer about a new model, add it to FAMILY.
"""

VIDEO_BASE = (
    "A strong video prompt is ONE clip: a clear subject, what that subject DOES over the clip (named motion, in the order it happens), the camera "
    "movement, the setting, the light and the look. Prefer concrete visual words to feelings. Describe motion that fits the clip length (one or two "
    "actions, never a whole story). Say what is in focus and what is soft. No on-screen text, no logos, no cuts or scene changes, nothing that "
    "depends on another prompt.")

IMAGE_BASE = (
    "A strong image prompt names the subject and its pose or expression, the setting and background, the composition and framing, the light, "
    "the colours, the medium or camera and lens, and the level of detail. Prefer concrete visual words to feelings. No on-screen text unless the "
    "idea needs it, no logos.")

# family -> (kind, words, style rules)
GUIDES = {
    "ltx": ("video", "60-120 words",
            "LTX-Video likes ONE flowing paragraph in the present tense that reads like a shot description. Start with the main action, then movement "
            "details, the look of the subject, the background, the camera angle and movement, and the lighting, in that order."),
    "wan": ("video", "80-120 words",
            "Wan follows this order: subject, scene, motion, camera, light and aesthetic. Use plain descriptive sentences. Name the camera move "
            "explicitly (slow dolly in, handheld, orbit, low angle, aerial). Mention the style words once (cinematic, documentary, 35mm film)."),
    "hunyuan": ("video", "60-110 words",
                "HunyuanVideo reads natural sentences: subject, scene, motion, camera work and atmosphere. It has no negative prompt, so state what "
                "you want and avoid describing what you do not want. Realistic detail and physical motion work best."),
    "cogvideox": ("video", "50-90 words",
                  "CogVideoX reads only about 226 tokens, so keep it compact: subject, action, setting, camera and style in one or two sentences. "
                  "Put the most important content first."),
    "sdxl": ("image", "20-50 words",
             "SDXL-family models like a short natural description followed by a few comma-separated style and quality phrases (photorealistic, sharp "
             "focus, 85mm, soft light). Keep it under about 60 words; put the subject first."),
    "danbooru": ("image", "25-60 tags",
                 "Illustrious and NoobAI are trained on tag captions: write comma-separated lowercase tags. Start with the subject count and kind "
                 "(1girl, 1boy, solo), then character traits, clothing, pose, setting, light, then style and quality tags (masterpiece, best quality, "
                 "very aesthetic, absurdres). No full sentences."),
    "natural": ("image", "40-90 words",
                "This model understands full natural-language sentences. Write one or two clear sentences that describe the whole picture the way a "
                "photographer or art director would, with the subject first. Quality tags are not needed."),
}

FAMILY = {
    # video
    "ltx_video": "ltx", "wan": "wan", "wan22_ti2v_5b": "wan", "wan22_t2v_a14b": "wan", "wan22_t2v_a14b_lora": "wan", "wan22_t2v_a14b_lightning": "wan",
    "tpu_wan": "wan", "hunyuan_video": "hunyuan", "hunyuan_video_lora": "hunyuan", "hunyuan_video_15": "hunyuan",
    "cogvideox": "cogvideox", "cogvideox_5b": "cogvideox",
    # image
    "sdxl": "sdxl", "sdxl_turbo": "sdxl", "realvisxl_v5": "sdxl", "illustrious_xl": "danbooru", "noobai_xl": "danbooru",
}
IMAGE_NATURAL = ("flux", "z_image", "qwen_image", "moss_", "sd35", "chroma", "ernie")      # name prefixes of the natural-language image models


def family_for(kind, model):
    model = (model or "").removeprefix("image_")
    if model in FAMILY:
        return FAMILY[model]
    if kind == "image" and model.startswith(IMAGE_NATURAL):
        return "natural"
    return ""


def guide_for(kind, model=None):
    """(rules text, length hint) for the model the prompts are for; the general rules for the kind when the model is unknown."""
    fam = family_for(kind, model)
    base = VIDEO_BASE if kind == "video" else IMAGE_BASE
    if fam and fam in GUIDES and GUIDES[fam][0] == kind:
        _, words, rules = GUIDES[fam]
        return f"{base} Target model: {model}. Length: {words}. {rules}", words
    return base + (" Length: 50-90 words." if kind == "video" else " Length: 30-70 words."), ("50-90 words" if kind == "video" else "30-70 words")


def writer_system(kind, model=None):
    """The system prompt for the writing AI (any engine)."""
    rules, _ = guide_for(kind, model)
    return (f"You are an expert prompt writer for {kind} generation models. You write vivid, specific, production-ready prompts. {rules} "
            "Reply with a single JSON object and nothing else.")


def review_system():
    return ("You are a careful reviewer of AI-generated pictures and video frames. You compare a result with the prompt that made it and judge only what "
            "you can see. You reply with a single JSON object and nothing else.")
