import json
from pathlib import Path
import os as _os
root = Path(_os.environ["STUDIO_GEN_DIR"]) if _os.environ.get("STUDIO_GEN_DIR") else Path(__file__).resolve().parent.parent   # STUDIO_GEN_DIR: write somewhere else (the run scripts use a throw-away folder)

HEADER = '''import csv, os, subprocess, sys, tarfile, time
from pathlib import Path

def sh(cmd):
    subprocess.run(cmd, shell=True, check=True)

# Injected by run_colab_model.sh / the notebooks; defaults suit `colab exec` on a fresh VM.
START = globals().get("START", 1)
END = globals().get("END", 5)
CSV_PATH = globals().get("CSV_PATH", "/content/all_shots.csv")
OUT = Path(globals().get("OUT", "/content/audio"))
MAKE_TAR = globals().get("MAKE_TAR", True)
OUT.mkdir(parents=True, exist_ok=True)
rows = list(csv.DictReader(open(CSV_PATH, newline="")))
END = min(END, len(rows))
failed = []
'''

FOOTER = '''
if MAKE_TAR:
    tar = f"/content/batch_{START}_{END}.tar"
    with tarfile.open(tar, "w") as tf:
        for p in sorted(OUT.glob("*.wav")):
            tf.add(p, arcname=p.name)
    print("tar:", tar)
print("failed:", failed or "none")
if failed and len(failed) == END - START + 1:
    raise RuntimeError(f"all {len(failed)} row(s) failed; see the messages above")
'''

KOKORO_WORKER = r'''import csv, json, sys, time
from pathlib import Path
import numpy as np, soundfile as sf
from kokoro import KPipeline

csv_path, start, end, out_dir = sys.argv[1], int(sys.argv[2]), int(sys.argv[3]), Path(sys.argv[4])
out_dir.mkdir(parents=True, exist_ok=True)
rows = list(csv.DictReader(open(csv_path, newline="")))
end = min(end, len(rows))

# (language code, voice, speed). Names not listed fall back to the male or female default.
VOICES = {"NARRATOR": ("b", "bm_george", 0.95), "WORD": ("b", "bm_lewis", 0.85), "THE LORD": ("b", "bm_lewis", 0.85),
          "ANGELS": ("b", "bm_lewis", 0.9), "SATAN": ("a", "am_adam", 0.9),
          "EVE": ("a", "af_bella", 1.0), "LULUWA": ("a", "af_bella", 1.0)}
FEMALE = {"EVE", "LULUWA", "AWAN", "HAWA"}
pipes = {"a": KPipeline(lang_code="a"), "b": KPipeline(lang_code="b")}
SR = 24000


def speak(speaker, text, voice=None):
    """voice (third item of a line, set for new books) wins over the table; its first letter is the language (a/b)."""
    if voice:
        lang, speed = voice[0], 1.0
    else:
        lang, voice, speed = VOICES.get(speaker, ("a", "af_bella" if speaker in FEMALE else "am_michael", 1.0))
    parts = [np.asarray(a, dtype=np.float32) for _, _, a in pipes[lang](text, voice=voice, speed=speed)]
    return np.concatenate(parts) if parts else np.zeros(0, dtype=np.float32)


failed, tried = [], 0
for i in range(start, end + 1):
    out = out_dir / f"narration-{i:04d}.wav"
    lines = json.loads(rows[i - 1]["lines_json"])
    if out.exists() or not lines:
        continue
    tried += 1
    t = time.time()
    try:
        gap = np.zeros(int(SR * 0.35), dtype=np.float32)
        audio = np.concatenate([np.concatenate([speak(*item), gap]) for item in lines])   # item = [speaker, text, (voice)]
        sf.write(str(out), audio, SR)
        print(f"[{i}/{end}] {rows[i-1]['chapter']} ok ({len(audio)/SR:.1f}s audio, {time.time()-t:.0f}s)", flush=True)
    except Exception as e:
        failed.append(i); print(f"[{i}/{end}] FAILED: {e}", flush=True)
print("failed:", failed or "none")
if tried and len(failed) == tried:
    sys.exit(1)
'''

CHATTERBOX_WORKER = r'''import csv, json, sys, time
from pathlib import Path
import numpy as np, soundfile as sf, torch
from chatterbox.tts_turbo import ChatterboxTurboTTS

csv_path, start, end, out_dir = sys.argv[1], int(sys.argv[2]), int(sys.argv[3]), Path(sys.argv[4])
out_dir.mkdir(parents=True, exist_ok=True)
rows = list(csv.DictReader(open(csv_path, newline="")))
end = min(end, len(rows))
model = ChatterboxTurboTTS.from_pretrained(device="cuda")
sr = model.sr
failed, tried = [], 0
for i in range(start, end + 1):
    out = out_dir / f"narration-{i:04d}.wav"
    lines = json.loads(rows[i - 1]["lines_json"])
    if out.exists() or not lines:
        continue
    tried += 1
    t = time.time()
    try:
        parts = []
        for item in lines:                                   # item = [speaker, text, (voice)]
            wav = model.generate(item[1])
            parts += [wav.squeeze().cpu().numpy().astype(np.float32), np.zeros(int(sr * 0.35), dtype=np.float32)]
        sf.write(str(out), np.concatenate(parts), sr)
        print(f"[{i}/{end}] {rows[i-1]['chapter']} ok ({time.time()-t:.0f}s)", flush=True)
    except Exception as e:
        torch.cuda.empty_cache(); failed.append(i); print(f"[{i}/{end}] FAILED: {e}", flush=True)
print("failed:", failed or "none")
if tried and len(failed) == tried:
    sys.exit(1)
'''

KINDS = {
"kokoro": dict(title="Kokoro narration", prefix="narration", csv_hint="audio_shots.csv",
 note="Text-to-speech for the narrator and speaking characters (24 kHz wav). Runs on CPU or GPU. Voices are picked per speaker from the `lines_json` column.",
 body='''
import shlex
sh("apt-get -qq update && apt-get -qq install -y espeak-ng > /dev/null")
# Kaggle's image now runs Python 3.13, where Kokoro's dependency spacy cannot be built (the first Kaggle run failed on exactly
# that), so Kokoro runs in a Python 3.12 environment made with uv. uv downloads Python 3.12 if the machine has none.
sh(f"{sys.executable} -m pip install -q uv")
PYENV = "/tmp/kokoro_py312"
sh(f"{sys.executable} -m uv venv --python 3.12 --seed {PYENV}")
sh(f"{PYENV}/bin/python -m pip install -q kokoro soundfile numpy")
WORKER = @@WORKER@@
Path("/tmp/kokoro_worker.py").write_text(WORKER)
sh(f"{PYENV}/bin/python /tmp/kokoro_worker.py {shlex.quote(str(CSV_PATH))} {START} {END} {shlex.quote(str(OUT))}")
'''),
"musicgen": dict(title="MusicGen music", prefix="music", csv_hint="audio_shots.csv",
 note="Background score from the `music` column using Meta's MusicGen (small). 15 s per row, or 28 s per chapter in chapter mode. Check the model license for how you plan to use the music.",
 body='''
sh(f"{sys.executable} -m pip install -q -U transformers accelerate scipy")
import numpy as np, scipy.io.wavfile as wavfile, torch
from transformers import AutoProcessor, MusicgenForConditionalGeneration

SECONDS = 28 if "chapters" in str(CSV_PATH) else 15     # length of each clip (about 50 tokens per second): a chapter's cue is long enough to loop gently
dev = "cuda" if torch.cuda.is_available() else "cpu"
processor = AutoProcessor.from_pretrained("facebook/musicgen-small")
model = MusicgenForConditionalGeneration.from_pretrained("facebook/musicgen-small").to(dev)
sr = model.config.audio_encoder.sampling_rate

for i in range(START, END + 1):
    out = OUT / f"music-{i:04d}.wav"
    if out.exists():
        continue
    t = time.time()
    try:
        inputs = processor(text=[rows[i - 1]["music"]], padding=True, return_tensors="pt").to(dev)
        audio = model.generate(**inputs, do_sample=True, guidance_scale=3.0, max_new_tokens=int(SECONDS * 50))
        wavfile.write(str(out), sr, audio[0, 0].cpu().numpy().astype(np.float32))
        print(f"[{i}/{END}] {rows[i-1]['chapter']} ok ({time.time()-t:.0f}s)", flush=True)
    except Exception as e:
        torch.cuda.empty_cache(); failed.append(i); print(f"[{i}/{END}] FAILED: {e}", flush=True)
'''),
"mmaudio": dict(title="MMAudio sound effects", prefix="sfx", csv_hint="audio_shots.csv",
 note="Sound effects and ambience from the `sfx` column (text-to-audio mode of MMAudio; it does not look at the video). 8 s per row. This is the least certain of the three: the command-line flags are from memory of the MMAudio repo, so check its README if a call fails.",
 body='''
if not Path("MMAudio").exists():
    sh("git clone -q https://github.com/hkchengrex/MMAudio.git")
sh(f"{sys.executable} -m pip install -q -e MMAudio soundfile")
import glob, shutil
import soundfile as sf

SECONDS = 8
TMP = Path("mmaudio_tmp"); TMP.mkdir(exist_ok=True)

for i in range(START, END + 1):
    out = OUT / f"sfx-{i:04d}.wav"
    if out.exists():
        continue
    t = time.time()
    try:
        for old in TMP.glob("*"):
            old.unlink()
        # demo.py names its output file after the prompt text, and a file name longer than 255 characters cannot be written (a long scene
        # description made "avio_open failed"). Sound-effect prompts are short anyway, so cut at a word boundary well under that limit.
        prompt = " ".join(rows[i - 1]["sfx"].split())
        if len(prompt) > 150:
            prompt = prompt[:150].rsplit(" ", 1)[0]
        sh(f'cd MMAudio && {sys.executable} demo.py --duration={SECONDS} --output ../{TMP} '
           f'--seed {i} --prompt {json_q(prompt)} --negative_prompt "music, speech, voice"')
        made = sorted(TMP.glob("*.flac")) + sorted(TMP.glob("*.wav"))
        if not made:
            raise RuntimeError("MMAudio wrote no audio file (check its README for current flags)")
        data, sr = sf.read(str(made[0]))
        sf.write(str(out), data, sr)
        print(f"[{i}/{END}] {rows[i-1]['chapter']} ok ({time.time()-t:.0f}s)", flush=True)
    except Exception as e:
        failed.append(i); print(f"[{i}/{END}] FAILED: {e}", flush=True)
'''),
"qwen3_tts": dict(title="Qwen3-TTS narration", prefix="narration", csv_hint="audio_shots.csv",
 note="Text-to-speech for the narrator and speaking characters with Qwen3-TTS 1.7B (Apache-2.0, Jan 2026), a newer and more natural voice than Kokoro (24 kHz wav). Needs a GPU. Speakers named in FEMALE get the female voice, everyone else the male voice; the language is detected from the text.",
 body='''
sh(f"{sys.executable} -m pip install -q -U qwen-tts soundfile")
import json, numpy as np, soundfile as sf, torch
from qwen_tts import Qwen3TTSModel

model = Qwen3TTSModel.from_pretrained("Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice", device_map="cuda:0", dtype=torch.bfloat16, attn_implementation="sdpa")
try:
    print("speakers:", model.get_supported_speakers())
except Exception as e:
    print("speaker list not available:", e)
FEMALE = {"EVE", "LULUWA", "AWAN", "HAWA"}
MALE_VOICE, FEMALE_VOICE = "Ryan", "Serena"

for i in range(START, END + 1):
    out = OUT / f"narration-{i:04d}.wav"
    lines = json.loads(rows[i - 1]["lines_json"])
    if out.exists() or not lines:
        continue
    t = time.time()
    try:
        parts, sr = [], 24000
        for item in lines:                                   # item = [speaker, text, (voice)]
            wavs, sr = model.generate_custom_voice(text=item[1], language="Auto", speaker=FEMALE_VOICE if item[0] in FEMALE else MALE_VOICE)
            parts += [np.asarray(wavs[0], dtype=np.float32), np.zeros(int(sr * 0.35), dtype=np.float32)]
        sf.write(str(out), np.concatenate(parts), sr)
        print(f"[{i}/{END}] {rows[i-1]['chapter']} ok ({time.time()-t:.0f}s)", flush=True)
    except Exception as e:
        torch.cuda.empty_cache(); failed.append(i); print(f"[{i}/{END}] FAILED: {e}", flush=True)
'''),
"chatterbox_turbo": dict(title="Chatterbox-Turbo narration", prefix="narration", csv_hint="audio_shots.csv",
 note="Text-to-speech with Resemble AI's Chatterbox-Turbo (MIT, Dec 2025): fast, natural, and it understands tags such as [chuckle] in the text. One default voice for every speaker. Needs a GPU. 24 kHz wav. It pins an older torch, so it runs in its own Python 3.12 environment made with uv (like Kokoro) and does not disturb the notebook's torch.",
 body='''
import shlex
sh(f"{sys.executable} -m pip install -q uv")
PYENV = "/tmp/chatterbox_py312"
sh(f"{sys.executable} -m uv venv --python 3.12 --seed {PYENV}")
sh(f"{PYENV}/bin/python -m pip install -q chatterbox-tts soundfile numpy 'setuptools<81'")      # perth (its watermarker) needs pkg_resources, which setuptools 81+ removed
WORKER = @@CWORKER@@
Path("/tmp/chatterbox_worker.py").write_text(WORKER)
sh(f"{PYENV}/bin/python /tmp/chatterbox_worker.py {shlex.quote(str(CSV_PATH))} {START} {END} {shlex.quote(str(OUT))}")
'''),
}
KINDS["kokoro"]["body"] = KINDS["kokoro"]["body"].replace("@@WORKER@@", repr(KOKORO_WORKER))
KINDS["chatterbox_turbo"]["body"] = KINDS["chatterbox_turbo"]["body"].replace("@@CWORKER@@", repr(CHATTERBOX_WORKER))
KINDS["mmaudio"]["body"] = "import shlex\njson_q = shlex.quote\n" + KINDS["mmaudio"]["body"]

def script(k, m):
    return f'"""{m["title"]}. Runs ON the Colab/Kaggle VM. {m["note"]}\n\nReads {m["csv_hint"]} (or the chapters variant) rows START..END and writes {m["prefix"]}-NNNN.wav files.\n"""\n' + HEADER + m["body"] + FOOTER

def md(t): return {"cell_type": "markdown", "metadata": {}, "source": t.strip().splitlines(True)}
def code(t): return {"cell_type": "code", "metadata": {}, "execution_count": None, "outputs": [], "source": t.strip().splitlines(True)}

def notebook(k, m, platform):
    SUF = "SUFFIX = '_chapters' if 'chapters' in CSV_NAME else ''"
    if platform == "colab":
        intro = f"# Pistachio's Studio audio: {m['title']} on Colab\n\n{m['note']}\n\nPut `audio_shots.csv` / `audio_chapters.csv` in `MyDrive/PistachioStudio/`."
        setup = [code("from google.colab import drive\ndrive.mount('/content/drive')")]
        paths = ("from pathlib import Path\nBASE = Path('/content/drive/MyDrive/PistachioStudio')\nCSV_NAME = 'audio_shots.csv'   # or 'audio_chapters.csv'\n"
                 "CSV_PATH = BASE / CSV_NAME\n" + SUF + f"\nOUT = BASE / 'audio' / ('{k}' + SUFFIX)")
    else:
        intro = (f"# Pistachio's Studio audio: {m['title']} on Kaggle\n\n{m['note']}\n\nAccelerator = GPU T4 x2, Internet = On, "
                 "dataset with the CSVs attached. Files go to `/kaggle/working/audio/`.")
        setup = []
        paths = ("from pathlib import Path\nCSV_NAME = 'audio_shots.csv'   # or 'audio_chapters.csv'\n"
                 "CSV_PATH = next(Path('/kaggle/input').rglob(CSV_NAME))\n" + SUF + f"\nOUT = Path('/kaggle/working/audio') / ('{k}' + SUFFIX)")
    cfg = paths + "\nSTART, END = 1, 10   # CSV row numbers (1-based)\nMAKE_TAR = False"
    meta = {"accelerator": "GPU"} if platform == "colab" else {}
    meta["kernelspec"] = {"display_name": "Python 3", "name": "python3"}
    return {"cells": [md(intro)] + setup + [code(cfg), code(script(k, m))], "metadata": meta, "nbformat": 4, "nbformat_minor": 0}

for k, m in KINDS.items():
    (root / f"colab_generate_audio_{k}.py").write_text(script(k, m))
    json.dump(notebook(k, m, "colab"), open(root / f"Studio_Colab_audio_{k}.ipynb", "w"), indent=1)
    json.dump(notebook(k, m, "kaggle"), open(root / f"Studio_Kaggle_audio_{k}.ipynb", "w"), indent=1)
