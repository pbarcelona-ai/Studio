import json
from pathlib import Path
import os as _os
root = Path(_os.environ["STUDIO_GEN_DIR"]) if _os.environ.get("STUDIO_GEN_DIR") else Path(__file__).resolve().parent.parent   # STUDIO_GEN_DIR: write somewhere else (the run scripts use a throw-away folder)

NEG = "worst quality, inconsistent motion, blurry, jittery, distorted, text, subtitles, watermark, logo, modern objects"
MODELS = {
"ltx_video": dict(
  title="LTX-Video", repo="Lightricks/LTX-Video", fps=24,
  note="Fast; fits a free T4. ~4 s clips, 2.4:1 widescreen. Prompt window is set to 256 tokens so the ~800-char prompts are not cut.",
  config='MODEL_ID = "Lightricks/LTX-Video"\nWIDTH, HEIGHT = 768, 320   # divisible by 32, ~2.4:1\nNUM_FRAMES = 97            # 8*k+1, about 4 s at 24 fps\nFPS = 24\nSTEPS = 40\nGUIDANCE = 3.0',
  load='from diffusers import LTXPipeline\n\n# T4 has no native bf16 and fp16 can give black frames with LTX, so bf16 (slower on T4, fast on L4/A100).\npipe = LTXPipeline.from_pretrained(MODEL_ID, torch_dtype=torch.bfloat16)\npipe.enable_model_cpu_offload()\npipe.vae.enable_tiling()',
  gen='''def opt(row, key, default, cast=int):
    """Per-row setting from the CSV (blank/missing -> the default above)."""
    v = row.get(key)
    return cast(v) if v not in (None, "") else default


def generate(row, seed):
    return pipe(prompt=row["prompt"], negative_prompt=row.get("negative") or NEGATIVE,
                width=opt(row, "width", WIDTH), height=opt(row, "height", HEIGHT), num_frames=opt(row, "frames", NUM_FRAMES),
                num_inference_steps=opt(row, "steps", STEPS), guidance_scale=opt(row, "guidance", GUIDANCE, float),
                max_sequence_length=256, generator=torch.Generator("cuda").manual_seed(seed)).frames[0]'''),
"wan": dict(
  title="Wan 2.1 (1.3B)", repo="Wan-AI/Wan2.1-T2V-1.3B-Diffusers", fps=16,
  note="Better motion and prompt-following than LTX but slower. The 1.3B model fits a T4 with CPU offload, but attention memory grows with the square of the video size, so on a T4 the default is small (512x288, 33 frames, about 2 s); the VAE runs in fp32 as the model card advises.",
  config='MODEL_ID = "Wan-AI/Wan2.1-T2V-1.3B-Diffusers"\n# T4 limit: bf16 attention is computed the plain way there, so one attention matrix needs 48 x tokens^2 bytes, with\n# tokens = ((frames-1)//4+1) * (height/16) * (width/16). 832x480x81 frames = 32,760 tokens = 48 GiB (this crashed the first Kaggle run);\n# keep tokens under about 6,500 on a T4. 512x288 with 33 frames = 5,184 tokens = 1.3 GiB. Raise these only on an L4/A100.\nWIDTH, HEIGHT = 512, 288\nNUM_FRAMES = 33           # 4*k+1, about 2 s at 16 fps\nFPS = 16\nSTEPS = 30\nGUIDANCE = 5.0',
  load='from diffusers import AutoencoderKLWan, WanPipeline\n\nvae = AutoencoderKLWan.from_pretrained(MODEL_ID, subfolder="vae", torch_dtype=torch.float32)\npipe = WanPipeline.from_pretrained(MODEL_ID, vae=vae, torch_dtype=torch.bfloat16)\npipe.enable_model_cpu_offload()',
  gen='''def opt(row, key, default, cast=int):
    """Per-row setting from the CSV (blank/missing -> the default above)."""
    v = row.get(key)
    return cast(v) if v not in (None, "") else default


def generate(row, seed):
    return pipe(prompt=row["prompt"], negative_prompt=row.get("negative") or NEGATIVE,
                width=opt(row, "width", WIDTH), height=opt(row, "height", HEIGHT), num_frames=opt(row, "frames", NUM_FRAMES),
                num_inference_steps=opt(row, "steps", STEPS), guidance_scale=opt(row, "guidance", GUIDANCE, float),
                generator=torch.Generator("cuda").manual_seed(seed)).frames[0]'''),
"cogvideox": dict(
  title="CogVideoX (2B)", repo="THUDM/CogVideoX-2b", fps=8,
  note="Runs in fp16 (works on a T4). 720x480, 6 s at 8 fps, so it looks choppy. Its text encoder reads only 226 tokens, so the tail of long prompts (the style boilerplate) is cut off.",
  config='MODEL_ID = "THUDM/CogVideoX-2b"\nWIDTH, HEIGHT = 720, 480\nNUM_FRAMES = 49           # fixed by the model, 6 s at 8 fps\nFPS = 8\nSTEPS = 50\nGUIDANCE = 6.0',
  load='from diffusers import CogVideoXPipeline\n\npipe = CogVideoXPipeline.from_pretrained(MODEL_ID, torch_dtype=torch.float16)\npipe.enable_model_cpu_offload()\npipe.vae.enable_tiling()\npipe.vae.enable_slicing()',
  gen='''def opt(row, key, default, cast=int):
    """Per-row setting from the CSV (blank/missing -> the default above)."""
    v = row.get(key)
    return cast(v) if v not in (None, "") else default


def generate(row, seed):
    return pipe(prompt=row["prompt"], negative_prompt=row.get("negative") or None, width=WIDTH, height=HEIGHT,
                num_frames=NUM_FRAMES,      # size and frames are fixed by this model, so those columns are ignored
                num_inference_steps=opt(row, "steps", STEPS), guidance_scale=opt(row, "guidance", GUIDANCE, float),
                generator=torch.Generator("cuda").manual_seed(seed)).frames[0]'''),
}

# ---------------------------------------------------------------------------------------------------------------------------
# More text-to-video models. All of them download from Hugging Face without a login (no gated repositories).
# NOT run on a GPU yet: names, files and arguments were checked against the repositories and the diffusers source.
# GGUF = a pre-quantized transformer (diffusers loads it with from_single_file); it keeps a 14B model within a 16 GB GPU.
# ---------------------------------------------------------------------------------------------------------------------------
OPT = '''def opt(row, key, default, cast=int):
    """Per-row setting from the CSV (blank/missing -> the default above)."""
    v = row.get(key)
    return cast(v) if v not in (None, "") else default


'''
PIP_GGUF = "!pip install -q -U diffusers transformers accelerate sentencepiece protobuf imageio imageio-ffmpeg ftfy gguf peft safetensors\n!pip uninstall -y -q torchao      # Kaggle ships torchao 0.10, which the new peft rejects; nothing here needs it"
_GGUF_WAN = """from diffusers import AutoencoderKLWan, GGUFQuantizationConfig, WanPipeline, WanTransformer3DModel
from huggingface_hub import hf_hub_download

def _expert(filename):
    # The quantized weights stay small on the GPU and are expanded layer by layer while sampling.
    return WanTransformer3DModel.from_single_file(hf_hub_download(GGUF_REPO, filename), config=MODEL_ID, subfolder="transformer",
                                                  quantization_config=GGUFQuantizationConfig(compute_dtype=torch.bfloat16), torch_dtype=torch.bfloat16)

vae = AutoencoderKLWan.from_pretrained(MODEL_ID, subfolder="vae", torch_dtype=torch.float32)
# System-RAM limit (Kaggle ~29 GB): the two 7 GB experts plus the 11 GB text encoder did not fit together and the kernel was killed. So the text
# encoder goes first, alone on the GPU, encodes every prompt of this batch, and is thrown away before the experts are loaded.
pipe = WanPipeline.from_pretrained(MODEL_ID, vae=vae, transformer=None, transformer_2=None, torch_dtype=torch.bfloat16)
pipe.text_encoder.to("cuda")
_EMB = {}
for _i in range(START, min(END, len(shots)) + 1):
    _r = shots[_i - 1]
    _key = (PROMPT_PREFIX + _r["prompt"], _r.get("negative") or NEGATIVE)
    if _key not in _EMB:
        with torch.no_grad():
            _p, _n = pipe.encode_prompt(prompt=_key[0], negative_prompt=_key[1], do_classifier_free_guidance=True, device="cuda")
        _EMB[_key] = (_p.cpu(), _n.cpu())
pipe.register_modules(text_encoder=None)
import gc; gc.collect(); torch.cuda.empty_cache()
print("prompts encoded:", len(_EMB), "- text encoder freed", flush=True)
pipe.register_modules(transformer=_expert(HIGH_FILE), transformer_2=_expert(LOW_FILE))
pipe.vae.enable_tiling()      # the float32 VAE decode otherwise asks for ~4 GB at once and runs out of GPU memory next to the 7 GB expert
pipe.vae.enable_slicing()
"""
_WAN14_CFG = ('MODEL_ID = "Wan-AI/Wan2.2-T2V-A14B-Diffusers"     # supplies the text encoder, VAE and settings\nGGUF_REPO = "QuantStack/Wan2.2-T2V-A14B-GGUF"\n'
              'HIGH_FILE = "HighNoise/Wan2.2-T2V-A14B-HighNoise-Q3_K_M.gguf"   # 7.2 GB each; the model has two "experts" (early and late sampling steps)\n'
              'LOW_FILE = "LowNoise/Wan2.2-T2V-A14B-LowNoise-Q3_K_M.gguf"\n'
              '# T4 limit: plain fp32 attention, one matrix = 160 x tokens^2 bytes, tokens = ((frames-1)/4+1) x (H/16) x (W/16); 512x288x33 needed 4 GiB and crashed\nWIDTH, HEIGHT = 448, 256    # multiples of 16\nNUM_FRAMES = 25            # 4*k+1, 1.6 s at 16 fps\nFPS = 16\nSTEPS = 30\nGUIDANCE = 4.0           # first expert\nGUIDANCE_2 = 3.0         # second expert')
_WAN14_GEN = OPT + '''def generate(row, seed):
    _p, _n = _EMB[(PROMPT_PREFIX + row["prompt"], row.get("negative") or NEGATIVE)]      # prompts were encoded before the text encoder was freed
    return pipe(prompt_embeds=_p.to("cuda", torch.bfloat16), negative_prompt_embeds=_n.to("cuda", torch.bfloat16),
                width=opt(row, "width", WIDTH), height=opt(row, "height", HEIGHT), num_frames=opt(row, "frames", NUM_FRAMES),
                num_inference_steps=opt(row, "steps", STEPS), guidance_scale=opt(row, "guidance", GUIDANCE, float), guidance_scale_2=GUIDANCE_2,
                generator=torch.Generator("cuda").manual_seed(seed)).frames[0]'''

MODELS["wan22_ti2v_5b"] = dict(
  title="Wan 2.2 (TI2V 5B)", repo="Wan-AI/Wan2.2-TI2V-5B-Diffusers", fps=24,
  note="Wan 2.2's 5B text+image-to-video model (Apache-2.0), used here for text only. Better quality than Wan 2.1 1.3B at 24 fps; its VAE is 4x more compact, so it fits a T4 with CPU offload at a modest size (default 704x384, 33 frames). Sizes must be multiples of 32. Slow on a T4 because bf16 is emulated there. EXPERIMENTAL: not run on a GPU yet.",
  config='MODEL_ID = "Wan-AI/Wan2.2-TI2V-5B-Diffusers"\nWIDTH, HEIGHT = 704, 384    # multiples of 32\nNUM_FRAMES = 33            # 4*k+1, 1.4 s at 24 fps\nFPS = 24\nSTEPS = 30\nGUIDANCE = 5.0\nPROMPT_PREFIX = ""',
  load="""from diffusers import AutoencoderKLWan, WanPipeline

vae = AutoencoderKLWan.from_pretrained(MODEL_ID, subfolder="vae", torch_dtype=torch.float32)     # a float32 VAE decodes cleanly
pipe = WanPipeline.from_pretrained(MODEL_ID, vae=vae, torch_dtype=torch.bfloat16)
pipe.enable_model_cpu_offload()""",
  gen=OPT + '''def generate(row, seed):
    return pipe(prompt=PROMPT_PREFIX + row["prompt"], negative_prompt=row.get("negative") or NEGATIVE,
                width=opt(row, "width", WIDTH), height=opt(row, "height", HEIGHT), num_frames=opt(row, "frames", NUM_FRAMES),
                num_inference_steps=opt(row, "steps", STEPS), guidance_scale=opt(row, "guidance", GUIDANCE, float),
                generator=torch.Generator("cuda").manual_seed(seed)).frames[0]''')

MODELS["wan22_t2v_a14b"] = dict(
  title="Wan 2.2 (T2V A14B, GGUF)", repo="Wan-AI/Wan2.2-T2V-A14B-Diffusers", fps=16, pip=PIP_GGUF,
  note="Wan 2.2's 14B text-to-video model (Apache-2.0) as two 7 GB 3-bit GGUF files (QuantStack/Wan2.2-T2V-A14B-GGUF) so it fits a 16 GB GPU. Best motion and prompt-following of the Wan family. Needs most of Kaggle's ~29 GB system RAM (two 7 GB experts plus a 11 GB text encoder): if the run dies with an out-of-memory error, use Wan 2.2 5B. Default 512x288, 33 frames at 16 fps. EXPERIMENTAL: not run on a GPU yet.",
  config=_WAN14_CFG + '\nPROMPT_PREFIX = ""',
  load=_GGUF_WAN + "pipe.enable_model_cpu_offload()",
  gen=_WAN14_GEN)

MODELS["wan22_t2v_a14b_lora"] = dict(
  title="Wan 2.2 (T2V A14B, GGUF) + adult LoRA", repo="Wan-AI/Wan2.2-T2V-A14B-Diffusers", fps=16, pip=PIP_GGUF,
  note="The Wan 2.2 14B GGUF model above plus a community adult LoRA pair (JERRYNPC/WAN2.2-LORA-NSFW, 'T2V - Big Perky Breasts', one file per expert; the repo has no licence statement). The base model has no safety filter of its own; the LoRA adds adult body detail. For clearly adult, fictional subjects only. The LoRA is loaded into both experts and the run stops with an error if it does not fit, rather than quietly running without it. Same memory needs as the base model. EXPERIMENTAL: not run on a GPU yet.",
  config=_WAN14_CFG + '\nLORA_REPO = "JERRYNPC/WAN2.2-LORA-NSFW"\nLORA_HIGH = "Wan2.2 - T2V - Big Perky Breasts - HIGH 14B.safetensors"\nLORA_LOW = "Wan2.2 - T2V - Big Perky Breasts - LOW 14B.safetensors"\nPROMPT_PREFIX = ""',
  load=_GGUF_WAN + """pipe.load_lora_weights(LORA_REPO, weight_name=LORA_HIGH, adapter_name="adult_high")                              # first expert
pipe.load_lora_weights(LORA_REPO, weight_name=LORA_LOW, adapter_name="adult_low", load_into_transformer_2=True)   # second expert
print("LoRA loaded into both experts")
pipe.enable_model_cpu_offload()""",
  gen=_WAN14_GEN)

MODELS["wan22_t2v_a14b_lightning"] = dict(
  title="Wan 2.2 (T2V A14B, GGUF) Lightning 4-step", repo="Wan-AI/Wan2.2-T2V-A14B-Diffusers", fps=16, pip=PIP_GGUF,
  note="The Wan 2.2 14B GGUF model above with the Lightning speed-up LoRA (lightx2v/Wan2.2-Lightning, Seko V2.0, Apache-2.0) in both experts, so a clip takes 4 steps with no guidance trick: about 7x faster than the 30-step model at similar quality. Same memory needs as the plain 14B model. Default size 448x256, 25 frames.",
  config=_WAN14_CFG + '\nLORA_REPO = "lightx2v/Wan2.2-Lightning"\nLORA_HIGH = "Wan2.2-T2V-A14B-4steps-lora-rank64-Seko-V2.0/high_noise_model.safetensors"\nLORA_LOW = "Wan2.2-T2V-A14B-4steps-lora-rank64-Seko-V2.0/low_noise_model.safetensors"\nSTEPS = 4\nGUIDANCE = 1.0\nGUIDANCE_2 = 1.0\nPROMPT_PREFIX = ""',
  load=_GGUF_WAN + """pipe.load_lora_weights(LORA_REPO, weight_name=LORA_HIGH, adapter_name="lightning_high")                              # first expert
pipe.load_lora_weights(LORA_REPO, weight_name=LORA_LOW, adapter_name="lightning_low", load_into_transformer_2=True)   # second expert
print("Lightning LoRA loaded into both experts")
pipe.enable_model_cpu_offload()""",
  gen=_WAN14_GEN)

_HUN_CFG = ('MODEL_ID = "hunyuanvideo-community/HunyuanVideo"     # supplies the text encoders, VAE and settings\nGGUF_REPO = "city96/HunyuanVideo-gguf"\n'
            'GGUF_FILE = "hunyuan-video-t2v-720p-Q4_K_S.gguf"       # 7.7 GB (the full model is 26 GB)\n'
            '# T4 limit: plain fp32 attention, one matrix = 96 x tokens^2 bytes, tokens = ((frames-1)/4+1) x (H/16) x (W/16); 640x368x61 asked for 20 GiB and crashed\nWIDTH, HEIGHT = 480, 272    # multiples of 16\nNUM_FRAMES = 33            # 4*k+1, 2.2 s at 15 fps\nFPS = 15\nSTEPS = 30\nGUIDANCE = 6.0')
_HUN_LOAD = """from diffusers import GGUFQuantizationConfig, HunyuanVideoPipeline, HunyuanVideoTransformer3DModel
from huggingface_hub import hf_hub_download

transformer = HunyuanVideoTransformer3DModel.from_single_file(hf_hub_download(GGUF_REPO, GGUF_FILE), config=MODEL_ID, subfolder="transformer",
                                                              quantization_config=GGUFQuantizationConfig(compute_dtype=torch.bfloat16), torch_dtype=torch.bfloat16)
pipe = HunyuanVideoPipeline.from_pretrained(MODEL_ID, transformer=transformer, torch_dtype=torch.float16)
"""
_HUN_TAIL = "pipe.vae.enable_tiling()\npipe.enable_model_cpu_offload()"
_HUN_GEN = OPT + '''def generate(row, seed):
    # HunyuanVideo takes no negative prompt; GUIDANCE is its built-in "embedded" guidance.
    return pipe(prompt=PROMPT_PREFIX + row["prompt"], width=opt(row, "width", WIDTH), height=opt(row, "height", HEIGHT),
                num_frames=opt(row, "frames", NUM_FRAMES), num_inference_steps=opt(row, "steps", STEPS),
                guidance_scale=opt(row, "guidance", GUIDANCE, float), generator=torch.Generator("cuda").manual_seed(seed)).frames[0]'''

MODELS["hunyuan_video"] = dict(
  title="HunyuanVideo (GGUF)", repo="hunyuanvideo-community/HunyuanVideo", fps=15, pip=PIP_GGUF,
  note="Tencent's 13B text-to-video model (Tencent Hunyuan community licence; not available in the EU, UK or South Korea) as a 4-bit GGUF file (city96/HunyuanVideo-gguf) so it fits a 16 GB GPU. Good realism and motion. Its text encoder is an 8B language model (16 GB in system RAM), so it needs Kaggle rather than Colab. No negative prompt. Default 640x368, 61 frames at 15 fps. EXPERIMENTAL: not run on a GPU yet.",
  config=_HUN_CFG + '\nPROMPT_PREFIX = ""',
  load=_HUN_LOAD + _HUN_TAIL,
  gen=_HUN_GEN)

MODELS["hunyuan_video_lora"] = dict(
  title="HunyuanVideo (GGUF) + adult LoRA", repo="hunyuanvideo-community/HunyuanVideo", fps=15, pip=PIP_GGUF,
  note="HunyuanVideo above plus the community adult LoRA BigStationW/HunyuanVideo_nfsw_lora (licence 'unknown'; it was taken down from Civitai). Its trigger word nsfwsks is put at the start of every prompt for you. For clearly adult, fictional subjects only. The weights were checked to convert and map onto every layer of the model; the run stops with an error if they do not load. EXPERIMENTAL: not run on a GPU yet.",
  config=_HUN_CFG + '\nLORA_REPO = "BigStationW/HunyuanVideo_nfsw_lora"\nLORA_FILE = "nsfw-e7.safetensors"\nLORA_SCALE = 1.0\nPROMPT_PREFIX = "nsfwsks, "   # the LoRA\'s trigger word',
  load=_HUN_LOAD + """from safetensors.torch import load_file

# The file uses ComfyUI-style names ("diffusion_model.double_blocks..."); diffusers converts the original names once the prefix is gone.
_state = {k.removeprefix("diffusion_model."): v for k, v in load_file(hf_hub_download(LORA_REPO, LORA_FILE)).items()}
pipe.load_lora_weights(_state, adapter_name="adult")      # raises if nothing matches: the run stops instead of running without the LoRA
pipe.set_adapters(["adult"], adapter_weights=[LORA_SCALE])
print("LoRA active:", pipe.get_active_adapters(), "tensors:", len(_state))
""" + _HUN_TAIL,
  gen=_HUN_GEN)

MODELS["cogvideox_5b"] = dict(
  title="CogVideoX (5B)", repo="zai-org/CogVideoX-5b", fps=8,
  note="The larger CogVideoX (CogVideoX licence, free for most uses; weights moved from THUDM to zai-org). Clearly better detail than the 2B model; bf16, so slow on a T4. 720x480, 6 s at 8 fps (choppy). Its text encoder reads only 226 tokens. EXPERIMENTAL: not run on a GPU yet.",
  config='MODEL_ID = "zai-org/CogVideoX-5b"\nWIDTH, HEIGHT = 720, 480\nNUM_FRAMES = 49           # fixed by the model, 6 s at 8 fps\nFPS = 8\nSTEPS = 50\nGUIDANCE = 6.0',
  load='from diffusers import CogVideoXPipeline\n\n# A T4 has no fast bf16 attention kernel, so bf16 attention builds the whole matrix (113 GiB at 720x480x49: out of memory). Running just the attention in fp16 uses the memory-saving kernel.\nimport torch.nn.functional as F\n_sdpa = F.scaled_dot_product_attention\ndef _sdpa_fp16(q, k, v, *a, **kw):\n    if q.dtype == torch.bfloat16 and q.is_cuda and torch.cuda.get_device_capability()[0] < 8:\n        if torch.is_tensor(kw.get("attn_mask")) and kw["attn_mask"].is_floating_point():\n            kw["attn_mask"] = kw["attn_mask"].half()\n        return _sdpa(q.half(), k.half(), v.half(), *a, **kw).to(torch.bfloat16)\n    return _sdpa(q, k, v, *a, **kw)\nF.scaled_dot_product_attention = _sdpa_fp16\npipe = CogVideoXPipeline.from_pretrained(MODEL_ID, torch_dtype=torch.bfloat16)\npipe.enable_model_cpu_offload()\npipe.vae.enable_tiling()\npipe.vae.enable_slicing()',
  gen=OPT + '''def generate(row, seed):
    return pipe(prompt=row["prompt"], negative_prompt=row.get("negative") or None, width=WIDTH, height=HEIGHT,
                num_frames=NUM_FRAMES,      # size and frames are fixed by this model, so those columns are ignored
                num_inference_steps=opt(row, "steps", STEPS), guidance_scale=opt(row, "guidance", GUIDANCE, float),
                generator=torch.Generator("cuda").manual_seed(seed)).frames[0]''')


_SDPA16 = """# A T4 has no fast bf16 attention kernel, so bf16 attention builds the whole matrix. Running just the attention in fp16 uses the memory-saving kernel.
import torch.nn.functional as F
_sdpa = F.scaled_dot_product_attention
def _sdpa_fp16(*a, **kw):                       # the caller may pass query/key/value by name or by position
    q = a[0] if a else kw["query"]
    if q.dtype == torch.bfloat16 and q.is_cuda and torch.cuda.get_device_capability()[0] < 8:
        half = lambda t: t.half() if torch.is_tensor(t) and t.is_floating_point() else t
        return _sdpa(*[half(x) for x in a], **{k: half(v) for k, v in kw.items()}).to(torch.bfloat16)
    return _sdpa(*a, **kw)
F.scaled_dot_product_attention = _sdpa_fp16

"""

MODELS["hunyuan_video_15"] = dict(
  title="HunyuanVideo 1.5 (8.3B, 4-bit)", repo="hunyuanvideo-community/HunyuanVideo-1.5-Diffusers-480p_t2v_distilled", fps=24,
  pip="!pip install -q -U diffusers transformers accelerate sentencepiece imageio imageio-ffmpeg ftfy bitsandbytes protobuf",
  note="Tencent's newer HunyuanVideo 1.5 (8.3B, 480p distilled text-to-video; Tencent Hunyuan community licence, not available in the EU, UK or South Korea). The transformer and the 7B text encoder are loaded in 4-bit (bitsandbytes) so they fit a T4 and Kaggle's system RAM; the download is about 48 GB. 24 fps. No negative prompt. EXPERIMENTAL: it runs on a T4, but at 6 to 30 steps the clips come out smeared with a woven texture (4-bit weights and fp16 attention are probably too coarse); not recommended until that is fixed.",
  config='MODEL_ID = "hunyuanvideo-community/HunyuanVideo-1.5-Diffusers-480p_t2v_distilled"\nWIDTH, HEIGHT = 640, 368    # multiples of 16\nNUM_FRAMES = 33            # 4*k+1, 1.4 s at 24 fps\nFPS = 24\nSTEPS = 30\nGUIDANCE = 1.0',
  load=_SDPA16 + """from diffusers import HunyuanVideo15Pipeline
from diffusers.quantizers import PipelineQuantizationConfig

_q = PipelineQuantizationConfig(quant_backend="bitsandbytes_4bit", quant_kwargs={"load_in_4bit": True, "bnb_4bit_quant_type": "nf4", "bnb_4bit_compute_dtype": torch.bfloat16},
                                components_to_quantize=["transformer", "text_encoder"])
pipe = HunyuanVideo15Pipeline.from_pretrained(MODEL_ID, quantization_config=_q, torch_dtype=torch.bfloat16)
pipe.enable_model_cpu_offload()
pipe.vae.enable_tiling(tile_sample_min_height=128, tile_sample_min_width=128, tile_latent_min_height=8, tile_latent_min_width=8)   # decode in small tiles: the whole clip at once asked for 14 GiB
print("VAE tiling:", pipe.vae.use_tiling, "tile (latent):", pipe.vae.tile_latent_min_height, pipe.vae.tile_latent_min_width)""",
  gen=OPT + '''def generate(row, seed):
    return pipe(prompt=row["prompt"], width=opt(row, "width", WIDTH), height=opt(row, "height", HEIGHT), num_frames=opt(row, "frames", NUM_FRAMES),
                num_inference_steps=opt(row, "steps", STEPS), generator=torch.Generator("cuda").manual_seed(seed)).frames[0]''')


# ---------------------------------------------------------------------------------------------------------------------------
# Image-to-video: each shot starts from its keyframe (a still made first by an image model and reviewed on the Storyboard), so the
# look, framing and characters are decided before any GPU time goes into motion. The run script puts the keyframes next to the CSV
# as kf-NNNN.png (NNNN = row number in all_shots.csv). Kaggle only: the Colab and Hugging Face runners do not upload them.
# ---------------------------------------------------------------------------------------------------------------------------
_KEYFRAME = '''from PIL import Image

_KF_ROOT = Path(CSV_PATH).parent if "CSV_PATH" in globals() else Path("/content")


def keyframe(row, width, height):
    """This row's keyframe, cropped to the clip's shape (centre) and resized. Stops the shot with a clear message if it is missing."""
    n = next(k for k, r in enumerate(shots, 1) if r is row)
    hits = sorted(_KF_ROOT.rglob(f"kf-{n:04d}.png"))
    if not hits:
        raise FileNotFoundError(f"no keyframe kf-{n:04d}.png for row {n}: make keyframes for these rows first (Movies tab, Storyboard)")
    img = Image.open(hits[0]).convert("RGB")
    want = width / height
    if img.width / img.height > want:                       # too wide: trim the sides
        w = round(img.height * want); x = (img.width - w) // 2
        img = img.crop((x, 0, x + w, img.height))
    else:                                                   # too tall: trim top and bottom
        h = round(img.width / want); y = (img.height - h) // 2
        img = img.crop((0, y, img.width, y + h))
    return img.resize((width, height), Image.LANCZOS)


'''

MODELS["ltx_video_i2v"] = dict(
  title="LTX-Video, from keyframes", repo="Lightricks/LTX-Video", fps=24,
  note="LTX-Video animating each shot's keyframe (image-to-video), so every clip starts from the still you approved on the Storyboard. Same speed and size as LTX-Video (768x320, ~4 s); fits a free T4. Needs keyframes for the rows first. Kaggle only. EXPERIMENTAL: not run on a GPU yet.",
  config=MODELS["ltx_video"]["config"],
  load='from diffusers import LTXImageToVideoPipeline\n\npipe = LTXImageToVideoPipeline.from_pretrained(MODEL_ID, torch_dtype=torch.bfloat16)\npipe.enable_model_cpu_offload()\npipe.vae.enable_tiling()',
  gen=OPT + _KEYFRAME + '''def generate(row, seed):
    w, h = opt(row, "width", WIDTH), opt(row, "height", HEIGHT)
    return pipe(image=keyframe(row, w, h), prompt=row["prompt"], negative_prompt=row.get("negative") or NEGATIVE,
                width=w, height=h, num_frames=opt(row, "frames", NUM_FRAMES),
                num_inference_steps=opt(row, "steps", STEPS), guidance_scale=opt(row, "guidance", GUIDANCE, float),
                max_sequence_length=256, generator=torch.Generator("cuda").manual_seed(seed)).frames[0]''')

MODELS["wan22_ti2v_5b_i2v"] = dict(
  title="Wan 2.2 (TI2V 5B), from keyframes", repo="Wan-AI/Wan2.2-TI2V-5B-Diffusers", fps=24,
  note="Wan 2.2's 5B model in its image-to-video mode (Apache-2.0): each shot starts from its keyframe, which keeps faces, costumes and sets the same from clip to clip. Better motion than LTX. Default 704x384, 33 frames at 24 fps (sizes are multiples of 32); slow on a T4. Needs keyframes for the rows first. Kaggle only. EXPERIMENTAL: not run on a GPU yet.",
  config=MODELS["wan22_ti2v_5b"]["config"],
  load="""from diffusers import AutoencoderKLWan, WanImageToVideoPipeline

vae = AutoencoderKLWan.from_pretrained(MODEL_ID, subfolder="vae", torch_dtype=torch.float32)     # a float32 VAE decodes cleanly
pipe = WanImageToVideoPipeline.from_pretrained(MODEL_ID, vae=vae, torch_dtype=torch.bfloat16)  # the 5B model needs no CLIP image encoder (expand_timesteps)
pipe.enable_model_cpu_offload()""",
  gen=OPT + _KEYFRAME + '''def generate(row, seed):
    w, h = opt(row, "width", WIDTH), opt(row, "height", HEIGHT)
    return pipe(image=keyframe(row, w, h), prompt=PROMPT_PREFIX + row["prompt"], negative_prompt=row.get("negative") or NEGATIVE,
                width=w, height=h, num_frames=opt(row, "frames", NUM_FRAMES),
                num_inference_steps=opt(row, "steps", STEPS), guidance_scale=opt(row, "guidance", GUIDANCE, float),
                generator=torch.Generator("cuda").manual_seed(seed)).frames[0]''')


def script(name, m):
    return f'''"""{m["title"]} generator. Runs ON the Colab VM (via `colab exec`). {m["note"]}

Renders shots START..END from /content/all_shots.csv into /content/videos, then tars them to
/content/batch_START_END.tar. START / END are injected by run_colab_model.sh.
"""
import csv, tarfile, time
from pathlib import Path

import torch
from diffusers.utils import export_to_video

START = globals().get("START", 1)
END = globals().get("END", 5)
{m["config"]}
NEGATIVE = "{NEG}"

OUT = Path("/content/videos"); OUT.mkdir(exist_ok=True)
shots = list(csv.DictReader(open("/content/all_shots.csv", newline="")))
END = min(END, len(shots))

{m["load"]}

{m["gen"]}

failed = []
for i in range(START, END + 1):
    out = OUT / f"shot-{{i:04d}}.mp4"
    if out.exists():
        continue
    t = time.time()
    try:
        export_to_video(generate(shots[i - 1], opt(shots[i - 1], "seed", i)), str(out), fps=FPS)
        print(f"[{{i}}/{{END}}] ok ({{time.time() - t:.0f}}s)", flush=True)
    except Exception as e:
        torch.cuda.empty_cache(); failed.append(i)
        print(f"[{{i}}/{{END}}] FAILED: {{e}}", flush=True)

tar = f"/content/batch_{{START}}_{{END}}.tar"
with tarfile.open(tar, "w") as tf:
    for p in sorted(OUT.glob("shot-*.mp4")):
        tf.add(p, arcname=p.name)
print("failed:", failed or "none"); print("tar:", tar)
'''

def md(t): return {"cell_type":"markdown","metadata":{},"source":t.strip().splitlines(True)}
def code(t): return {"cell_type":"code","metadata":{},"execution_count":None,"outputs":[],"source":t.strip().splitlines(True)}

PIP = "!pip install -q -U diffusers transformers accelerate sentencepiece imageio imageio-ffmpeg ftfy"
SUFFIX = "SUFFIX = '' if CSV_NAME == 'all_shots.csv' else '_chapters'   # keeps per-shot and per-chapter clips apart"
CSV_LINE = "CSV_NAME = 'all_shots.csv'   # or 'all_chapters.csv' for ONE prompt per chapter (~209 clips)"
LOOP = """failed = []
last = min(END, len(shots))
for i in range(START, last + 1):
    out = OUT / f'shot-{i:04d}.mp4'
    if out.exists():
        continue
    t = time.time()
    try:
        export_to_video(generate(shots[i-1], opt(shots[i-1], 'seed', i)), str(out), fps=FPS)
        print(f"[{i}/{last}] {shots[i-1]['chapter']} ok ({time.time()-t:.0f}s)")
    except Exception as e:
        torch.cuda.empty_cache(); failed.append(i)
        print(f'[{i}/{last}] FAILED: {e}'); import traceback; traceback.print_exc(limit=-4)
print('failed:', failed or 'none')
if failed and len(failed) == last - START + 1:
    raise RuntimeError(f'all {len(failed)} shot(s) failed; see the messages above')"""

def notebook(name, m, platform):
    if platform == "colab":
        intro = (f"# Pistachio's Studio: {m['title']} on Colab\n\n{m['note']}\n\n"
                 "Runtime → Change runtime type → **T4 GPU**. Put `all_shots.csv` / `all_chapters.csv` in `MyDrive/PistachioStudio/`.")
        setup = [code("from google.colab import drive\ndrive.mount('/content/drive')")]
        paths = ("from pathlib import Path\nBASE = Path('/content/drive/MyDrive/PistachioStudio')\n" + CSV_LINE +
                 "\nCSV_PATH = BASE / CSV_NAME\n" + SUFFIX + f"\nOUT = BASE / 'videos' / ('{name}' + SUFFIX)")
    else:
        intro = (f"# Pistachio's Studio: {m['title']} on Kaggle\n\n{m['note']}\n\n"
                 "Right panel: **Accelerator = GPU T4 x2**, **Internet = On**, add your dataset containing `all_shots.csv` / `all_chapters.csv`. "
                 "Clips are written to `/kaggle/working/videos/` and show up in the Output tab.")
        setup = []
        paths = ("from pathlib import Path\n" + CSV_LINE +
                 "\nCSV_PATH = next(Path('/kaggle/input').rglob(CSV_NAME))   # found wherever the dataset is mounted\n" + SUFFIX +
                 f"\nOUT = Path('/kaggle/working/videos') / ('{name}' + SUFFIX)")
    config = (paths + "\nSTART, END = 1, 10          # row numbers in the CSV (1-based); raise END once you like the look\n"
              + m["config"] + f'\nNEGATIVE = "{NEG}"\nOUT.mkdir(parents=True, exist_ok=True)')
    # Hugging Face token from the notebook's secrets (Kaggle: Add-ons > Secrets, label HF_TOKEN; Colab: the key icon). Optional: all models used here are public,
    # the token only gives faster downloads and higher rate limits. It is never printed.
    if platform == "colab":
        secret = "import os\ntry:\n    from google.colab import userdata\n    os.environ['HF_TOKEN'] = userdata.get('HF_TOKEN')\nexcept Exception:\n    pass\nprint('HF token:', 'found' if os.environ.get('HF_TOKEN') else 'not set (public models still work)')"
    else:
        secret = "import os\ntry:\n    from kaggle_secrets import UserSecretsClient\n    os.environ['HF_TOKEN'] = UserSecretsClient().get_secret('HF_TOKEN')\nexcept Exception:\n    pass\nprint('HF token:', 'found' if os.environ.get('HF_TOKEN') else 'not set (public models still work)')"
    cells = [md(intro), code(m.get("pip", PIP)), code(secret)] + setup + [
        code(config),
        code("import csv, time, torch\nfrom diffusers.utils import export_to_video\n"
             "shots = list(csv.DictReader(open(CSV_PATH, newline='')))\nprint(len(shots), 'rows from', CSV_PATH)"),
        code(m["load"]), code(m["gen"]), code(LOOP)]
    meta = {"accelerator": "GPU", "colab": {"gpuType": "T4"}} if platform == "colab" else {}
    meta["kernelspec"] = {"display_name": "Python 3", "name": "python3"}
    return {"cells": cells, "metadata": meta, "nbformat": 4, "nbformat_minor": 0}

for name, m in MODELS.items():
    (root / f"colab_generate_{name}.py").write_text(script(name, m))
    json.dump(notebook(name, m, "colab"), open(root / f"Studio_Colab_{name}.ipynb", "w"), indent=1)
    json.dump(notebook(name, m, "kaggle"), open(root / f"Studio_Kaggle_{name}.ipynb", "w"), indent=1)
