#!/usr/bin/env bash
# Kaggle regression test: one small job per model, stops at the first failure so it can be fixed before moving on.
set -euo pipefail

help() {
  cat <<'EOF'
run_regression.sh - send one small job per model to Kaggle and check that each really produces a file

USAGE
  scripts/run_regression.sh [options]

OPTIONS
  -u USER     your Kaggle username (the part after kaggle.com/). Default: $KAGGLE_USER, else the one the Kaggle CLI is logged in as
  -m LIST     only these models, comma separated (for example: -m sdxl,wan)
  -v          only the video models
  -i          only the image models
  -a          only the audio models   (any mix of -v -i -a runs those kinds; none of them = all three kinds)
  -k          keep going after a failure (default: STOP at the first failure so you can fix it first)
  -r          run again the models that already passed (default: skip them)   [was -a]
  -l          list the models and their last result, then exit
  -n          dry run: show what would be sent, send nothing
  -2          run two models at the same time (Kaggle allows two GPU sessions); the default is one at a time
  -t MIN      minutes to wait for one model (default 90)
  -g GPU      Kaggle accelerator (default NvidiaTeslaT4)
  -s N        most steps any model runs with (default: no limit, every model runs its real default steps; -s 6 gives a quick smoke test)
  -h          show this help

HOW IT WORKS
  Each model gets one prompt, at its default size and default steps, sent through the same code the Studio uses (CSV row, dataset,
  notebook, push). It passes when the Kaggle run completes AND a real picture, clip or sound file comes back.
  The run stops at the first failure and prints the end of the Kaggle log. Fix the cause, then run the same command again:
  models that passed are skipped, so it carries on with the one you fixed.

FILES
  regression_kaggle_report.md / .json   result per model (the .json is what makes a re-run skip the passed ones)
  projects/regression/regtest_a/logs/      the full log of each model (regtest_b for the second lane)
  The notebooks stay on your Kaggle account; remove them with the Cleanup button on the Import tab.

EXAMPLES
  scripts/run_regression.sh -l                 what is there and what passed
  scripts/run_regression.sh -n                 what would be sent
  scripts/run_regression.sh -m sdxl            just sdxl
  scripts/run_regression.sh                    everything not yet passed, stopping at the first failure
  scripts/run_regression.sh -k                 everything, listing all failures at the end
  scripts/run_regression.sh -v -k              only the video models
  scripts/run_regression.sh -i -r              only the image models, again even if they passed
  scripts/run_regression.sh -a -k              only the audio models

NOTE  A full run uses several hours of Kaggle GPU time (the free allowance is about 30 hours a week).
EOF
}

cd "$(dirname "$0")/.."
USER_SLUG=${KAGGLE_USER:-}; ARGS=()
KINDS=()
while getopts ":u:m:krlnt:g:s:2hvia" o; do
  case "$o" in
    u) USER_SLUG=$OPTARG ;;
    m) ARGS+=(--only "$OPTARG") ;;
    k) ARGS+=(--keep-going) ;;
    r) ARGS+=(--again) ;;
    a) KINDS+=(audio) ;;
    l) ARGS+=(--list) ;;
    n) ARGS+=(--dry-run) ;;
    t) ARGS+=(--timeout "$OPTARG") ;;
    g) ARGS+=(--gpu "$OPTARG") ;;
    s) ARGS+=(--steps-cap "$OPTARG") ;;
    2) ARGS+=(--lanes 2) ;;
    v) KINDS+=(video) ;;
    i) KINDS+=(image) ;;
    h) help; exit 0 ;;
    :) echo "option -$OPTARG needs a value"; echo; help; exit 2 ;;
    *) echo "unknown option -$OPTARG"; echo; help; exit 2 ;;
  esac
done

if [ ${#KINDS[@]} -gt 0 ]; then ARGS+=(--kinds "$(IFS=,; echo "${KINDS[*]}")"); fi

if [ -z "$USER_SLUG" ]; then      # the Kaggle CLI knows who is logged in
  USER_SLUG=$(env -u PYTHONHOME kaggle config view 2>/dev/null | sed -n 's/^- username: *//p' | head -1 || true)
fi
case " ${ARGS[*]-} " in *" --list "*) exec env -u PYTHONHOME python3 scripts/regress_kaggle.py --list ;; esac
[ -n "$USER_SLUG" ] || { echo "no Kaggle username: use -u USER or set KAGGLE_USER"; echo; help; exit 2; }
exec env -u PYTHONHOME python3 scripts/regress_kaggle.py --user "$USER_SLUG" ${ARGS[@]+"${ARGS[@]}"}
