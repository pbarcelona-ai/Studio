#!/usr/bin/env python3
"""Export a finished film for a destination: YouTube, a festival, a 1080p or 4K master, a vertical short, a small web copy.

  uv run --with imageio-ffmpeg python export_film.py --project BOOK --film my_film.mp4 --preset youtube_1080p
        [--languages es,fr] [--engine claude --model sonnet] [--audio-track es=audio/dub_es.wav] [--out name]

The film is a file in the book's films/ folder. The result is films/<name>_<preset>.<ext>. Captions: the film's own .srt (same name, made by Make film) is
muxed in as a soft subtitle track and also copied next to the export; --languages translates it with the AI engine into more subtitle tracks (checked to keep
every cue and its timing). --audio-track adds a dubbed audio track you made yourself (language=file inside the project).
Honest limits: a 4K master made from clips that are smaller is the same picture scaled up (use the upscalers first for real detail). Loudness is
mastered in two passes (loudnorm linear mode) with automatic fallback to single-pass when measurement is unavailable (e.g. silent audio).
"""
import argparse
import json
import math
import re
import shutil
import subprocess
import sys
from pathlib import Path

# name -> (label, width, height, fps or None, video args, audio args, loudness LUFS or None, container, note)
PRESETS = {
    "youtube_1080p": ("YouTube 1080p", 1920, 1080, None, ["-c:v", "libx264", "-preset", "slow", "-crf", "18", "-profile:v", "high", "-pix_fmt", "yuv420p"],
                      ["-c:a", "aac", "-b:a", "192k", "-ar", "48000"], -14, "mp4", "H.264 + AAC, -14 LUFS, fast start (plays while it loads)"),
    "youtube_4k": ("YouTube 4K", 3840, 2160, None, ["-c:v", "libx264", "-preset", "slow", "-crf", "16", "-profile:v", "high", "-pix_fmt", "yuv420p"],
                   ["-c:a", "aac", "-b:a", "256k", "-ar", "48000"], -14, "mp4", "H.264 + AAC at 3840x2160, -14 LUFS"),
    "festival": ("Festival screener", 1920, 1080, 24, ["-c:v", "libx264", "-preset", "slow", "-crf", "14", "-profile:v", "high", "-pix_fmt", "yuv420p", "-color_primaries", "bt709",
                                                       "-color_trc", "bt709", "-colorspace", "bt709"], ["-c:a", "aac", "-b:a", "320k", "-ar", "48000"], -23, "mp4",
                 "H.264 1080p at 24 fps, high bitrate, -23 LUFS (broadcast level)"),
    "master_1080p": ("Master 1080p (ProRes)", 1920, 1080, None, ["-c:v", "prores_ks", "-profile:v", "3", "-pix_fmt", "yuv422p10le"], ["-c:a", "pcm_s24le", "-ar", "48000"], None, "mov",
                     "ProRes 422 HQ + 24-bit PCM, loudness untouched; large files"),
    "master_4k": ("Master 4K (ProRes)", 3840, 2160, None, ["-c:v", "prores_ks", "-profile:v", "3", "-pix_fmt", "yuv422p10le"], ["-c:a", "pcm_s24le", "-ar", "48000"], None, "mov",
                  "ProRes 422 HQ 3840x2160; very large files"),
    "vertical_short": ("Vertical short (9:16)", 1080, 1920, None, ["-c:v", "libx264", "-preset", "slow", "-crf", "20", "-profile:v", "high", "-pix_fmt", "yuv420p"],
                       ["-c:a", "aac", "-b:a", "192k", "-ar", "48000"], -14, "mp4", "centre-cropped to 1080x1920 for Shorts / Reels / TikTok (the sides are cut off)"),
    "web_small": ("Small web copy", 1280, 720, None, ["-c:v", "libx264", "-preset", "medium", "-crf", "24", "-pix_fmt", "yuv420p"], ["-c:a", "aac", "-b:a", "128k", "-ar", "44100"],
                  -16, "mp4", "720p, small file for sharing a preview"),
}
LANG_RE = re.compile(r"^[a-z]{2,3}(-[A-Za-z]{2,4})?$")
ISO3 = {"en": "eng", "es": "spa", "fr": "fra", "de": "deu", "it": "ita", "pt": "por", "ja": "jpn", "zh": "zho", "ko": "kor", "ru": "rus", "ar": "ara", "hi": "hin", "nl": "nld",
        "sv": "swe", "no": "nor", "da": "dan", "fi": "fin", "pl": "pol", "tr": "tur", "uk": "ukr", "he": "heb", "el": "ell", "cs": "ces", "hu": "hun", "ro": "ron", "th": "tha",
        "vi": "vie", "id": "ind", "fa": "fas", "bn": "ben", "ta": "tam", "sw": "swa", "la": "lat", "cy": "cym", "ga": "gle"}


def lang3(code: str) -> str:
    """The three-letter code MP4 and MOV files store for a language ("pt-BR" -> "por"); "und" (undetermined) when we do not know it."""
    base = code.split("-")[0].lower()
    return ISO3.get(base, base if len(base) == 3 else "und")


class ExportError(ValueError):
    """A readable reason an export cannot be made."""


def find_ffmpeg() -> str:
    exe = shutil.which("ffmpeg")
    if exe:
        return exe
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except ImportError as e:
        raise ExportError("No ffmpeg. Run with: uv run --with imageio-ffmpeg python export_film.py ...") from e


def probe(ffmpeg: str, path: Path) -> dict:
    """{width, height, fps, seconds, has_audio} of a media file, read from ffmpeg's report."""
    err = subprocess.run([ffmpeg, "-i", str(path)], capture_output=True, text=True, stdin=subprocess.DEVNULL).stderr
    line = next((ln for ln in err.splitlines() if "Video:" in ln), "")
    size, fps = re.search(r", (\d{2,5})x(\d{2,5})", line), re.search(r"([\d.]+) fps", line)
    dur = re.search(r"Duration:\s*(\d+):(\d+):(\d+\.\d+)", err)
    if not size:
        raise ExportError(f"cannot read the picture size of {path.name}")
    return {"width": int(size.group(1)), "height": int(size.group(2)), "fps": float(fps.group(1)) if fps else 24.0,
            "seconds": int(dur.group(1)) * 3600 + int(dur.group(2)) * 60 + float(dur.group(3)) if dur else 0.0, "has_audio": "Audio:" in err}


def video_filter(preset: str, src: dict) -> str:
    _, w, h, fps, *_ = PRESETS[preset]
    if preset == "vertical_short":                       # centre crop to 9:16, then scale
        chain = ["crop='min(iw,ih*9/16)':'min(ih,iw*16/9)'", f"scale={w}:{h}:flags=lanczos"]
    else:
        chain = [f"scale={w}:{h}:force_original_aspect_ratio=decrease:flags=lanczos", f"pad={w}:{h}:(ow-iw)/2:(oh-ih)/2:color=black"]
    chain.append("setsar=1")
    if fps:
        chain.append(f"fps={fps}")
    return ",".join(chain)


def parse_srt(text: str) -> list[tuple[str, str, str]]:
    """[(index, timing line, text)] of an SRT file."""
    out = []
    for block in re.split(r"\n\s*\n", text.strip().replace("\r\n", "\n")):
        lines = block.split("\n")
        if len(lines) >= 3 and "-->" in lines[1]:
            out.append((lines[0].strip(), lines[1].strip(), "\n".join(lines[2:]).strip()))
    return out


def render_srt(cues: list[tuple[str, str, str]]) -> str:
    return "".join(f"{i}\n{t}\n{x}\n\n" for i, t, x in cues)


def translate_cues(cues, language: str, llm, batch: int = 40):
    """Cues with the same numbers and timings and the text in `language`. llm(prompt, validate) -> the parsed JSON {"lines": [...]}. Raises if the model loses a line."""
    out = []
    for lo in range(0, len(cues), batch):
        part = cues[lo: lo + batch]
        prompt = (f"Translate these subtitle lines into {language}. Keep the meaning and the register; do not merge or split lines; keep names. "
                  f'Reply with one JSON object {{"lines": [...]}} with exactly {len(part)} strings in the same order.\n\n' + "\n".join(f"{n + 1}: {c[2]}" for n, c in enumerate(part)))

        n = len(part)

        def check(d, n=n):
            if not isinstance(d.get("lines"), list) or len(d["lines"]) != n or not all(isinstance(x, str) and x.strip() for x in d["lines"]):
                raise ValueError(f"'lines' must be a list of exactly {n} non-empty strings")
        data = llm(prompt, check)
        out += [(c[0], c[1], re.sub(r"\n\s*\n+", "\n", t.strip()).replace("-->", "->")) for c, t in zip(part, data["lines"], strict=True)]     # a blank line or an arrow would break the SRT
    return out


def parse_loudnorm_stats(stderr_text: str) -> dict[str, str] | None:
    """Extract the JSON measurement block printed by ffmpeg's loudnorm pass 1, or None if missing/non-finite."""
    matches = re.findall(r"\{[^{}]*\"input_i\"[^{}]*\}", stderr_text, flags=re.DOTALL)
    if not matches:
        return None
    try:
        data = json.loads(matches[-1])
    except ValueError:
        return None
    keys = ("input_i", "input_tp", "input_lra", "input_thresh", "target_offset")
    out: dict[str, str] = {}
    for k in keys:
        val = str(data.get(k, "")).strip()
        try:
            num = float(val)
        except ValueError:
            return None
        if not math.isfinite(num):
            return None
        out[k] = val
    return out


def measure_loudness(ffmpeg: str, src: Path, target_lufs: float, tp: float = -1.5, lra: float = 11.0) -> dict[str, str] | None:
    """Run loudnorm pass 1 on `src` and return measured stats for linear two-pass normalization, or None on failure/silence."""
    cmd = [ffmpeg, "-hide_banner", "-nostats", "-i", str(src), "-vn",
           "-af", f"loudnorm=I={target_lufs}:TP={tp}:LRA={lra}:print_format=json", "-f", "null", "-"]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, stdin=subprocess.DEVNULL, timeout=180)
    except (OSError, subprocess.SubprocessError):
        return None
    if r.returncode != 0:
        return None
    return parse_loudnorm_stats(r.stderr)


def loudnorm_filter(target_lufs: float, measured: dict[str, str] | None = None, tp: float = -1.5, lra: float = 11.0) -> str:
    """Build a two-pass linear loudnorm filter when `measured` stats are available, else single-pass fallback."""
    base = f"loudnorm=I={target_lufs}:TP={tp}:LRA={lra}"
    if not measured:
        return base
    return (f"{base}:measured_I={measured['input_i']}:measured_TP={measured['input_tp']}:"
            f"measured_LRA={measured['input_lra']}:measured_thresh={measured['input_thresh']}:"
            f"offset={measured['target_offset']}:linear=true")


def build_command(ffmpeg, src: Path, dest: Path, preset: str, info: dict, subs: list[tuple[Path, str]], audio_tracks: list[tuple[Path, str]],
                  title: str = "", loudnorm_stats: dict[str, str] | None = None) -> list[str]:
    label, w, h, fps, vargs, aargs, lufs, container, _ = PRESETS[preset]
    cmd = [ffmpeg, "-y", "-loglevel", "error", "-i", str(src)]
    for p, _lang in subs:
        cmd += ["-i", str(p)]
    for p, _lang in audio_tracks:
        cmd += ["-i", str(p)]
    n_sub, n_aud = len(subs), len(audio_tracks)
    cmd += ["-map", "0:v:0"]
    if info["has_audio"]:
        cmd += ["-map", "0:a:0"]
    cmd += [f for i in range(n_aud) for f in ("-map", f"{1 + n_sub + i}:a:0")]
    cmd += [f for i in range(n_sub) for f in ("-map", f"{1 + i}:0")]
    cmd += ["-vf", video_filter(preset, info)] + vargs
    if info["has_audio"] or n_aud:
        if lufs is not None and info["has_audio"]:
            cmd += ["-af", loudnorm_filter(lufs, loudnorm_stats)]
        cmd += aargs
    if n_sub:
        cmd += ["-c:s", "mov_text" if container == "mp4" else "srt" if container == "mkv" else "mov_text"]
    for i, (_, lang) in enumerate(subs):
        cmd += [f"-metadata:s:s:{i}", f"language={lang3(lang)}"]
    for i, (_, lang) in enumerate(audio_tracks):
        cmd += [f"-metadata:s:a:{i + (1 if info['has_audio'] else 0)}", f"language={lang3(lang)}"]
    if title:
        cmd += ["-metadata", f"title={title}"]
    if container == "mp4":
        cmd += ["-movflags", "+faststart"]
    return cmd + [str(dest)]


def export(project_dir: Path, film: str, preset: str, languages: list[str], llm=None, audio_tracks: list[tuple[str, str]] | None = None, out: str = "", title: str = "") -> dict:
    """Make the export. Returns {"file": path, "preset": ..., "subtitles": [languages], "seconds": n}."""
    if preset not in PRESETS:
        raise ExportError(f"preset must be one of {', '.join(PRESETS)}")
    ffmpeg = find_ffmpeg()
    films = Path(project_dir) / "films"
    src = (films / film).resolve()
    if films.resolve() not in src.parents or src.suffix.lower() != ".mp4" or not src.is_file():
        raise ExportError(f"{film} is not a film in this book's films folder")
    for lang in languages:
        if not LANG_RE.match(lang):
            raise ExportError(f"{lang!r} is not a language code (for example es or pt-BR)")
    name = out or f"{src.stem}_{preset}"
    if not re.fullmatch(r"[A-Za-z0-9_.-]{1,80}", name):
        raise ExportError("the export name may use letters, digits, . _ - only")
    container = PRESETS[preset][7]
    dest = films / f"{name}.{container}"
    info = probe(ffmpeg, src)
    subs: list[tuple[Path, str]] = []
    srt = src.with_suffix(".srt")
    made: list[str] = []
    if srt.is_file():
        cues = parse_srt(srt.read_text(encoding="utf-8"))
        if cues:
            shutil.copyfile(srt, films / f"{name}.en.srt")
            subs.append((films / f"{name}.en.srt", "en"))
            made.append("en")
            for lang in languages:
                if llm is None:
                    raise ExportError("translating subtitles needs the AI engine")
                tr = translate_cues(cues, lang, llm)
                p = films / f"{name}.{lang}.srt"
                p.write_text(render_srt(tr), encoding="utf-8")
                subs.append((p, lang))
                made.append(lang)
    elif languages:
        raise ExportError(f"{src.name} has no captions ({srt.name}) to translate: make the film with captions first")
    tracks: list[tuple[Path, str]] = []
    for lang, rel in audio_tracks or []:
        p = (Path(project_dir) / rel).resolve()
        if Path(project_dir).resolve() not in p.parents or not p.is_file() or not LANG_RE.match(lang):
            raise ExportError(f"audio track {lang}={rel}: choose a language code and a file inside the book's folder")
        tracks.append((p, lang))
    lufs = PRESETS[preset][6]
    ln_stats = measure_loudness(ffmpeg, src, lufs) if (lufs is not None and info["has_audio"]) else None
    cmd = build_command(ffmpeg, src, dest, preset, info, subs, tracks, title, loudnorm_stats=ln_stats)
    r = subprocess.run(cmd, capture_output=True, text=True, stdin=subprocess.DEVNULL)
    if r.returncode != 0:
        dest.unlink(missing_ok=True)
        raise ExportError("ffmpeg failed: " + r.stderr.strip()[-400:])
    return {"file": str(dest), "preset": preset, "subtitles": made, "audio_tracks": [lang for _, lang in tracks], "seconds": probe(ffmpeg, dest)["seconds"]}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--project", required=True)
    ap.add_argument("--film", required=True, help="a .mp4 in the book's films folder")
    ap.add_argument("--preset", required=True, choices=sorted(PRESETS))
    ap.add_argument("--languages", default="", help="comma-separated codes for extra subtitle tracks, translated by the AI engine")
    ap.add_argument("--audio-track", action="append", default=[], metavar="LANG=FILE", help="a dubbed audio track you made (file inside the book's folder)")
    ap.add_argument("--engine", default="claude", choices=["claude", "fcc-claude", "codex", "fcc-codex", "hf", "local"])
    ap.add_argument("--model", default=None)
    ap.add_argument("--out", default="")
    ap.add_argument("--title", default="")
    a = ap.parse_args(argv)
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import bookkit
    import crew
    langs = [x.strip() for x in a.languages.split(",") if x.strip()]
    tracks = []
    for t in a.audio_track:
        lang, _, rel = t.partition("=")
        tracks.append((lang.strip(), rel.strip()))

    def llm(prompt, check):
        return bookkit.llm_json(prompt, crew.system("subtitle_translator", bookkit.project_dir(a.project), "subtitles"), model=a.model, engine=a.engine, validate=check)
    try:
        res = export(bookkit.project_dir(a.project), a.film, a.preset, langs, llm if langs else None, tracks, a.out, a.title)
    except (ExportError, RuntimeError) as e:
        sys.exit(str(e))
    print(f"exported {res['file']} ({res['seconds']:.1f} s) as {PRESETS[a.preset][0]}; subtitles: {', '.join(res['subtitles']) or 'none'}; extra audio: {', '.join(res['audio_tracks']) or 'none'}")


if __name__ == "__main__":
    main()
