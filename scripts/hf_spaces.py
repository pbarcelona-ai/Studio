"""Studio models that can run on Hugging Face, through a public Space (ZeroGPU: Hugging Face's shared GPUs, free daily quota).

One entry per Studio model. "style" says how run_hf_space.py builds the call; "defaults" are used when the prompt row leaves a box blank.
A Space runs the author's own version of the model and only exposes the controls it has, so results differ a little from the Kaggle notebooks.
To add a model: add an entry here (and a style in run_hf_space.py if the Space's API is new), then test it with a real call.
Status values: checked = the call was made on a real Space; api = the Space's API was read but no picture has been made through it yet.
"""

SPACES = {
    "flux1_schnell": {"kind": "image", "space": "black-forest-labs/FLUX.1-schnell", "style": "flux", "api": "/infer",
                      "defaults": {"width": 1024, "height": 1024, "steps": 4}, "status": "checked"},
    "flux1_dev": {"kind": "image", "space": "black-forest-labs/FLUX.1-dev", "style": "flux", "api": "/infer",
                  "defaults": {"width": 1024, "height": 1024, "steps": 28, "guidance": 3.5}, "status": "api"},
    "sd35_large": {"kind": "image", "space": "stabilityai/stable-diffusion-3.5-large", "style": "sd35", "api": "/infer",
                   "defaults": {"width": 1024, "height": 1024, "steps": 28, "guidance": 4.5}, "status": "api"},
    "sd35_large_turbo": {"kind": "image", "space": "stabilityai/stable-diffusion-3.5-large-turbo", "style": "sd35", "api": "/infer",
                         "defaults": {"width": 1024, "height": 1024, "steps": 4, "guidance": 0.0}, "status": "api"},
    "flux2_klein_4b": {"kind": "image", "space": "black-forest-labs/FLUX.2-klein-4B", "style": "klein", "api": "/infer",
                       "defaults": {"width": 1024, "height": 1024, "steps": 4, "guidance": 1.0}, "status": "api"},
    # The Space you used: uncensored Qwen-Image-2.1 (the 4-bit GGUF) with optional LoRAs; "None (Base Uncensored)" is the same model as qwen_image_21_uc.
    "qwen_image_21_uc": {"kind": "image", "space": "Guaryn/qwen-image-2.1-uncensored-aio-loras", "style": "qwen_aio", "api": "/generate",
                         "defaults": {"width": 1024, "height": 1024, "steps": 30}, "status": "checked"},
    # Pika H3 Flex (a post-training of MiniMax-H3; MiniMax H3 Community Licence, ask MiniMax if you are in the USA, EU, UK or South Korea): far too big for a free GPU,
    # but the public Space animates a keyframe, about 33 s of GPU for a 5 s clip at 832x480.
    "pika_h3_flex_i2v": {"kind": "video", "space": "Pika-Labs/pika-h3-flex", "style": "pika", "api": "/generate", "defaults": {"seconds": 5, "resolution": "480p"}, "status": "checked"},
    "cogvideox_5b": {"kind": "video", "space": "zai-org/CogVideoX-5B-Space", "style": "cogvideox", "api": "/generate",
                     "defaults": {}, "status": "api"},
}

# aspect ratios the Qwen AIO Space offers
QWEN_AIO_SIZES = {
    "Square · 1:1 (1024x1024)": (1024, 1024), "Landscape · 16:9 (1344x768)": (1344, 768), "Portrait · 9:16 (768x1344)": (768, 1344),
    "Landscape · 4:3 (1152x864)": (1152, 864), "Portrait · 3:4 (864x1152)": (864, 1152),
}
