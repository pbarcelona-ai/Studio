"""studio_app.media"""
import re
import struct
from bookkit import SLUG_RE
from layout import project_dir as pdir     # a name -> its folder (books/, characters/ or prompts/); see layout.py

from .common import PlanError, num
from .config import SYNC_MODES
from .generation import sound_flags
from .projects import read_csv_rows


# ---------------------------------------------------------------- make a film from the downloaded files you tick
AUDIO_KINDS_FILES = {"narration": "narration-*.wav", "sfx": "sfx-*.wav", "music": "music-*.wav"}
FILM_NAME_RE = re.compile(r"^[A-Za-z0-9_-]{1,60}$")


def media_inventory(slug):
    """What has been downloaded for a project: clip folders and audio folders with the rows each holds, plus a line of text per row."""
    d = pdir(slug)
    if not SLUG_RE.match(slug) or not d.is_dir():
        raise PlanError("pick a book or prompt set first")
    inv = {"videos": {}, "narration": {}, "sfx": {}, "music": {}, "texts": {}}

    def rows_of(folder, pattern):
        out = []
        for f in folder.glob(pattern):
            m = re.search(r"-(\d+)\.", f.name)
            if m:
                out.append(int(m.group(1)))
        return sorted(out)

    for sub in sorted((d / "videos").glob("*")) if (d / "videos").is_dir() else []:
        rows = rows_of(sub, "shot-*.mp4") if sub.is_dir() else []
        if rows:
            inv["videos"][f"videos/{sub.name}"] = rows
    for sub in sorted((d / "audio").glob("*")) if (d / "audio").is_dir() else []:
        if sub.is_dir():
            for kind, pattern in AUDIO_KINDS_FILES.items():
                rows = rows_of(sub, pattern)
                if rows:
                    inv[kind][f"audio/{sub.name}"] = rows
    inv["seconds"] = {}                                # length of every clip and sound, for the timeline: {folder: {row: seconds}}
    for kind in ("videos", "narration", "sfx", "music"):
        for src, rows in inv[kind].items():
            pattern = "shot-{:04d}.mp4" if kind == "videos" else AUDIO_KINDS_FILES[kind].replace("*", "{:04d}")
            inv["seconds"].setdefault(src, {}).update({str(n): media_seconds(d / src / pattern.format(n)) for n in rows})
    for src, rows in inv["videos"].items():
        csv_name = "all_chapters.csv" if src.endswith("_chapters") else "all_shots.csv"
        table = read_csv_rows(d / csv_name)
        inv["texts"][src] = {str(n): (f"{table[n - 1]['chapter']}: {table[n - 1]['prompt']}"[:110] if 0 < n <= len(table) else "") for n in rows}
    return inv


_SECONDS = {}      # (path, size, mtime) -> seconds


def _mp4_seconds(fh, size):
    """Duration from the mp4's movie header (moov/mvhd), walking the top-level boxes; None if it has none."""
    pos = 0
    while pos + 8 <= size:
        fh.seek(pos)
        head = fh.read(16)
        box, kind = struct.unpack(">I", head[:4])[0], head[4:8]
        hdr = 8
        if box == 1:                                   # 64-bit size
            box, hdr = struct.unpack(">Q", head[8:16])[0], 16
        elif box == 0:
            box = size - pos
        if box < hdr:
            return None
        if kind == b"moov":
            end, p = pos + box, pos + hdr
            while p + 8 <= end:
                fh.seek(p)
                sub, skind = struct.unpack(">I4s", fh.read(8))
                if sub < 8:
                    return None
                if skind == b"mvhd":
                    version = fh.read(1)[0]
                    fh.read(3)
                    if version == 1:
                        fh.read(16); scale, dur = struct.unpack(">IQ", fh.read(12))
                    else:
                        fh.read(8); scale, dur = struct.unpack(">II", fh.read(8))
                    return dur / scale if scale else None
                p += sub
            return None
        pos += box
    return None


def _wav_seconds(fh):
    """Duration of a RIFF/WAVE file from its fmt (bytes per second) and data chunk sizes; None if it is not one."""
    if fh.read(4) != b"RIFF":
        return None
    fh.read(4)
    if fh.read(4) != b"WAVE":
        return None
    rate = None
    while True:
        head = fh.read(8)
        if len(head) < 8:
            return None
        cid, n = struct.unpack("<4sI", head)
        if cid == b"fmt ":
            if n < 12:
                return None                            # too short to hold the byte rate (and seeking back would never end)
            rate = struct.unpack("<HHII", fh.read(12))[3]
            fh.seek(n - 12 + (n & 1), 1)
        elif cid == b"data":
            return n / rate if rate else None
        else:
            fh.seek(n + (n & 1), 1)


def media_seconds(path):
    """Length in seconds (rounded to 0.01) of an .mp4 or .wav file, or None if it cannot be read. Cached until the file changes."""
    try:
        st = path.stat()
    except OSError:
        return None
    key = (str(path), st.st_size, st.st_mtime_ns)
    if key not in _SECONDS:
        try:
            with open(path, "rb") as fh:
                secs = _mp4_seconds(fh, st.st_size) if path.suffix.lower() == ".mp4" else _wav_seconds(fh)
        except (OSError, ValueError, IndexError, struct.error):          # a truncated or odd file: no length, the timeline guesses
            secs = None
        _SECONDS[key] = round(secs, 2) if secs else None
    return _SECONDS[key]


def film_step(opt):
    slug = str(opt.get("project", ""))
    inv = media_inventory(slug)
    name = str(opt.get("name") or "my_film").strip()
    if not FILM_NAME_RE.match(name):
        raise PlanError("film name: letters, digits, - and _ only (up to 60)")
    vsrc = opt.get("video_source")
    if vsrc not in inv["videos"]:
        raise PlanError("choose where the video clips come from")
    srcs = {}
    for kind in AUDIO_KINDS_FILES:
        v = (opt.get("sources") or {}).get(kind) or ""
        if v and v not in inv[kind]:
            raise PlanError(f"unknown {kind} folder {v!r}")
        srcs[kind] = v
    have = {"video": set(inv["videos"][vsrc]), **{k: set(inv[k][srcs[k]]) if srcs[k] else set() for k in AUDIO_KINDS_FILES}}
    clips, seen = [], set()
    for item in opt.get("rows") or []:                     # in the page's order: the table can reorder clips
        n = int(item.get("n"))
        if n not in have["video"]:
            raise PlanError(f"row {n} has no clip in {vsrc}")
        if n in seen:
            raise PlanError(f"row {n} is listed twice")
        seen.add(n)
        c = {"row": n, "video": f"{vsrc}/shot-{n:04d}.mp4",
             "trim_start": num(item, "trim_start", 0.0, float, 0, 30), "trim_end": num(item, "trim_end", 0.0, float, 0, 30)}
        for kind in AUDIO_KINDS_FILES:
            use = bool(item.get(kind)) and n in have[kind]
            c[kind] = f"{srcs[kind]}/{kind}-{n:04d}.wav" if use else None
        clips.append(c)
    if not clips:
        raise PlanError("tick at least one clip")
    sync = opt.get("sync", "stretch")
    if sync not in SYNC_MODES:
        raise PlanError("bad sync mode")
    vols = {k: num(opt.get("vol", {}), k, d, float, 0, 5) for k, d in (("narration", 1.0), ("sfx", 0.5), ("music", 0.25))}
    transition = opt.get("transition", "cut")
    if transition not in ("cut", "fade", "dissolve"):
        raise PlanError("bad transition")
    fade = num(opt, "fade", 0.5, float, 0.1, 1.5)
    titles = {k: re.sub(r"[\x00-\x1f\x7f]", " ", str(opt.get(k) or "")).strip()[:120] for k in ("title", "end_title")}   # one line of plain text each
    (pdir(slug) / "films").mkdir(exist_ok=True)
    extra = ["--transition", transition, "--fade", str(fade)] + (["--burn-captions"] if opt.get("burn_captions") else []) + (["--match-colour"] if opt.get("match_colour") else []) + sound_flags(opt, bool(opt.get("music_bed")) and not vsrc.endswith("_chapters"))   # rows of a per-chapter film are chapters, and each already has its own music
    return slug, {"clips": clips, **titles}, {"label": f"Make film {name}.mp4 from {len(clips)} clip(s)", "env": {},
        "argv": ["uv", "run", "--with", "imageio-ffmpeg", "python", "mix_film.py", "--project", slug, "--selection", "films/_selection.json",
                 "--sync", sync, "--out", f"{name}.mp4", "--vol-narration", str(vols["narration"]), "--vol-sfx", str(vols["sfx"]),
                 "--vol-music", str(vols["music"])] + extra}
