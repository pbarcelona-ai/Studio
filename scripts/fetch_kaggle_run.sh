#!/usr/bin/env bash
# Pick up a Kaggle run whose local waiter is gone (laptop slept, page closed, terminal closed) and put its results in the project.
#
# Usage: ./fetch_kaggle_run.sh KERNEL_SLUG [--wait] [--project NAME] [--dest DIR]
#   KERNEL_SLUG  the notebook name, e.g. adam-eve-wan-1-40 (also accepted: pbarcelona/adam-eve-wan-1-40; very old runs had one extra word in front)
#   --wait       if the run is still going, check every 60 s until it ends, then download
#   --project    the book / character set / prompt set name (guessed from the slug if omitted); it lives under projects/books, projects/characters or projects/prompts
#   --dest DIR   copy into DIR instead of the project's folder (for testing)
# The run keeps going on Kaggle whatever happens on this Mac; this only downloads. It never starts or changes a run.
set -euo pipefail
command -v kaggle >/dev/null || export PATH="$HOME/.local/bin:$PATH"
cd "$(dirname "$0")/.."

SLUG=""; WAIT=0; PROJECT=""; DEST=""
while [ $# -gt 0 ]; do
  case "$1" in
    --wait) WAIT=1 ;;
    --project) PROJECT="$2"; shift ;;
    --dest) DEST="$2"; shift ;;
    -*) echo "unknown option $1"; exit 1 ;;
    *) SLUG="$1" ;;
  esac
  shift
done
[ -n "$SLUG" ] || { sed -n '2,12p' "$0"; exit 1; }

# full name owner/slug
case "$SLUG" in
  */*) REF="$SLUG"; SLUG="${SLUG#*/}" ;;
  *) REF=$(kaggle kernels list -m -v --page-size 100 2>/dev/null | cut -d, -f1 | grep "/$SLUG\$" | head -1 || true)
     [ -n "$REF" ] || { echo "no notebook named $SLUG on your Kaggle account (try: kaggle kernels list -m)"; exit 1; } ;;
esac

# which project: the longest book / character set / prompt set whose name (underscores -> dashes) starts the slug (if none does, one extra word in front of it is skipped: very old runs had one)
if [ -z "$PROJECT" ]; then
  best=""
  for NAME in "$SLUG" "${SLUG#*-}"; do
    for d in projects/books/*/ projects/characters/*/ projects/prompts/*/; do
      [ -d "$d" ] || continue
      case "$d" in projects/characters/*) [ -f "${d}promptset.json" ] || continue ;; esac     # a character SERIES (tokens) is not a run target
      n=$(basename "$d"); k="${n//_/-}-"
      case "$NAME" in "$k"*) [ ${#n} -gt ${#best} ] && best="$n" ;; esac
    done
    [ -n "$best" ] && break
  done
  PROJECT="$best"
fi
if [ -n "$DEST" ]; then PD="$DEST"; else
  [ -n "$PROJECT" ] && PD="$(python3 scripts/layout.py "$PROJECT")" && [ -d "$PD" ] || { echo "could not tell which project this belongs to: add --project NAME"; exit 1; }
fi

status() { kaggle kernels status "$REF" 2>&1 | grep -o 'KernelWorkerStatus\.[A-Za-z]*' | head -1 | sed 's/KernelWorkerStatus\.//' || true; }
S=$(status); echo "$REF is: ${S:-unknown}"
while [ "$S" = "RUNNING" ] || [ "$S" = "QUEUED" ]; do
  if [ $WAIT -eq 0 ]; then echo "still going on Kaggle; run this again later, or add --wait to wait for it"; exit 2; fi
  sleep 60; S=$(status); echo "$(date +%H:%M:%S) $S"
done

TMP=$(mktemp -d); trap 'rm -rf "$TMP"' EXIT
kaggle kernels output "$REF" -p "$TMP" -o -q
mkdir -p "$PD/logs"
for f in "$TMP"/*.log; do [ -f "$f" ] && cp "$f" "$PD/logs/"; done
n=0
for d in videos audio images; do                       # the notebooks save to videos/<model>, audio/<kind>, images/<model>
  if [ -d "$TMP/$d" ]; then
    mkdir -p "$PD/$d"; cp -R "$TMP/$d/." "$PD/$d/"
    n=$((n + $(find "$TMP/$d" -type f | wc -l)))
  fi
done
echo "✅ $n file(s) copied into $PD/   (log saved in $PD/logs/)"
if [ "$S" != "COMPLETE" ]; then
  echo "note: the run ended as ${S:-unknown}. End of its log:"
  python3 - "$PD/logs/$SLUG.log" <<'PY' || true
import json, re, sys
try:
    raw = open(sys.argv[1]).read()
    try: text = "".join(e.get("data", "") for e in json.loads(raw))
    except Exception: text = raw
    print(re.sub(r"\x1b\[[0-9;]*m", "", text)[-2500:])
except OSError:
    print("(no log was downloaded)")
PY
fi
