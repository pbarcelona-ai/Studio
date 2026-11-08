"""Generate the text-to-image scripts and notebooks. Run: python3 scripts/make_image.py

For each model below this writes   colab_generate_image_<key>.py      (runs on the VM via the Colab CLI)
                                   Studio_Kaggle_image_<key>.ipynb      and   Studio_Colab_image_<key>.ipynb
Rows come from a CSV with columns  chapter,shot,prompt  plus optional  negative,width,height,steps,guidance,seed.
Output: image-NNNN.png (NNNN = CSV row number).
"""
import json
from pathlib import Path
import os as _os
root = Path(_os.environ["STUDIO_GEN_DIR"]) if _os.environ.get("STUDIO_GEN_DIR") else Path(__file__).resolve().parent.parent   # STUDIO_GEN_DIR: write somewhere else (the run scripts use a throw-away folder)

HEADER = '''import csv, os, tarfile, time
from pathlib import Path

os.environ.setdefault('PYTORCH_CUDA_ALLOC_CONF', 'expandable_segments:True')     # less memory fragmentation; must be set before torch loads
import torch

# Injected by run_colab_model.sh / the notebooks; defaults suit `colab exec` on a fresh VM.
START = globals().get("START", 1)
END = globals().get("END", 5)
CSV_PATH = globals().get("CSV_PATH", "/content/all_shots.csv")
OUT = Path(globals().get("OUT", "/content/images"))
MAKE_TAR = globals().get("MAKE_TAR", True)
OUT.mkdir(parents=True, exist_ok=True)
rows = list(csv.DictReader(open(CSV_PATH, newline="")))
END = min(END, len(rows))
HF_TOKEN = os.environ.get("HF_TOKEN") or None      # only needed for gated models (Stable Diffusion 3.5)


def opt(row, key, default, cast=int):
    """Per-row setting from the CSV (blank/missing -> the default above)."""
    v = row.get(key)
    return cast(v) if v not in (None, "") else default

'''

LOOP = '''
failed = []
for i in range(START, END + 1):
    out = OUT / f"image-{i:04d}.png"
    if out.exists():
        continue
    t = time.time()
    try:
        generate(rows[i - 1], opt(rows[i - 1], "seed", i)).save(out)
        print(f"[{i}/{END}] ok ({time.time() - t:.0f}s)", flush=True)
    except Exception as e:
        torch.cuda.empty_cache(); failed.append(i)
        print(f"[{i}/{END}] FAILED: {e}", flush=True)

if MAKE_TAR:
    tar = f"/content/batch_{START}_{END}.tar"
    with tarfile.open(tar, "w") as tf:
        for p in sorted(OUT.glob("image-*.png")):
            tf.add(p, arcname=p.name)
    print("tar:", tar)
print("failed:", failed or "none")
if failed and len(failed) == END - START + 1:
    raise RuntimeError(f"all {len(failed)} image(s) failed; see the messages above")
'''

MODELS = {
"sdxl_turbo": dict(title="SDXL-Turbo", repo="stabilityai/sdxl-turbo",
  note="Fastest option: 1-4 steps, 512x512 by default, a few seconds per image on a T4. Good for trying ideas. Not gated.",
  config='MODEL_ID = "stabilityai/sdxl-turbo"\nWIDTH, HEIGHT = 512, 512\nSTEPS = 4\nGUIDANCE = 0.0          # Turbo is trained without guidance',
  load='from diffusers import AutoPipelineForText2Image\n\npipe = AutoPipelineForText2Image.from_pretrained(MODEL_ID, torch_dtype=torch.float16, variant="fp16").to("cuda")',
  gen='''def generate(row, seed):
    return pipe(prompt=row["prompt"], negative_prompt=row.get("negative") or None,
                width=opt(row, "width", WIDTH), height=opt(row, "height", HEIGHT),
                num_inference_steps=opt(row, "steps", STEPS), guidance_scale=opt(row, "guidance", GUIDANCE, float),
                generator=torch.Generator("cuda").manual_seed(seed)).images[0]'''),
"sdxl": dict(title="Stable Diffusion XL", repo="stabilityai/stable-diffusion-xl-base-1.0",
  note="Higher quality than Turbo: 1024x1024, 30 steps, roughly 20-40 s per image on a T4. Fits in 16 GB. Not gated.",
  config='MODEL_ID = "stabilityai/stable-diffusion-xl-base-1.0"\nWIDTH, HEIGHT = 1024, 1024\nSTEPS = 30\nGUIDANCE = 7.0',
  load='from diffusers import StableDiffusionXLPipeline\n\npipe = StableDiffusionXLPipeline.from_pretrained(MODEL_ID, torch_dtype=torch.float16, variant="fp16", use_safetensors=True).to("cuda")\npipe.vae.enable_slicing()',
  gen='''def generate(row, seed):
    return pipe(prompt=row["prompt"], negative_prompt=row.get("negative") or "blurry, low quality, distorted, text, watermark",
                width=opt(row, "width", WIDTH), height=opt(row, "height", HEIGHT),
                num_inference_steps=opt(row, "steps", STEPS), guidance_scale=opt(row, "guidance", GUIDANCE, float),
                generator=torch.Generator("cuda").manual_seed(seed)).images[0]'''),
}


def _moss(key_title, repo, note):
    return dict(title=key_title, repo=repo, note=note,
  config=f'MODEL_ID = "{repo}"\nWIDTH, HEIGHT = 1024, 1024    # must be multiples of 16\nSTEPS = 50\nGUIDANCE = 3.0',
  load=('from diffusers import DiffusionPipeline\n\n# Needs diffusers>=0.38 and transformers>=5.3 (the pip cell upgrades them). The pipeline code is downloaded from the model repo\n'
        '# (trust_remote_code), as the model card instructs. ~25 GB of weights: the transformer and text encoder are bf16, the VAE fp32.\n'
        'pipe = DiffusionPipeline.from_pretrained(MODEL_ID, custom_pipeline="pipeline_moss_image", trust_remote_code=True,\n'
        '                                         torch_dtype={"default": torch.bfloat16, "vae": torch.float32}, token=HF_TOKEN)\n'
        'pipe.scheduler = type(pipe.scheduler).from_config(pipe.scheduler.config)\n'
        '# The model card uses .to("cuda"). A T4 has 14.5 GB usable and the transformer alone is about 14 GB, so even model-level offload ran out\n'
        '# of memory (first Kaggle run, Oct 27, 2026). Sequential offload streams the weights through the GPU layer by layer: slower, but it fits.\n'
        'pipe.enable_sequential_cpu_offload()\n'
        'try:\n    pipe.vae.enable_tiling()\nexcept Exception:\n    pass'),
  gen='''def generate(row, seed):
    neg = row.get("negative") or None
    extra = {"negative_prompt": neg, "uncond_skip_layers": []} if neg else {"uncond_skip_layers": [22]}   # model card defaults
    return pipe(row["prompt"], height=opt(row, "height", HEIGHT), width=opt(row, "width", WIDTH),
                num_inference_steps=opt(row, "steps", STEPS), guidance_scale=opt(row, "guidance", GUIDANCE, float),
                generator=torch.Generator("cpu").manual_seed(seed), **extra).images[0]''')


MODELS["moss_image_sft"] = _moss("MOSS-Image-SFT", "OpenMOSS-Team/MOSS-Image-SFT",
    "General-purpose fine-tuned MOSS-Image (Apache-2.0), 1024x1024, 50 steps with two transformer passes each, so it is slow on a T4 (minutes per image, my expectation). About 25 GB of weights: needs CPU offload and plenty of system RAM (Kaggle's is borderline, Colab free's is not enough). Custom pipeline code from the repo; needs diffusers>=0.38 and transformers>=5.3. EXPERIMENTAL: not tested.")
MODELS["moss_image_base"] = _moss("MOSS-Image-Base", "OpenMOSS-Team/MOSS-Image-Base",
    "The pretrained base of MOSS-Image (Apache-2.0), same size and settings as the SFT version; the SFT version is the one meant for everyday use. EXPERIMENTAL: not tested.")


MODELS["qwen_image_21"] = dict(title="Qwen-Image-2.1", repo="Qwen/Qwen-Image-2.1",
  note="Qwen-Image-2.1 (Qwen Research License, not Apache): 7B image generator, strong text rendering and portraits, 40 steps. Native size is 2048x2048; this default is 1024x1024 so it runs on a T4 (the weights are moved to the GPU layer by layer, so it is slow). No negative prompt or guidance setting is passed. Needs diffusers from GitHub (QwenImage21Pipeline) and transformers>=5.17, which the pip cell installs. EXPERIMENTAL: not tested.",
  pip="!pip install -q -U torch torchvision torchaudio 'transformers>=5.17' accelerate sentencepiece protobuf pillow git+https://github.com/huggingface/diffusers",
  config='MODEL_ID = "Qwen/Qwen-Image-2.1"\nWIDTH, HEIGHT = 1024, 1024\nSTEPS = 40\nGUIDANCE = 0.0   # not used by this model',
  load='from diffusers import QwenImage21Pipeline\n\n# Offload keeps the weights off the GPU until needed (the 7B transformer is 14 GB, too big for a T4 as one piece, so it is moved to the GPU layer by layer).\npipe = QwenImage21Pipeline.from_pretrained(MODEL_ID, torch_dtype=torch.bfloat16, token=HF_TOKEN)\npipe.enable_sequential_cpu_offload()',
  gen='''def generate(row, seed):
    return pipe(prompt=row["prompt"], width=opt(row, "width", WIDTH), height=opt(row, "height", HEIGHT),
                num_inference_steps=opt(row, "steps", STEPS),
                generator=torch.Generator("cuda").manual_seed(seed)).images[0]''')


# --- adult-content variants (community adapters). Both model cards limit use to clearly adult, fictional subjects. ---
MODELS["qwen_image_21_uc"] = dict(title="Qwen-Image-2.1 Uncensored", repo="Qwen/Qwen-Image-2.1",
  note="Qwen-Image-2.1 plus the abenzerps 'uncensored' LoRA, read from the community mirror KasugaiSakura/Qwen-Image-2.1-Uncensored-Abenzerps-GGUF because the original repository was renamed and no longer has it (Qwen Research License). The GGUF / FP8 / MLX files in that repo are ComfyUI formats and are NOT used here; only its 33 MB LoRA is applied to the base model. No safety filter; adult, clearly fictional subjects only. The LoRA ships without a config, so its scale is a guess (1.0). Needs diffusers from GitHub. If the adapter fails to load the run stops, it never falls back to the plain model. EXPERIMENTAL: not tested.",
  pip="!pip install -q -U torch torchvision torchaudio 'transformers>=5.17' accelerate sentencepiece protobuf pillow peft safetensors git+https://github.com/huggingface/diffusers\n!pip uninstall -y -q torchao      # Kaggle ships torchao 0.10, which the new peft rejects; nothing here needs it",
  config='MODEL_ID = "Qwen/Qwen-Image-2.1"\nLORA_REPO = "KasugaiSakura/Qwen-Image-2.1-Uncensored-Abenzerps-GGUF"   # community mirror: abenzerps renamed their repo and removed the LoRA from it\nLORA_FILE = "qwen-image-2.1-uncensored-lora.safetensors"\nLORA_SCALE = 1.0\nWIDTH, HEIGHT = 1024, 1024\nSTEPS = 40\nGUIDANCE = 0.0   # not used by this model',
  load="""from diffusers import QwenImage21Pipeline
from huggingface_hub import hf_hub_download
from safetensors.torch import load_file

pipe = QwenImage21Pipeline.from_pretrained(MODEL_ID, torch_dtype=torch.bfloat16, token=HF_TOKEN)
# The file's keys look like "transformer_blocks.0.attn.to_k.lora_A.default.weight". diffusers wants a "transformer." prefix and no adapter name.
_raw = load_file(hf_hub_download(LORA_REPO, LORA_FILE, token=HF_TOKEN))
_state = {"transformer." + k.replace(".default.", "."): v for k, v in _raw.items()}
pipe.load_lora_weights(_state, adapter_name="uncensored")      # raises if no key matches: we want the run to stop, not run uncensored-less
pipe.set_adapters(["uncensored"], adapter_weights=[LORA_SCALE])
print("LoRA active:", pipe.get_active_adapters(), "tensors:", len(_state))
pipe.enable_sequential_cpu_offload()""",
  gen='''def generate(row, seed):
    return pipe(prompt=row["prompt"], width=opt(row, "width", WIDTH), height=opt(row, "height", HEIGHT),
                num_inference_steps=opt(row, "steps", STEPS),
                generator=torch.Generator("cuda").manual_seed(seed)).images[0]''')

_nsfw = _moss("MOSS-Image-SFT + NSFW LoRA", "OpenMOSS-Team/MOSS-Image-SFT",
    "MOSS-Image-SFT with the community adult LoRA axiomofmind/Moss-image-nsfw-uncensored-lora (Apache-2.0, not an official OpenMOSS release): focused 1,750-step checkpoint at scale 0.8, 30 steps, guidance 3.0, 1024x1024, empty negative prompt. The trigger phrase moss_xvstyle is put at the start of every prompt for you. Clearly adult, fictional subjects only (see the model card). Same size as MOSS-Image-SFT (~25 GB): Kaggle only, realistically. Follows the model card's own diffusers + PEFT recipe. EXPERIMENTAL: not tested.")
_nsfw["pip"] = "!pip install -q -U diffusers transformers accelerate sentencepiece protobuf peft safetensors\n!pip uninstall -y -q torchao      # Kaggle ships torchao 0.10, which the new peft rejects; the LoRA does not need it"
_nsfw["config"] = ('MODEL_ID = "OpenMOSS-Team/MOSS-Image-SFT"\nLORA_REPO = "axiomofmind/Moss-image-nsfw-uncensored-lora"\nLORA_SCALE = 0.8   # 0.7-0.9 were evaluated\n'
                   'TRIGGER = "moss_xvstyle"\nWIDTH, HEIGHT = 1024, 1024    # must be multiples of 16\nSTEPS = 30\nGUIDANCE = 3.0')
_nsfw["load"] = """import json
from diffusers import DiffusionPipeline
from huggingface_hub import hf_hub_download
from peft import LoraConfig, inject_adapter_in_model, set_peft_model_state_dict
from peft.tuners.lora.layer import LoraLayer
from safetensors.torch import load_file

pipe = DiffusionPipeline.from_pretrained(MODEL_ID, custom_pipeline="pipeline_moss_image", trust_remote_code=True,
                                         torch_dtype={"default": torch.bfloat16, "vae": torch.float32}, token=HF_TOKEN)
pipe.scheduler = type(pipe.scheduler).from_config(pipe.scheduler.config)

# Attach the LoRA to the transformer with PEFT, exactly as the adapter's model card does.
_cfg = json.load(open(hf_hub_download(LORA_REPO, "adapter_config.json")))
inject_adapter_in_model(LoraConfig(r=_cfg["r"], lora_alpha=_cfg["lora_alpha"], target_modules=_cfg["target_modules"]), pipe.transformer)
_state = {k.removeprefix("transformer."): v for k, v in load_file(hf_hub_download(LORA_REPO, "pytorch_lora_weights.safetensors")).items()}
_, _unexpected = set_peft_model_state_dict(pipe.transformer, _state)
if _unexpected:
    raise RuntimeError(f"Unexpected LoRA tensors: {_unexpected[:5]}")
for _layer in pipe.transformer.modules():
    if isinstance(_layer, LoraLayer):
        _layer.set_scale("default", LORA_SCALE)
pipe.transformer.to(torch.bfloat16)
print("LoRA attached, scale", LORA_SCALE)

# A T4 cannot hold the 14 GB transformer (see the MOSS-Image-SFT notes): stream weights through the GPU layer by layer.
pipe.enable_sequential_cpu_offload()
try:
    pipe.vae.enable_tiling()
except Exception:
    pass"""
_nsfw["gen"] = '''def generate(row, seed):
    prompt = row["prompt"]
    if not prompt.lower().startswith(TRIGGER):
        prompt = TRIGGER + ", " + prompt          # the LoRA needs its trigger phrase first
    neg = row.get("negative") or None
    extra = {"negative_prompt": neg, "uncond_skip_layers": []} if neg else {"negative_prompt": "", "uncond_skip_layers": [22]}   # model card defaults
    return pipe(prompt, height=opt(row, "height", HEIGHT), width=opt(row, "width", WIDTH),
                num_inference_steps=opt(row, "steps", STEPS), guidance_scale=opt(row, "guidance", GUIDANCE, float),
                generator=torch.Generator("cpu").manual_seed(seed), **extra).images[0]'''
MODELS["moss_image_sft_lora"] = _nsfw

# MOSS-Sharpness-Slider is a small LoRA (18 MB, rank 4) for MOSS-Image-Base, not a model of its own: load the base model and attach the LoRA.
_slider = _moss("MOSS-Image-Base + Sharpness Slider", "OpenMOSS-Team/MOSS-Image-Base",
    "MOSS-Image-Base plus the aoleg/MOSS-Sharpness-Slider LoRA (Apache-2.0): a concept slider that sharpens (positive strength) or blurs (negative) the picture, no trigger word. This notebook uses strength 1.0 (sharper); change LORA_SCALE for more or less, or -1.0 to blur. Intended for the Base model. 1024x1024, 50 steps with two transformer passes each. About 25 GB of weights: layer-by-layer offload, slow, and Kaggle's system RAM is borderline. EXPERIMENTAL.")
_slider["pip"] = _nsfw["pip"]
_slider["config"] = ('MODEL_ID = "OpenMOSS-Team/MOSS-Image-Base"\nLORA_REPO = "aoleg/MOSS-Sharpness-Slider"\nLORA_FILE = "moss-sharp-v1_000000400.safetensors"\n'
                     'LORA_SCALE = 1.0   # positive sharpens, negative blurs, 0 is the untouched model\nWIDTH, HEIGHT = 1024, 1024    # must be multiples of 16\nSTEPS = 50\nGUIDANCE = 3.0')
_old_cfg = '_cfg = json.load(open(hf_hub_download(LORA_REPO, "adapter_config.json")))\ninject_adapter_in_model(LoraConfig(r=_cfg["r"], lora_alpha=_cfg["lora_alpha"], target_modules=_cfg["target_modules"]), pipe.transformer)'
_old_st = '{k.removeprefix("transformer."): v for k, v in load_file(hf_hub_download(LORA_REPO, "pytorch_lora_weights.safetensors")).items()}'
assert _old_cfg in _nsfw["load"] and _old_st in _nsfw["load"]
_slider["load"] = (_nsfw["load"]
    .replace(_old_cfg, '# rank 4, alpha 4 (the model card); same layers as the other MOSS LoRA\ninject_adapter_in_model(LoraConfig(r=4, lora_alpha=4, target_modules=r".*layers\\.\\d+\\.proj\\.(q|k|v|o|ffn_up_gate|ffn_down)"), pipe.transformer)')
    .replace(_old_st, '{k.removeprefix("diffusion_model."): v for k, v in load_file(hf_hub_download(LORA_REPO, LORA_FILE)).items()}'))
_slider["gen"] = MODELS["moss_image_base"]["gen"]
MODELS["moss_sharpness_slider"] = _slider


def md(t): return {"cell_type": "markdown", "metadata": {}, "source": t.strip().splitlines(True)}
def code(t): return {"cell_type": "code", "metadata": {}, "execution_count": None, "outputs": [], "source": t.strip().splitlines(True)}


# ---------------------------------------------------------------------------------------------------------------------------
# More text-to-image models. None needs a Hugging Face login: the gated originals (FLUX.1, Stable Diffusion 3.5) are read from
# public, ungated copies (unsloth/FLUX.1-*, adamo1139/stable-diffusion-3.5-large-*-ungated); the licences of the originals still apply.
# NOT run on a GPU yet: file names, folders and call arguments were checked against the repositories and the diffusers source.
# GGUF = a pre-quantized transformer (diffusers loads it with from_single_file); it lets a 12B model fit a 16 GB GPU.
# ---------------------------------------------------------------------------------------------------------------------------
PIP_GGUF = "!pip install -q -U diffusers transformers accelerate sentencepiece protobuf gguf"
_GGUF_LOAD = """from huggingface_hub import hf_hub_download
from diffusers import GGUFQuantizationConfig, {pipe_cls}, {tr_cls}

# Only the quantized transformer comes from the GGUF file; the text encoders, VAE and settings come from MODEL_ID.
transformer = {tr_cls}.from_single_file(hf_hub_download(GGUF_REPO, GGUF_FILE), config=MODEL_ID, subfolder="transformer",
                                        quantization_config=GGUFQuantizationConfig(compute_dtype=torch.bfloat16), torch_dtype=torch.bfloat16)
pipe = {pipe_cls}.from_pretrained(MODEL_ID, transformer=transformer, torch_dtype=torch.bfloat16)
pipe.enable_model_cpu_offload()"""

_FLUX1_GEN = '''def generate(row, seed):
    return pipe(prompt=row["prompt"], width=opt(row, "width", WIDTH), height=opt(row, "height", HEIGHT),
                num_inference_steps=opt(row, "steps", STEPS), guidance_scale=opt(row, "guidance", GUIDANCE, float),
                max_sequence_length=256, generator=torch.Generator("cpu").manual_seed(seed)).images[0]'''

MODELS["flux1_schnell"] = dict(title="FLUX.1-schnell (GGUF)", repo="unsloth/FLUX.1-schnell",
  note="Black Forest Labs' fast 12B model (Apache-2.0): 4 steps, very good prompt-following and text. The original repository asks for a Hugging Face login; this reads the public copy unsloth/FLUX.1-schnell plus a 4-bit GGUF file (city96/FLUX.1-schnell-gguf, 6.8 GB) so it fits a 16 GB GPU. No negative prompt. 1024x1024. Needs Kaggle's system RAM for the 9 GB text encoder. EXPERIMENTAL: not run on a GPU yet.",
  pip=PIP_GGUF,
  config='MODEL_ID = "unsloth/FLUX.1-schnell"      # ungated copy of black-forest-labs/FLUX.1-schnell\nGGUF_REPO = "city96/FLUX.1-schnell-gguf"\nGGUF_FILE = "flux1-schnell-Q4_K_S.gguf"\nWIDTH, HEIGHT = 1024, 1024\nSTEPS = 4\nGUIDANCE = 0.0   # schnell ignores it',
  load=_GGUF_LOAD.format(pipe_cls="FluxPipeline", tr_cls="FluxTransformer2DModel"), gen=_FLUX1_GEN)

MODELS["flux1_dev"] = dict(title="FLUX.1-dev (GGUF)", repo="unsloth/FLUX.1-dev",
  note="Black Forest Labs' best-quality 12B model, 28 steps (FLUX.1 [dev] Non-Commercial licence: free for personal and research use, not for selling the pictures). The original repository asks for a Hugging Face login; this reads the public copy unsloth/FLUX.1-dev plus a 4-bit GGUF file (city96/FLUX.1-dev-gguf, 6.8 GB). No negative prompt. 1024x1024; slow on a T4. EXPERIMENTAL: not run on a GPU yet.",
  pip=PIP_GGUF,
  config='MODEL_ID = "unsloth/FLUX.1-dev"      # ungated copy of black-forest-labs/FLUX.1-dev\nGGUF_REPO = "city96/FLUX.1-dev-gguf"\nGGUF_FILE = "flux1-dev-Q4_K_S.gguf"\nWIDTH, HEIGHT = 1024, 1024\nSTEPS = 28\nGUIDANCE = 3.5',
  load=_GGUF_LOAD.format(pipe_cls="FluxPipeline", tr_cls="FluxTransformer2DModel"), gen=_FLUX1_GEN)

_SD35_GEN = '''def generate(row, seed):
    return pipe(prompt=row["prompt"], negative_prompt=row.get("negative") or None,
                width=opt(row, "width", WIDTH), height=opt(row, "height", HEIGHT),
                num_inference_steps=opt(row, "steps", STEPS), guidance_scale=opt(row, "guidance", GUIDANCE, float),
                generator=torch.Generator("cpu").manual_seed(seed)).images[0]'''

MODELS["sd35_large"] = dict(title="Stable Diffusion 3.5 Large (GGUF)", repo="adamo1139/stable-diffusion-3.5-large-ungated",
  note="Stability AI's 8B model (Stability Community Licence: free below 1 million dollars of yearly revenue). The original repository asks for a Hugging Face login; this reads the public copy adamo1139/stable-diffusion-3.5-large-ungated plus a 4-bit GGUF file (city96/stable-diffusion-3.5-large-gguf, 4.8 GB). 28 steps, 1024x1024, supports a negative prompt. EXPERIMENTAL: not run on a GPU yet.",
  pip=PIP_GGUF,
  config='MODEL_ID = "adamo1139/stable-diffusion-3.5-large-ungated"      # ungated copy of stabilityai/stable-diffusion-3.5-large\nGGUF_REPO = "city96/stable-diffusion-3.5-large-gguf"\nGGUF_FILE = "sd3.5_large-Q4_0.gguf"\n# T4 limit: plain fp32 attention, 2 images per pass with guidance: 1024x1024 needed 5.5 GiB and crashed, 768x768 needs about 2 GiB\nWIDTH, HEIGHT = 768, 768\nSTEPS = 28\nGUIDANCE = 3.5',
  load=_GGUF_LOAD.format(pipe_cls="StableDiffusion3Pipeline", tr_cls="SD3Transformer2DModel"), gen=_SD35_GEN)

MODELS["sd35_large_turbo"] = dict(title="Stable Diffusion 3.5 Large Turbo (GGUF)", repo="adamo1139/stable-diffusion-3.5-large-turbo-ungated",
  note="The 4-step version of Stable Diffusion 3.5 Large (Stability Community Licence). The original repository asks for a Hugging Face login; this reads the public copy adamo1139/stable-diffusion-3.5-large-turbo-ungated plus a 4-bit GGUF file (city96/stable-diffusion-3.5-large-turbo-gguf). Guidance 0, 4 steps, 1024x1024. EXPERIMENTAL: not run on a GPU yet.",
  pip=PIP_GGUF,
  config='MODEL_ID = "adamo1139/stable-diffusion-3.5-large-turbo-ungated"      # ungated copy of stabilityai/stable-diffusion-3.5-large-turbo\nGGUF_REPO = "city96/stable-diffusion-3.5-large-turbo-gguf"\nGGUF_FILE = "sd3.5_large_turbo-Q4_0.gguf"\nWIDTH, HEIGHT = 1024, 1024\nSTEPS = 4\nGUIDANCE = 0.0',
  load=_GGUF_LOAD.format(pipe_cls="StableDiffusion3Pipeline", tr_cls="SD3Transformer2DModel"), gen=_SD35_GEN)

MODELS["flux2_klein_4b"] = dict(title="FLUX.2 klein 4B", repo="black-forest-labs/FLUX.2-klein-4B",
  note="Black Forest Labs' small, fast FLUX.2 model (Apache-2.0, not gated): 4 steps, 1024x1024, about 4B parameters plus a Qwen3 text encoder, so it fits a T4 with CPU offload. No negative prompt. EXPERIMENTAL: not run on a GPU yet.",
  pip="!pip install -q -U diffusers transformers accelerate sentencepiece protobuf",
  config='MODEL_ID = "black-forest-labs/FLUX.2-klein-4B"\nWIDTH, HEIGHT = 1024, 1024\nSTEPS = 4\nGUIDANCE = 1.0',
  load='from diffusers import Flux2KleinPipeline\n\npipe = Flux2KleinPipeline.from_pretrained(MODEL_ID, torch_dtype=torch.bfloat16)\npipe.enable_model_cpu_offload()',
  gen='''from PIL import Image

_REF_ROOT = Path(CSV_PATH).parent if "CSV_PATH" in globals() else Path("/content")


def references(row):
    """Character pictures named in the row's refs column (keyframes only), found next to the CSV. None when there are none."""
    pics = []
    for name in [n for n in (row.get("refs") or "").split("|") if n]:
        hits = sorted(_REF_ROOT.rglob(name))
        if hits:
            pics.append(Image.open(hits[0]).convert("RGB"))
        else:
            print(f"   reference picture {name} not found; continuing without it", flush=True)
    return pics or None


def generate(row, seed):
    kw = dict(prompt=row["prompt"], width=opt(row, "width", WIDTH), height=opt(row, "height", HEIGHT),
              num_inference_steps=opt(row, "steps", STEPS), guidance_scale=opt(row, "guidance", GUIDANCE, float))
    refs = references(row)
    if refs:
        try:       # each picture adds tokens to every attention step; on a T4 that can run out of memory
            return pipe(image=refs, generator=torch.Generator("cpu").manual_seed(seed), **kw).images[0]
        except torch.cuda.OutOfMemoryError:
            torch.cuda.empty_cache()
            print("   out of GPU memory with reference pictures; this image is made without them", flush=True)
    return pipe(generator=torch.Generator("cpu").manual_seed(seed), **kw).images[0]''')

# --- adult-content (uncensored) additions. Community models; use only for clearly adult, fictional subjects. ---
MODELS["chroma1_hd"] = dict(title="Chroma1-HD (GGUF)", repo="lodestones/Chroma1-HD",
  note="Chroma1-HD (Apache-2.0, not gated): an 8.9B model built on FLUX.1-schnell. Its model card makes no promise about content, but it is widely used for adult images without extra adapters and the pipeline here applies no safety filter. Uses a 4-bit GGUF file (silveroxides/Chroma1-HD-GGUF, 5.4 GB) so it fits a 16 GB GPU. 40 steps, guidance 3.0, supports a negative prompt, 1024x1024; slow on a T4. For clearly adult, fictional subjects only. EXPERIMENTAL: not run on a GPU yet.",
  pip=PIP_GGUF,
  config='MODEL_ID = "lodestones/Chroma1-HD"\nGGUF_REPO = "silveroxides/Chroma1-HD-GGUF"\nGGUF_FILE = "Chroma1-HD-Q4_K_S.gguf"\nWIDTH, HEIGHT = 1024, 1024\nSTEPS = 40\nGUIDANCE = 3.0\nNEGATIVE = "low quality, ugly, unfinished, out of focus, deformed, disfigure, blurry, smudged, restricted palette, flat colors"',
  load=_GGUF_LOAD.format(pipe_cls="ChromaPipeline", tr_cls="ChromaTransformer2DModel"),
  gen='''def generate(row, seed):
    return pipe(prompt=row["prompt"], negative_prompt=row.get("negative") or NEGATIVE,
                width=opt(row, "width", WIDTH), height=opt(row, "height", HEIGHT),
                num_inference_steps=opt(row, "steps", STEPS), guidance_scale=opt(row, "guidance", GUIDANCE, float),
                generator=torch.Generator("cpu").manual_seed(seed)).images[0]''')

MODELS["qwen_image_21_lora"] = dict(title="Qwen-Image-2.1 + adult LoRA", repo="Qwen/Qwen-Image-2.1",
  note="Qwen-Image-2.1 (Qwen Research License) plus the community adult LoRA f23gg/NSFW-LORA-Qwen-Image-2.1 (160 MB, made for this exact base model; the repo states no licence). A second option next to 'Qwen-Image-2.1 Uncensored'. 40 steps, 1024x1024. For clearly adult, fictional subjects only. The run stops with an error if the LoRA does not load. EXPERIMENTAL: not run on a GPU yet.",
  pip="!pip install -q -U torch torchvision torchaudio 'transformers>=5.17' accelerate sentencepiece protobuf pillow peft safetensors git+https://github.com/huggingface/diffusers\n!pip uninstall -y -q torchao      # Kaggle ships torchao 0.10, which the new peft rejects; nothing here needs it",
  config='MODEL_ID = "Qwen/Qwen-Image-2.1"\nLORA_REPO = "f23gg/NSFW-LORA-Qwen-Image-2.1"\nLORA_FILE = "NSFW Qwen Lora.safetensors"\nLORA_SCALE = 1.0\nWIDTH, HEIGHT = 1024, 1024\nSTEPS = 40\nGUIDANCE = 0.0   # not used by this model',
  load="""from diffusers import QwenImage21Pipeline
from huggingface_hub import hf_hub_download
from safetensors.torch import load_file

pipe = QwenImage21Pipeline.from_pretrained(MODEL_ID, torch_dtype=torch.bfloat16, token=HF_TOKEN)
# The file's keys look like "diffusion_model.transformer_blocks.0.attn.to_k.lora_A.weight"; diffusers wants a "transformer." prefix instead.
_raw = load_file(hf_hub_download(LORA_REPO, LORA_FILE, token=HF_TOKEN))
_state = {"transformer." + k.removeprefix("diffusion_model."): v for k, v in _raw.items()}
pipe.load_lora_weights(_state, adapter_name="adult")      # raises if no key matches: we want the run to stop, not run without the LoRA
pipe.set_adapters(["adult"], adapter_weights=[LORA_SCALE])
print("LoRA active:", pipe.get_active_adapters(), "tensors:", len(_state))
pipe.enable_sequential_cpu_offload()""",
  gen='''def generate(row, seed):
    return pipe(prompt=row["prompt"], width=opt(row, "width", WIDTH), height=opt(row, "height", HEIGHT),
                num_inference_steps=opt(row, "steps", STEPS),
                generator=torch.Generator("cuda").manual_seed(seed)).images[0]''')

_SDXL_GEN = '''def generate(row, seed):
    return pipe(prompt=row["prompt"], negative_prompt=row.get("negative") or NEGATIVE,
                width=opt(row, "width", WIDTH), height=opt(row, "height", HEIGHT),
                num_inference_steps=opt(row, "steps", STEPS), guidance_scale=opt(row, "guidance", GUIDANCE, float),
                generator=torch.Generator("cuda").manual_seed(seed)).images[0]'''

MODELS["noobai_xl"] = dict(title="NoobAI-XL 1.1", repo="Laxhar/noobai-XL-1.1",
  note="NoobAI-XL 1.1 (Fair AI Public License, not gated): a Stable Diffusion XL anime / illustration model trained on the full Danbooru and e621 image sets, which include adult images; add the tag 'nsfw' to a prompt to get them. Tag-style prompts such as '1girl, red hair, castle, masterpiece, best quality' work better than long sentences. 1024x1024, 28 steps, fits a free T4 in about 15 seconds per image. For clearly adult, fictional subjects only. EXPERIMENTAL: not run on a GPU yet.",
  config='MODEL_ID = "Laxhar/noobai-XL-1.1"\nWIDTH, HEIGHT = 1024, 1024\nSTEPS = 28\nGUIDANCE = 5.0\nNEGATIVE = "worst quality, low quality, bad anatomy, bad hands, missing fingers, extra digits, watermark, text, signature"',
  load='from diffusers import StableDiffusionXLPipeline\n\npipe = StableDiffusionXLPipeline.from_pretrained(MODEL_ID, torch_dtype=torch.float16, use_safetensors=True).to("cuda")\npipe.vae.enable_slicing()',
  gen=_SDXL_GEN)

MODELS["realvisxl_v5"] = dict(title="RealVisXL V5.0", repo="SG161222/RealVisXL_V5.0",
  note="RealVisXL V5.0 (OpenRAIL++ licence, not gated): a photorealistic Stable Diffusion XL model; its card says it 'can produce sfw and nsfw images'. Understands normal sentences. 1024x1024, 30 steps, about 15 seconds per image on a free T4. For clearly adult, fictional subjects only. EXPERIMENTAL: not run on a GPU yet.",
  config='MODEL_ID = "SG161222/RealVisXL_V5.0"\nWIDTH, HEIGHT = 1024, 1024\nSTEPS = 30\nGUIDANCE = 5.0\nNEGATIVE = "(worst quality, low quality, illustration, 3d, 2d, painting, cartoons, sketch), open mouth, blurry, deformed, watermark, text"',
  load='from diffusers import StableDiffusionXLPipeline\n\npipe = StableDiffusionXLPipeline.from_pretrained(MODEL_ID, torch_dtype=torch.float16, variant="fp16", use_safetensors=True).to("cuda")\npipe.vae.enable_slicing()',
  gen=_SDXL_GEN)

MODELS["illustrious_xl"] = dict(title="Illustrious-XL 1.0", repo="OnomaAIResearch/Illustrious-XL-v1.0",
  note="Illustrious-XL 1.0 (SDXL licence, not gated): a Stable Diffusion XL illustration model that many adult anime checkpoints are built on; its model card says nothing about content, and the pipeline here applies no safety filter. Danbooru-style tag prompts work best. One single-file checkpoint (6.9 GB). 1024x1024, 28 steps, about 15 seconds per image on a free T4. For clearly adult, fictional subjects only. EXPERIMENTAL: not run on a GPU yet.",
  config='MODEL_ID = "OnomaAIResearch/Illustrious-XL-v1.0"\nMODEL_FILE = "Illustrious-XL-v1.0.safetensors"\nWIDTH, HEIGHT = 1024, 1024\nSTEPS = 28\nGUIDANCE = 5.5\nNEGATIVE = "worst quality, low quality, bad anatomy, bad hands, missing fingers, extra digits, watermark, text, signature"',
  load='from diffusers import StableDiffusionXLPipeline\nfrom huggingface_hub import hf_hub_download\n\npipe = StableDiffusionXLPipeline.from_single_file(hf_hub_download(MODEL_ID, MODEL_FILE), torch_dtype=torch.float16).to("cuda")\npipe.vae.enable_slicing()',
  gen=_SDXL_GEN)

# --- batch 1 of the catalogue expansion (newest first, from docs/MODEL_PLAN.md). Each must pass scripts/run_regression.sh before it is trusted. ---
_NEWPIP = "!pip install -q -U torch torchvision torchaudio 'transformers>=5.17' accelerate sentencepiece protobuf pillow git+https://github.com/huggingface/diffusers"

MODELS["z_image_turbo"] = dict(title="Z-Image-Turbo", repo="Tongyi-MAI/Z-Image-Turbo",
  note="Z-Image-Turbo (Apache-2.0, not gated, Nov 2025): a 6B image model from Alibaba Tongyi that makes a sharp 1024x1024 picture in 9 steps (8 forward passes) and is one of the most liked image models on Hugging Face. No negative prompt or guidance (guidance is 0 for the Turbo model). Weights are moved to the GPU layer by layer so it fits a T4 (slow). EXPERIMENTAL: not run on a GPU yet.",
  pip=_NEWPIP,
  config='MODEL_ID = "Tongyi-MAI/Z-Image-Turbo"\nWIDTH, HEIGHT = 1024, 1024\nSTEPS = 9\nGUIDANCE = 0.0',
  load='from diffusers import ZImagePipeline\n\npipe = ZImagePipeline.from_pretrained(MODEL_ID, torch_dtype=torch.bfloat16, token=HF_TOKEN)\npipe.vae.enable_tiling()\npipe.enable_sequential_cpu_offload()     # the 12 GB transformer plus the VAE decode did not fit a T4 with model offload (OOM)',
  gen='''def generate(row, seed):
    return pipe(prompt=row["prompt"], width=opt(row, "width", WIDTH), height=opt(row, "height", HEIGHT),
                num_inference_steps=opt(row, "steps", STEPS), guidance_scale=0.0,
                generator=torch.Generator("cuda").manual_seed(seed)).images[0]''')

MODELS["z_image"] = dict(title="Z-Image (full model)", repo="Tongyi-MAI/Z-Image",
  note="Z-Image (Apache-2.0, not gated, Jan 2026): the full, non-distilled 6B model behind Z-Image-Turbo. More varied and it follows a negative prompt, but needs 50 steps with guidance 4, so it is about five times slower than the Turbo one. 1024x1024. EXPERIMENTAL: not run on a GPU yet.",
  pip=_NEWPIP,
  config='MODEL_ID = "Tongyi-MAI/Z-Image"\nWIDTH, HEIGHT = 1024, 1024\nSTEPS = 50\nGUIDANCE = 4.0\nNEGATIVE = ""',
  load='from diffusers import ZImagePipeline\n\npipe = ZImagePipeline.from_pretrained(MODEL_ID, torch_dtype=torch.bfloat16, token=HF_TOKEN)\npipe.vae.enable_tiling()\npipe.enable_sequential_cpu_offload()     # the 12 GB transformer plus the VAE decode did not fit a T4 with model offload (OOM)',
  gen='''def generate(row, seed):
    return pipe(prompt=row["prompt"], negative_prompt=row.get("negative") or NEGATIVE, width=opt(row, "width", WIDTH), height=opt(row, "height", HEIGHT),
                num_inference_steps=opt(row, "steps", STEPS), guidance_scale=opt(row, "guidance", GUIDANCE, float), cfg_normalization=False,
                generator=torch.Generator("cuda").manual_seed(seed)).images[0]''')

MODELS["ernie_image_turbo"] = dict(title="ERNIE-Image-Turbo", repo="baidu/ERNIE-Image-Turbo",
  note="ERNIE-Image-Turbo (Apache-2.0, not gated, Apr 2026): Baidu's 8B image model, 8 steps, guidance 1.0, good at long detailed prompts and text in pictures. Sizes it was trained for: 1024x1024, 848x1264, 1264x848, 768x1376, 1376x768. Weights are moved to the GPU layer by layer so it fits a T4 (slow). EXPERIMENTAL: not run on a GPU yet.",
  pip=_NEWPIP,
  config='MODEL_ID = "baidu/ERNIE-Image-Turbo"\nWIDTH, HEIGHT = 1024, 1024\nSTEPS = 8\nGUIDANCE = 1.0',
  load='from diffusers import ErnieImagePipeline\n\npipe = ErnieImagePipeline.from_pretrained(MODEL_ID, torch_dtype=torch.bfloat16, token=HF_TOKEN)\npipe.enable_sequential_cpu_offload()',
  gen='''def generate(row, seed):
    return pipe(prompt=row["prompt"], width=opt(row, "width", WIDTH), height=opt(row, "height", HEIGHT),
                num_inference_steps=opt(row, "steps", STEPS), guidance_scale=opt(row, "guidance", GUIDANCE, float), use_pe=False,
                generator=torch.Generator("cuda").manual_seed(seed)).images[0]''')

MODELS["qwen_image_21_turbo"] = dict(title="Qwen-Image-2.1-Turbo", repo="Qwen/Qwen-Image-2.1-Turbo",
  note="Qwen-Image-2.1-Turbo (Qwen Research License, not gated, Oct 2026): the official distilled Qwen-Image-2.1, a few steps instead of 40, with the same strong text rendering. The number of steps is set by the model itself (its sampling schedule is built in), so the Steps box is ignored. 1024x1024; weights are moved to the GPU layer by layer so it fits a T4. EXPERIMENTAL: not run on a GPU yet.",
  pip="!pip install -q -U torch torchvision torchaudio 'transformers>=5.17' accelerate sentencepiece protobuf pillow git+https://github.com/huggingface/diffusers",
  config='MODEL_ID = "Qwen/Qwen-Image-2.1-Turbo"\nWIDTH, HEIGHT = 1024, 1024',
  load='from diffusers import QwenImage21Pipeline\n\npipe = QwenImage21Pipeline.from_pretrained(MODEL_ID, torch_dtype=torch.bfloat16, token=HF_TOKEN)\npipe.enable_sequential_cpu_offload()',
  gen='''def generate(row, seed):
    return pipe(prompt=row["prompt"], width=opt(row, "width", WIDTH), height=opt(row, "height", HEIGHT),
                generator=torch.Generator("cuda").manual_seed(seed)).images[0]''')


def script(key, m):
    return (f'"""{m["title"]} text-to-image. Runs ON the Colab/Kaggle VM. {m["note"]}\n\nReads rows START..END of the CSV and writes image-NNNN.png.\n"""\n'
            + HEADER + m["config"] + "\n\n" + m["load"] + "\n\n" + m["gen"] + "\n" + LOOP)


PIP = "!pip install -q -U diffusers transformers accelerate sentencepiece protobuf"


def notebook(key, m, platform):
    suffix = "SUFFIX = ''"
    if platform == "colab":
        intro = f"# Pistachio's Studio: {m['title']} images on Colab\n\n{m['note']}\n\nRuntime → Change runtime type → **T4 GPU**. Put `all_images.csv` in `MyDrive/PistachioStudio/`."
        secret = ("import os\ntry:\n    from google.colab import userdata\n    os.environ['HF_TOKEN'] = userdata.get('HF_TOKEN')   # only needed for gated models\n"
                  "except Exception:\n    pass")
        setup = [code("from google.colab import drive\ndrive.mount('/content/drive')")]
        paths = ("from pathlib import Path\nBASE = Path('/content/drive/MyDrive/PistachioStudio')\nCSV_NAME = 'all_images.csv'\nCSV_PATH = BASE / CSV_NAME\n"
                 f"OUT = BASE / 'images' / '{key}'")
    else:
        intro = (f"# Pistachio's Studio: {m['title']} images on Kaggle\n\n{m['note']}\n\nAccelerator = GPU T4 x2, Internet = On, dataset with the CSVs attached. "
                 "Images go to `/kaggle/working/images/`.")
        secret = ("import os\ntry:\n    from kaggle_secrets import UserSecretsClient\n    os.environ['HF_TOKEN'] = UserSecretsClient().get_secret('HF_TOKEN')   # only needed for gated models\n"
                  "except Exception:\n    pass")
        setup = []
        paths = ("from pathlib import Path\nCSV_NAME = 'all_images.csv'\nCSV_PATH = next(Path('/kaggle/input').rglob(CSV_NAME))\n"
                 f"OUT = Path('/kaggle/working/images') / '{key}'")
    cfg = paths + "\nSTART, END = 1, 10   # CSV row numbers (1-based)\nMAKE_TAR = False"
    meta = {"accelerator": "GPU"} if platform == "colab" else {}
    meta["kernelspec"] = {"display_name": "Python 3", "name": "python3"}
    return {"cells": [md(intro), code(m.get("pip", PIP))] + setup + [code(secret), code(cfg), code(script(key, m))],
            "metadata": meta, "nbformat": 4, "nbformat_minor": 0}


for key, m in MODELS.items():
    (root / f"colab_generate_image_{key}.py").write_text(script(key, m))
    json.dump(notebook(key, m, "colab"), open(root / f"Studio_Colab_image_{key}.ipynb", "w"), indent=1)
    json.dump(notebook(key, m, "kaggle"), open(root / f"Studio_Kaggle_image_{key}.ipynb", "w"), indent=1)
print("wrote", ", ".join(MODELS))
