#!/usr/bin/env bash
# Usage: [PROJECT=adam_eve] KAGGLE_USER=yourname ./run_kaggle_model.sh MODEL START END   (default project: adam_eve)
#        MODEL = ltx_video | wan | cogvideox (video)  |  audio_kokoro | audio_musicgen | audio_mmaudio (audio)  |  image_sdxl_turbo | image_sdxl | image_sd35_medium (images)
# e.g.   KAGGLE_USER=yourname ./run_kaggle_model.sh ltx_video 1 3
#        SHOTS_CSV=audio_shots.csv KAGGLE_USER=yourname ./run_kaggle_model.sh audio_kokoro 1 50   # audio uses audio_*.csv
#        SHOTS_CSV=all_chapters.csv KAGGLE_USER=yourname ./run_kaggle_model.sh wan 1 5   # one prompt per chapter
#        SHOTS_CSV=keyframes.csv KAGGLE_USER=yourname ./run_kaggle_model.sh image_sdxl 1 20   # keyframes -> images/sdxl_keyframes
#        KEYFRAME_MODEL=sdxl KAGGLE_USER=yourname ./run_kaggle_model.sh ltx_video_i2v 1 20   # animate those keyframes
#        UPSCALE_SOURCE=ltx_video_i2v KAGGLE_USER=yourname ./run_kaggle_model.sh upscale_x2 1 20   # videos/ltx_video_i2v -> videos/ltx_video_i2v_x2
# Uploads the prompt CSVs as a private dataset, runs the Kaggle notebook on a GPU, waits, and
# downloads the clips into ./videos/MODEL (or ./videos/MODEL_chapters in chapter mode).
set -euo pipefail
command -v kaggle >/dev/null || export PATH="$HOME/.local/bin:$PATH"       # only add uv's tool folder if kaggle is not already found (lets tests substitute a stand-in)
cd "$(dirname "$0")/.."          # the repository root: the notebooks (Studio_*.ipynb) and projects/ are relative to it
PROJECT=${PROJECT:-adam_eve}; PD="$(python3 scripts/layout.py "$PROJECT")"      # projects/books/<book>, projects/characters/<set> or projects/prompts/<set> (see layout.py)
[ -d "$PD" ] || { echo "no such project: $PD"; exit 1; }

MODEL=${1:?model: ltx_video | wan | cogvideox | audio_kokoro | audio_musicgen | audio_mmaudio | image_sdxl_turbo | image_sdxl | image_sd35_medium}; START=${2:?start row}; END=${3:?end row}
USER_SLUG=${KAGGLE_USER:?set KAGGLE_USER to your Kaggle username (the part after kaggle.com/)}
case "$MODEL" in audio_*) SHOTS_CSV=${SHOTS_CSV:-audio_shots.csv} ;; image_*) SHOTS_CSV=${SHOTS_CSV:-all_images.csv} ;; *) SHOTS_CSV=${SHOTS_CSV:-all_shots.csv} ;; esac
ACCEL=${KAGGLE_ACCELERATOR:-NvidiaTeslaT4}      # "GPU T4 x2" per the Kaggle CLI docs
GPU_FLAG=true; TPU_FLAG=false; case "$ACCEL" in Tpu*) GPU_FLAG=false; TPU_FLAG=true ;; esac   # Kaggle has separate GPU and TPU switches; a TPU run needs enable_tpu
case "$MODEL:$ACCEL" in
  tpu_*:Tpu*|image_tpu_*:Tpu*) ;;
  tpu_*:*|image_tpu_*:*) echo "$MODEL needs a TPU: set KAGGLE_ACCELERATOR=TpuV5E8"; exit 1 ;;
  *:Tpu*) echo "only tpu_* models run on a TPU (got $MODEL on $ACCEL)"; exit 1 ;;
esac
NB="Studio_Kaggle_${MODEL}.ipynb"
GEN=""
if [ ! -f "$NB" ]; then        # generated files can be deleted by the clean-up: re-create them in a throw-away folder, so the project folder stays clean
  GEN=$(mktemp -d); trap 'rm -rf "$GEN"' EXIT
  STUDIO_GEN_DIR="$GEN" python3 scripts/make_all.py >/dev/null 2>&1 || true
  NB="$GEN/$NB"
fi
[ -f "$NB" ] || { echo "no such model: $MODEL (missing $NB)"; exit 1; }
command -v kaggle >/dev/null || { echo "kaggle CLI not found: uv tool install kaggle"; exit 1; }

case "$MODEL" in audio_*) BASEDIR="$PD/audio/${MODEL#audio_}" ;; image_*) BASEDIR="$PD/images/${MODEL#image_}" ;; *) BASEDIR="$PD/videos/$MODEL" ;; esac
OUTDIR="$BASEDIR"; MODE=""
case "$SHOTS_CSV" in *chapters*) OUTDIR="${BASEDIR}_chapters"; MODE="-chapters" ;; keyframes*) OUTDIR="${BASEDIR}_keyframes"; MODE="-keyframes" ;; esac
# Image-to-video models (*_i2v) start each clip from its keyframe: images/<KEYFRAME_MODEL>_keyframes/image-NNNN.png, uploaded as kf-NNNN.png.
KFDIR=""
case "$MODEL" in *_i2v)
  case "$SHOTS_CSV" in all_shots.csv) ;; *) echo "$MODEL works per shot (all_shots.csv), not with $SHOTS_CSV"; exit 1 ;; esac
  if [ -n "${KEYFRAME_MODEL:-}" ]; then KFDIR="$PD/images/${KEYFRAME_MODEL}_keyframes"
  else KFDIR=$(ls -dt "$PD"/images/*_keyframes 2>/dev/null | head -1 || true); fi      # newest keyframe set if none was named
  [ -n "$KFDIR" ] && [ -d "$KFDIR" ] || { echo "!! $MODEL needs keyframes: make them first (no images/<model>_keyframes folder in $PD)"; exit 1; }
  MISSING=""
  for N in $(seq "$START" "$END"); do [ -f "$KFDIR/$(printf 'image-%04d.png' "$N")" ] || MISSING="$MISSING $N"; done
  [ -z "$MISSING" ] || { echo "!! no keyframe in $KFDIR for row(s):$MISSING - make keyframes for these rows first"; exit 1; }
  echo "== keyframes from $KFDIR" ;;
esac
# Upscalers (upscale_*) enlarge clips already made: videos/<UPSCALE_SOURCE>/shot-NNNN.mp4, uploaded as in-NNNN.mp4, come back in videos/<UPSCALE_SOURCE>_x2.
UPDIR=""
case "$MODEL" in upscale_*)
  case "$SHOTS_CSV" in all_shots.csv) ;; *) echo "$MODEL works per shot (all_shots.csv), not with $SHOTS_CSV"; exit 1 ;; esac
  SRC=${UPSCALE_SOURCE:?set UPSCALE_SOURCE to the video folder to upscale (for example ltx_video_i2v)}
  [[ "$SRC" =~ ^[a-z0-9_]{2,60}$ ]] || { echo "bad UPSCALE_SOURCE: $SRC"; exit 1; }
  UPDIR="$PD/videos/$SRC"
  [ -d "$UPDIR" ] || { echo "!! no clips folder $UPDIR"; exit 1; }
  MISSING=""
  for N in $(seq "$START" "$END"); do [ -f "$UPDIR/$(printf 'shot-%04d.mp4' "$N")" ] || MISSING="$MISSING $N"; done
  [ -z "$MISSING" ] || { echo "!! no clip in $UPDIR for row(s):$MISSING"; exit 1; }
  OUTDIR="$PD/videos/${SRC}_${MODEL#upscale_}"
  echo "== upscaling clips from $UPDIR into $OUTDIR" ;;
esac
KPREFIX=${KAGGLE_PREFIX:-}                                   # no prefix unless you set KAGGLE_PREFIX (for example KAGGLE_PREFIX=mine-)
DS="${KPREFIX}${PROJECT//_/-}-prompts"                      # one Kaggle dataset per project (Kaggle wants 3+ characters in the name and 6+ in the title, so a short set name like xv gets "-prompts")
SLUG="${KPREFIX}${PROJECT//_/-}-${MODEL//_/-}${MODE}-${START}-${END}"        # slug must equal the lower-cased, dashed title
WORK="$(mktemp -d)"; trap 'rm -rf "$WORK" "$GEN"' EXIT

# 1. Dataset with the prompt CSVs (create once, new version afterwards)
mkdir -p "$WORK/ds"; for f in all_shots.csv all_chapters.csv audio_shots.csv audio_chapters.csv all_images.csv keyframes.csv; do [ -f "$PD/$f" ] && cp "$PD/$f" "$WORK/ds/"; done
if { [ "$SHOTS_CSV" = keyframes.csv ] || [ "$SHOTS_CSV" = all_images.csv ]; } && [ -d "$PD/keyframe_refs" ]; then   # character pictures that steer the pictures (make_keyframes_csv.py --refs; the Characters tab)
  cp "$PD"/keyframe_refs/ref-*.png "$WORK/ds/" 2>/dev/null || true
fi
if [ -n "$UPDIR" ]; then         # this run's clips to upscale, flat beside the CSV
  for N in $(seq "$START" "$END"); do cp "$UPDIR/$(printf 'shot-%04d.mp4' "$N")" "$WORK/ds/$(printf 'in-%04d.mp4' "$N")"; done
fi
if [ -n "$KFDIR" ]; then         # this run's keyframes, flat beside the CSV (a dataset upload skips sub-folders)
  for N in $(seq "$START" "$END"); do cp "$KFDIR/$(printf 'image-%04d.png' "$N")" "$WORK/ds/$(printf 'kf-%04d.png' "$N")"; done
fi
cat > "$WORK/ds/dataset-metadata.json" <<JSON
{"title": "${DS//-/ }", "id": "$USER_SLUG/$DS", "licenses": [{"name": "CC0-1.0"}]}
JSON
if kaggle datasets files "$USER_SLUG/$DS" >/dev/null 2>&1; then
  echo "== updating dataset $USER_SLUG/$DS"
  kaggle datasets version -p "$WORK/ds" -m "update prompts" -t -q || echo "(dataset unchanged or update failed; continuing with the existing version)"
else
  echo "== creating private dataset $USER_SLUG/$DS"
  kaggle datasets create -p "$WORK/ds" -t -q
fi
echo "== waiting for dataset to be ready"
for _ in $(seq 1 30); do
  kaggle datasets status "$USER_SLUG/$DS" 2>&1 | grep -qi ready && break
  sleep 10
done
# "ready" can describe the PREVIOUS version while the new one is still being created, and a notebook that starts then sees the old CSV and does nothing
# (a run for row 11 found only 10 rows and reported success with no output). So wait until Kaggle's copy of the CSV has at least the rows this run needs.
NEED_ROWS=$(python3 -c "import csv,sys; print(len(list(csv.DictReader(open(sys.argv[1], newline='', encoding='utf-8')))))" "$PD/$SHOTS_CSV" 2>/dev/null || echo 0)
if [ "${NEED_ROWS:-0}" -ge "$END" ]; then
  echo "== checking that Kaggle's copy of $SHOTS_CSV has row $END"
  OK=0
  for _ in $(seq 1 30); do
    rm -rf "$WORK/chk"; mkdir -p "$WORK/chk"
    if kaggle datasets download "$USER_SLUG/$DS" -f "$SHOTS_CSV" -p "$WORK/chk" --unzip -q >/dev/null 2>&1 && [ -f "$WORK/chk/$SHOTS_CSV" ]; then
      HAVE=$(python3 -c "import csv,sys; print(len(list(csv.DictReader(open(sys.argv[1], newline='', encoding='utf-8')))))" "$WORK/chk/$SHOTS_CSV" 2>/dev/null || echo 0)
      [ "${HAVE:-0}" -ge "$END" ] && { OK=1; break; }
      echo "   Kaggle has ${HAVE:-0} rows, need $END; waiting 10 s"
    fi
    sleep 10
  done
  [ "$OK" = 1 ] || echo "!! Kaggle's copy never showed row $END; continuing anyway (the notebook may find too few rows)"
fi

# 2. Notebook copy with this run's range and CSV filled in
mkdir -p "$WORK/nb"
python3 - "$NB" "$WORK/nb/$SLUG.ipynb" "$START" "$END" "$SHOTS_CSV" <<'PY'
import json, os, sys
src, dst, start, end, csv_name = sys.argv[1:]
nb = json.load(open(src))
tok = os.environ.get("HF_TOKEN", "").strip()
if tok:    # opt-in: only when HF_TOKEN is set where this script runs. Goes into this private notebook copy only (never into a file here); gives faster, rate-limit-free downloads.
    first = next(i for i, c in enumerate(nb["cells"]) if c["cell_type"] == "code")
    nb["cells"].insert(first, {"cell_type": "code", "metadata": {}, "execution_count": None, "outputs": [],
                               "source": ["import os\n", "os.environ['HF_TOKEN'] = " + repr(tok)]})
for c in nb["cells"]:
    new = []
    for l in c["source"]:
        if l.startswith("START, END = "):
            l = f"START, END = {start}, {end}\n" if l.endswith("\n") else f"START, END = {start}, {end}"
        elif l.startswith("CSV_NAME = "):
            l = f"CSV_NAME = '{csv_name}'\n" if l.endswith("\n") else f"CSV_NAME = '{csv_name}'"
        new.append(l)
    c["source"] = new
json.dump(nb, open(dst, "w"), indent=1)
PY
cat > "$WORK/nb/kernel-metadata.json" <<JSON
{
  "id": "$USER_SLUG/$SLUG",
  "title": "${SLUG//-/ }",
  "code_file": "$SLUG.ipynb",
  "language": "python",
  "kernel_type": "notebook",
  "is_private": "true",
  "enable_gpu": "$GPU_FLAG",
  "enable_tpu": "$TPU_FLAG",
  "enable_internet": "true",
  "machine_shape": "$ACCEL",
  "dataset_sources": ["$USER_SLUG/$DS"],
  "competition_sources": [],
  "kernel_sources": [],
  "model_sources": []
}
JSON

# 3. Push (this also starts the run) and wait
echo "== pushing kernel $USER_SLUG/$SLUG on $ACCEL"
# `kaggle kernels push` can print an error and still exit 0, so the text is checked. Kaggle runs only 2 GPU sessions at a time: when both are busy
# (for example a previous run still going) wait and try again instead of pretending the notebook was pushed.
PUSHED=""
for TRY in $(seq 1 45); do
  kaggle kernels push -p "$WORK/nb" --accelerator "$ACCEL" 2>&1 | tee "$WORK/push.txt" || true
  if grep -qi "successfully pushed" "$WORK/push.txt"; then PUSHED=1; break; fi
  if grep -qi "Maximum batch GPU session count\|Maximum .* session count" "$WORK/push.txt"; then
    echo "== Kaggle allows only 2 GPU sessions at a time and both are busy; waiting 2 minutes (try $TRY of 45)"
    sleep 120
    continue
  fi
  break
done
if [ -z "$PUSHED" ]; then
  echo "!! kernel push failed: $(tr '\n' ' ' < "$WORK/push.txt" | cut -c1-300)"
  exit 1
fi
echo "== kernel pushed: https://www.kaggle.com/code/$USER_SLUG/$SLUG"
echo "== waiting for the run (checks every 60 s; Ctrl-C stops waiting, the run continues on Kaggle)"
while true; do
  STATUS=$(kaggle kernels status "$USER_SLUG/$SLUG" 2>&1 || true)
  echo "$(date +%H:%M:%S) $STATUS"
  case "$STATUS" in
    *COMPLETE*|*complete*)
      echo "== kernel completed"
      break ;;
    *ERROR*|*error*|*CANCEL*|*cancel*|*FAIL*|*fail*)
      echo "!! kernel run did not complete successfully (status: $STATUS); fetching whatever output exists"
      break ;;
    *"NOT FOUND"*|*"not found"*|*404*|*"Cannot access kernel"*)
      echo "!! kernel not found on Kaggle (may have been deleted or never created)"
      exit 1 ;;
    *QUEUED*|*queued*)
      echo "== kernel is queued, waiting for resources..." ;;
    *RUNNING*|*running*)
      echo "== kernel is running..." ;;
  esac
  sleep 60
done

# 4. Download clips and flatten into OUTDIR
mkdir -p "$OUTDIR" "$WORK/out"
kaggle kernels output "$USER_SLUG/$SLUG" -p "$WORK/out" -o
mkdir -p "$PD/logs"
for f in "$WORK"/out/*.log; do [ -f "$f" ] && cp "$f" "$PD/logs/"; done          # keep the kernel log (the temp folder is deleted on exit)
case "$STATUS" in *ERROR*|*error*|*CANCEL*|*cancel*|*FAIL*|*fail*)
  python3 - "$PD/logs/$SLUG.log" <<'PY' || true
import json, re, sys
try:
    raw = open(sys.argv[1]).read()
    try:
        text = "".join(e.get("data", "") for e in json.loads(raw))
    except Exception:
        text = raw
    text = re.sub(r"\x1b\[[0-9;]*m", "", text)
    print("\n----- end of the Kaggle log (full log: " + sys.argv[1] + ") -----\n" + text[-3500:] + "\n-----")
except OSError:
    print("(no log was downloaded)")
PY
esac
find "$WORK/out" \( -name 'shot-*.mp4' -o -name '*.wav' -o -name 'image-*.png' \) -exec mv {} "$OUTDIR/" \;
echo "✅ $(ls "$OUTDIR"/*.mp4 "$OUTDIR"/*.wav "$OUTDIR"/*.png 2>/dev/null | wc -l | tr -d ' ') files now in $(pwd)/$OUTDIR"
echo "   Log and page: https://www.kaggle.com/code/$USER_SLUG/$SLUG   (log saved in $PD/logs/)"
