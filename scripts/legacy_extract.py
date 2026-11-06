"""Build the four CSVs for an imported production-bible project (adam_eve or enoch).

  python3 legacy_extract.py adam_eve
  python3 legacy_extract.py enoch [--enoch-chars 300]   # 0 = narrate the whole chapter

Writes into projects/<name>/:  all_shots.csv, all_chapters.csv, audio_shots.csv, audio_chapters.csv
(chapter,shot,prompt  and  chapter,shot,lines_json,narration,sfx,music). Row N of the audio files is the audio for
row N of the matching video file. Adam & Eve text comes from each chapter's 'Narration & dialogue' and
'Sound & music' sections; Enoch narrates the Charles verse text in enoch_verses.json (extract_enoch_text.py).
New books go through book_*.py instead (README_NEW_BOOK.md).
"""
import argparse, csv, json, re
from pathlib import Path
from bookkit import apply_prompt_edits
from prompts import BOOKS, ENOCH, adam_eve_chapters, adam_shots, chapter_files, enoch_prompt

QUOTE = re.compile(r'[“"]([^”"]+)[”"]')
SHOTS = re.compile(r'Shots?\s*(\d+)(?:\s*[–—-]\s*(\d+))?', re.I)
SPEAKER = re.compile(r"\b([A-Z][A-Z' ]{2,}[A-Z])\b")
IGNORE = {"V", "VO", "THE", "ADAPTATION", "NARRATOR V", "NARRATOR VO"}
GENERIC_SFX = "quiet ancient ambience, soft wind, distant natural sounds"
MUSIC_PREFIX = "slow reverent cinematic biblical epic score, strings and choir, "


def section(text, name):
    if f"## {name}" not in text:
        return ""
    return text.split(f"## {name}", 1)[1].split("\n## ", 1)[0]


def clean(s):
    s = re.sub(r"\[[^\]]*\]", "", s)                # [adaptation ...]
    s = re.sub(r"\*?\((?:v\.|vv\.)[^)]*\)\*?", "", s)  # (v. 3)
    s = s.replace("*", "")
    return re.sub(r"\s+", " ", s).strip()


def speaker_of(prefix):
    names = [n.strip() for n in SPEAKER.findall(prefix) if n.strip() not in IGNORE]
    names = [n for n in names if not n.startswith("NARRATOR V")]
    if not names:
        return "NARRATOR"
    n = names[0]
    if "WORD" in n:
        return "WORD"
    return "NARRATOR" if "NARRATOR" in n else n


def shot_numbers(header):
    m = SHOTS.search(header)
    if not m:
        return []
    a = int(m.group(1)); b = int(m.group(2) or a)
    return list(range(a, b + 1))


def parse_narration(body):
    """-> {shot: [(speaker, text), ...]}"""
    out, current = {}, []
    for line in body.splitlines():
        stripped = line.strip().lstrip("- ").strip()
        if not stripped:
            continue
        m = re.match(r"\*\*([^*]+)\*\*(.*)", stripped)
        if m:
            header, rest = m.group(1), m.group(2)
            nums = shot_numbers(header)
            if nums:
                current = nums
            elif not line.lstrip().startswith("- "):
                continue
            else:
                current = []
        else:
            header, rest = "", stripped            # continuation line, e.g. "THE WORD OF GOD (V.O.): ..."
        quotes = QUOTE.findall(rest)
        if not quotes or not current:
            continue
        first_quote = QUOTE.search(rest).start()
        spk = speaker_of(header + " " + rest[:first_quote])
        text = clean(" ".join(quotes))
        if text:
            for s in current:
                out.setdefault(s, []).append((spk, text))
    return out


def parse_sound(body):
    """-> ({shot: text}, chapter_level_text)"""
    per, chapter = {}, []
    for line in body.splitlines():
        if not line.startswith("- "):
            continue
        m = re.match(r"- \*\*([^*]+)\*\*\s*(.*)", line)
        if not m:
            continue
        header, rest = m.group(1), clean(m.group(2))
        nums = shot_numbers(header)
        if nums and rest:
            for s in nums:
                per[s] = (per.get(s, "") + " " + rest).strip()
        elif rest:
            chapter.append(rest)
    return per, " ".join(chapter)


def music_prompt(*parts):
    text = " ".join(p for p in parts if p)
    return (MUSIC_PREFIX + text)[:330]


def sfx_prompt(shot_text, chapter_text):
    return (shot_text or chapter_text or GENERIC_SFX)[:300]


def excerpt(verses, limit):
    """Whole verses up to `limit` characters; if the first verse alone is longer, cut it at a sentence/word end."""
    if limit <= 0:
        return " ".join(verses)
    out, used = "", 0
    for v in verses:
        if out and len(out) + 1 + len(v) > limit:
            break
        out, used = (out + " " + v).strip(), used + 1
    if out.endswith((":", ",")) and used < len(verses):      # don't stop on "said to him:" - add the next sentence
        nxt = verses[used]
        m = re.search(r"[.!?](?:['\"”])?(?:\s|$)", nxt)
        out = (out + " " + (nxt[: m.end()] if m else nxt)).strip()
    if len(out) > limit * 1.3:
        cut = out[:limit]
        end = max(cut.rfind(". "), cut.rfind("; "), cut.rfind(": "))
        out = cut[: end + 1] if end > limit * 0.4 else cut[: cut.rfind(" ")] + "…"
    return out




FIELDS = ["chapter", "shot", "lines_json", "narration", "sfx", "music"]


def adam_rows():
    prompts, audio, first_narrated = [], [], {}
    for label, path in adam_eve_chapters():
        text = path.read_text()
        shots = adam_shots(path)
        narr = parse_narration(section(text, "Narration & dialogue"))
        snd, chap_snd = parse_sound(section(text, "Sound & music"))
        start = len(audio)
        for s, prompt in enumerate(shots, start=1):
            lines = narr.get(s, [])
            prompts.append({"chapter": label, "shot": s, "prompt": prompt})
            audio.append({"chapter": label, "shot": s, "lines_json": json.dumps(lines, ensure_ascii=False),
                          "narration": " ".join(t for _, t in lines),
                          "sfx": sfx_prompt(snd.get(s), chap_snd), "music": music_prompt(chap_snd, snd.get(s))})
        mine = audio[start:]
        first_narrated[label] = None if (not mine or mine[0]["narration"]) else next((r for r in mine if r["narration"]), None)
    return prompts, audio, first_narrated


def enoch_rows(project, enoch_chars):
    verses_file = project / "enoch_verses.json"
    verses = json.load(open(verses_file)) if verses_file.exists() else {}
    if not verses:
        print("note: enoch_verses.json missing; falling back to one-line summaries "
              "(make it: uv run --with pypdf python extract_enoch_text.py)")
    prompts, audio = [], []
    for n, path in chapter_files(ENOCH, 1, 108):
        text = path.read_text()
        prompt = enoch_prompt(path)
        if not prompt:
            continue
        summary = clean(text.splitlines()[2]) if len(text.splitlines()) > 2 else ""
        audio_note = clean(section(text, "Audio and editing notes"))
        sound = audio_note.split("Use a calm")[0].replace("Sound bed:", "").strip(" .") or GENERIC_SFX
        v = verses.get(str(n), {}).get("verses")
        body = excerpt(v, enoch_chars) if v else summary
        line = ("NARRATOR", f"First Enoch, chapter {n}. {body}")
        label = f"enoch-{n:03d}"
        prompts.append({"chapter": label, "shot": 1, "prompt": prompt})
        audio.append({"chapter": label, "shot": 1, "lines_json": json.dumps([line], ensure_ascii=False),
                      "narration": line[1], "sfx": sound[:300],
                      "music": music_prompt("restrained choral textures and deep atmospheric tones")})
    return prompts, audio


def write(path, fields, rows):
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("project", choices=["adam_eve", "enoch"])
    ap.add_argument("--enoch-chars", type=int, default=300,
                    help="max characters of verse text narrated per Enoch clip, cut at a verse/sentence end (0 = whole chapter)")
    ap.add_argument("--shot", type=int, default=1, help="which shot stands in for a chapter in all_chapters.csv (default 1)")
    args = ap.parse_args()
    proj = BOOKS / args.project
    if args.project == "adam_eve":
        prompts, audio, first_narrated = adam_rows()
    else:
        prompts, audio = enoch_rows(proj, args.enoch_chars)
        first_narrated = {}

    write(proj / "all_shots.csv", ["chapter", "shot", "prompt"], prompts)
    write(proj / "audio_shots.csv", FIELDS, audio)

    chap_prompts, chap_audio, seen = [], [], set()
    for r in prompts:
        if r["chapter"] in seen:
            continue
        seen.add(r["chapter"])
        same = [p for p in prompts if p["chapter"] == r["chapter"]]
        pick = same[min(args.shot, len(same)) - 1]
        chap_prompts.append({"chapter": r["chapter"], "shot": pick["shot"], "prompt": pick["prompt"]})
    seen = set()
    for r in audio:
        if r["chapter"] in seen:
            continue
        seen.add(r["chapter"])
        alt = first_narrated.get(r["chapter"])
        chap_audio.append({**r, **({k: alt[k] for k in ("lines_json", "narration")} if alt else {})})
    write(proj / "all_chapters.csv", ["chapter", "shot", "prompt"], chap_prompts)
    write(proj / "audio_chapters.csv", FIELDS, chap_audio)
    kept = apply_prompt_edits(proj)                      # your saved scene edits survive a rebuild
    if kept:
        print(f"re-applied {kept} saved prompt edit(s)")
    print(f"{args.project}: {len(prompts)} shots, {len(chap_prompts)} chapters; "
          f"{sum(1 for r in audio if r['narration'])} rows with narration")
