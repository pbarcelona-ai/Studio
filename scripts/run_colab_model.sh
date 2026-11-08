#!/usr/bin/env bash
# Usage: [PROJECT=adam_eve] ./run_colab_model.sh MODEL START END [GPU]    (default project: adam_eve)
#        MODEL = ltx_video | wan | cogvideox (video) | audio_kokoro | audio_musicgen | audio_mmaudio (audio) | image_sdxl_turbo | image_sdxl | image_sd35_medium (images)
# e.g.   ./run_colab_model.sh wan 1 5 T4
#         SHOTS_CSV=all_chapters.csv ./run_colab_model.sh wan 1 5 T4    # one prompt per chapter
# Renders shots on a Colab GPU and unpacks them into ./videos/MODEL/shot-NNNN.mp4.
set -euo pipefail
cd "$(dirname "$0")/.."          # the repository root: the generated colab_generate_*.py files and projects/ are relative to it
PROJECT=${PROJECT:-adam_eve}; PD="$(python3 scripts/layout.py "$PROJECT")"      # projects/books/<book>, projects/characters/<set> or projects/prompts/<set> (see layout.py)
[ -d "$PD" ] || { echo "no such project: $PD"; exit 1; }
MODEL=${1:?model: ltx_video | wan | cogvideox | audio_kokoro | audio_musicgen | audio_mmaudio | image_sdxl_turbo | image_sdxl | image_sd35_medium}; START=${2:?start shot}; END=${3:?end shot}; GPU=${4:-T4}
case "$MODEL" in audio_*) SHOTS_CSV=${SHOTS_CSV:-audio_shots.csv} ;; image_*) SHOTS_CSV=${SHOTS_CSV:-all_images.csv} ;; *) SHOTS_CSV=${SHOTS_CSV:-all_shots.csv} ;; esac
case "$MODEL" in tpu_*|image_tpu_*) echo "$MODEL is Kaggle-only (TPU): use run_kaggle_model.sh"; exit 1 ;; esac
SCRIPT="colab_generate_${MODEL}.py"
case "$MODEL" in audio_*) OUTDIR="$PD/audio/${MODEL#audio_}" ;; image_*) OUTDIR="$PD/images/${MODEL#image_}" ;; *) OUTDIR="$PD/videos/$MODEL" ;; esac
case "$SHOTS_CSV" in *chapters*) OUTDIR="${OUTDIR}_chapters" ;; esac
GEN=""
if [ ! -f "$SCRIPT" ]; then      # generated files can be deleted by the clean-up: re-create them in a throw-away folder, so the project folder stays clean
  GEN=$(mktemp -d)
  BIBLE_GEN_DIR="$GEN" python3 scripts/make_all.py >/dev/null 2>&1 || true
  SCRIPT="$GEN/$SCRIPT"
fi
[ -f "$SCRIPT" ] || { echo "no such model: $MODEL (missing $SCRIPT)"; exit 1; }
S="${PROJECT//_/-}-$MODEL-$START-$END"      # the Colab session name

colab new -s "$S" --gpu "$GPU"
trap 'colab stop -s "$S" || true; [ -z "$GEN" ] || rm -rf "$GEN"' EXIT   # always release the VM

colab upload -s "$S" "$PD/$SHOTS_CSV" /content/all_shots.csv
case "$MODEL" in audio_*) ;; *) colab install -s "$S" diffusers transformers accelerate sentencepiece protobuf imageio imageio-ffmpeg ftfy gguf peft safetensors ;; esac   # audio scripts install their own packages
{ echo "START, END = $START, $END"; cat "$SCRIPT"; } | colab exec -s "$S"

mkdir -p "$OUTDIR"
colab download -s "$S" "/content/batch_${START}_${END}.tar" "$OUTDIR/batch.tar"
tar -xf "$OUTDIR/batch.tar" -C "$OUTDIR" && rm "$OUTDIR/batch.tar"
echo "✅ clips in $(pwd)/$OUTDIR"
