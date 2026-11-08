#!/usr/bin/env python3
"""Check that each shot shows the same person as the character's reference picture: a free check on this computer's CPU, no GPU.

  uv run --with opencv-python-headless --with numpy python face_check.py BOOK --series SERIES [--look LOOK] [--source images/<model>_keyframes | videos/<model>] [--start 1 --end 100]

For each shot row it compares the faces found in the keyframe (or, for clips, the first and last frame) with the reference picture of each character
named in that row, using OpenCV's YuNet face finder and SFace recogniser. The two models (about 39 MB) are downloaded once to ~/.cache/studio_faces.
Life stages are respected: a stage with its own picture is compared with that picture.
Writes face_check.json in the book's folder: {"threshold", "source", "rows": {"12": {"status", "faces", "scores": {"Adam": 0.41}}}}.
  status  ok         every character with a reference picture matched a face
          different  a face was found, but one character matched none of them: retake this shot
          no_face    no face found (a back view, a wide shot, or a look the face finder cannot read)
          skipped    no one in the shot has a usable reference picture
This is a screening aid: the recogniser was trained on photographs. Use it for realistic films; for claymation or cartoons most shots will be no_face or
low. A low score on a side view, in shadow or at a small size can be a false alarm, so look at the flagged shots before remaking them.
"""
import argparse, csv, json, re, sys, urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import bookkit  # noqa: E402
import character_tokens as ct  # noqa: E402
import layout  # noqa: E402

MODELS = {"detector": "https://huggingface.co/opencv/face_detection_yunet/resolve/main/face_detection_yunet_2023mar.onnx",
          "recogniser": "https://huggingface.co/opencv/face_recognition_sface/resolve/main/face_recognition_sface_2021dec.onnx"}
THRESHOLD = 0.363       # SFace's published cosine threshold for "same person"
MIN_FACE = 40           # pixels: smaller faces cannot be compared reliably


def model_file(url):
    """The model file, downloaded once. The download goes to a temporary name, so a broken one is never used."""
    folder = Path.home() / ".cache" / "studio_faces"
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / url.rsplit("/", 1)[1]
    if not path.is_file():
        print(f"downloading {path.name} ...", flush=True)
        tmp = path.with_suffix(".part")
        urllib.request.urlretrieve(url, tmp)
        tmp.replace(path)
    return path


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("book")
    ap.add_argument("--series", required=True)
    ap.add_argument("--look", default="")
    ap.add_argument("--source", default="", help="folder inside the book: images/<model>_keyframes or videos/<model>; default: the newest keyframes")
    ap.add_argument("--start", type=int, default=1)
    ap.add_argument("--end", type=int, default=10**9)
    a = ap.parse_args(argv)
    if not layout.SLUG_RE.match(a.series):
        sys.exit(f"bad series name {a.series!r}")
    try:
        d = layout.find_dir(a.book)
    except ValueError as e:
        sys.exit(str(e))
    if d is None:
        sys.exit(f"no such book: {a.book}")
    if a.source and not re.fullmatch(r"(images|videos)/[a-z0-9_]{2,80}", a.source):
        sys.exit("--source must look like images/<model>_keyframes or videos/<model>")
    with open(d / "all_shots.csv", newline="", encoding="utf-8") as fh:
        shots = list(csv.DictReader(fh))
    if a.source:
        src = d / a.source
    else:
        kf = sorted((p for p in (d / "images").glob("*_keyframes") if p.is_dir()), key=lambda p: p.stat().st_mtime) if (d / "images").is_dir() else []
        src = kf[-1] if kf else None
    if src is None or not src.is_dir():
        sys.exit("nothing to check: make keyframes first, or name a folder with --source")
    is_video = src.parent.name == "videos"

    import cv2
    import numpy as np
    detector = cv2.FaceDetectorYN.create(str(model_file(MODELS["detector"])), "", (320, 320), 0.7)
    recogniser = cv2.FaceRecognizerSF.create(str(model_file(MODELS["recogniser"])), "")

    def read_picture(path):
        return cv2.imdecode(np.fromfile(str(path), dtype=np.uint8), cv2.IMREAD_COLOR)

    def faces_in(img):
        """An embedding for every face in the picture that is big enough to compare, largest first."""
        if img is None:
            return []
        h, w = img.shape[:2]
        scale = min(1.0, 1280 / max(h, w))
        if scale < 1:
            img = cv2.resize(img, (int(w * scale), int(h * scale)))
            h, w = img.shape[:2]
        detector.setInputSize((w, h))
        found = detector.detect(img)[1]
        if found is None:
            return []
        found = sorted(found, key=lambda f: -f[2] * f[3])
        return [recogniser.feature(recogniser.alignCrop(img, f)) for f in found if min(f[2], f[3]) >= MIN_FACE]

    def frames_of(n):
        if not is_video:
            path = src / f"image-{n:04d}.png"
            return [read_picture(path)] if path.is_file() else None
        path = src / f"shot-{n:04d}.mp4"
        if not path.is_file():
            return None
        cap = cv2.VideoCapture(str(path))
        total, out = int(cap.get(cv2.CAP_PROP_FRAME_COUNT)), []
        for at in (0, max(total - 1, 0)):
            cap.set(cv2.CAP_PROP_POS_FRAMES, at)
            ok, frame = cap.read()
            if ok:
                out.append(frame)
        cap.release()
        return out

    book = {str(c.get("name", "")).lower(): c for c in (bookkit.read_json(bookkit.continuity_file(d), {}) or {}).get("characters", []) if isinstance(c, dict)}
    refs, rows = {}, {}

    def reference(name, stage):
        """The face of a character at a life stage, or None. Looked up once for each."""
        key = (name, stage)
        if key not in refs:
            pic = ct.first_reference(a.series, name, stage)
            found = faces_in(read_picture(pic)) if pic else []
            refs[key] = found[0] if found else None
            if pic and not found:
                print(f"   no usable face in the reference picture of {name}: {pic.name}", flush=True)
        return refs[key]

    last = min(a.end, len(shots))
    for n in range(max(1, a.start), last + 1):
        row = shots[n - 1]
        names = [x.strip() for x in (row.get("characters") or "").split("|") if x.strip()]
        chapter = re.search(r"(\d+)$", str(row.get("chapter") or ""))
        chapter = int(chapter.group(1)) if chapter else None
        wanted = {}
        for name in names:
            stage = bookkit.stage_for(book.get(name.lower(), {}), chapter, a.look)
            face = reference(name, stage["label"] if stage else "")
            if face is not None:
                wanted[name] = face
        frames = frames_of(n)
        if frames is None:
            continue
        if not wanted:
            rows[str(n)] = {"status": "skipped", "faces": 0, "scores": {}}
            continue
        faces = [f for fr in frames for f in faces_in(fr)]
        scores = {name: round(max((float(recogniser.match(ref, f, cv2.FaceRecognizerSF_FR_COSINE)) for f in faces), default=-1.0), 3) for name, ref in wanted.items()}
        status = "no_face" if not faces else ("ok" if all(v >= THRESHOLD for v in scores.values()) else "different")
        rows[str(n)] = {"status": status, "faces": len(faces), "scores": scores}
        print(f"row {n}: {status} {scores}", flush=True)
    bookkit.write_json(d / "face_check.json", {"threshold": THRESHOLD, "source": str(src.relative_to(d)), "rows": rows})
    tally = {s: sum(1 for r in rows.values() if r["status"] == s) for s in ("ok", "different", "no_face", "skipped")}
    print(f"checked {len(rows)} shot(s) in {src.name}: {tally}")
    flagged = [n for n, r in rows.items() if r["status"] == "different"]
    if flagged:
        print("look at these shots, the face may be someone else: " + ", ".join(flagged))


if __name__ == "__main__":
    main()
