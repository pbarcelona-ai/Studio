#!/usr/bin/env python3
"""Regression test: send one small job per model to Kaggle through the Studio's own code path and check that it really produced a file.

  python3 scripts/regress_kaggle.py --user YOURNAME              run every model (video, image, audio), one at a time; STOPS at the first failure
  python3 scripts/regress_kaggle.py --user YOURNAME --only sdxl_turbo,wan   just those
  python3 scripts/regress_kaggle.py --user YOURNAME --dry-run     show the plan, push nothing
  python3 scripts/regress_kaggle.py --user YOURNAME --again       also re-run the models that already passed
  python3 scripts/regress_kaggle.py --user YOURNAME --keep-going  do not stop at a failure; test everything and list the failures at the end
  python3 scripts/regress_kaggle.py --steps-cap 6 --only MODEL --again   run one model with at most 6 steps (quick smoke test)
  python3 scripts/regress_kaggle.py --list                        list the models that would be tested

The prompt: the text in regression_prompt.txt (repository root) is sent to every model; edit it to compare the models on a new prompt. A pass only counts for the
prompt it was run with, so changing the file re-runs everything. Without the file the built-in zombie prompt is used.
How it works: for each model it asks studio.prompt_plan() for the same steps the page would run (so the CSV row, dataset, notebook and push are the
real ones), runs run_kaggle_model.sh, waits for the kernel, then looks for a new, non-trivial output file. Sizes are the model's defaults (that is
where out-of-memory bugs show up); steps are NOT cut unless --steps-cap is given. TPU models are skipped.
Fix-first workflow: by default the run stops at the first model that fails and prints the end of the Kaggle log. Fix the cause, run the same command
again: models that already passed are skipped, so it carries on with the model you just fixed. --lanes 2 runs two models at once (Kaggle allows two GPU
sessions); each lane has its own prompt set so the dataset versions do not race: projects/regression/regtest_a and regtest_b. The kernels stay on your Kaggle account: remove them with the Cleanup button on the Import tab.
Results: regression_kaggle_report.json / .md in the repository root (re-running skips models that passed), full logs in projects/regression/regtest_*/logs/.
"""
import argparse
import json
import queue
import re
import subprocess
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import studio as S                       # noqa: E402  (the Studio's planner, so the test follows the real code path)

REPORT = ROOT / "regression_kaggle_report.json"
DEFAULT_PROMPT = "a young woman running towards the camera, zombies are chasing her down a city street. not blurry, no cartoon."


def read_prompt():
    """The test prompt: the text in regression_prompt.txt (or regression_prompt) in the repository root, else the built-in zombie prompt."""
    for name in ("regression_prompt.txt", "regression_prompt"):
        try:
            t = " ".join((ROOT / name).read_text(encoding="utf-8").split())
        except OSError:
            continue
        if t:
            return t
    return DEFAULT_PROMPT


TEST_PROMPT = read_prompt()                     # the same prompt for every model
PROMPT = {"video": TEST_PROMPT, "image": TEST_PROMPT}
AUDIO = {f"audio_{k}": k for k in S.AUDIO_MODELS}
STEPS_CAP = 0                       # 0 = no limit: every model runs at its real default steps (a true comparison)
lock = threading.Lock()
stop = threading.Event()               # set at the first failure unless --keep-going


def all_models():
    video = [("video", m) for m in S.VIDEO_MODELS if not m.startswith("tpu_") and m not in S.I2V_MODELS]   # *_i2v need a book's keyframes
    image = [("image", m) for m in S.IMAGE_MODELS if not m.startswith("tpu_")]
    audio = [("audio", m) for m in AUDIO]
    return image + video + audio                 # cheap image models first, the 14B / 13B ones later


def load_report():
    try:
        return json.loads(REPORT.read_text())
    except (OSError, ValueError):
        return {}


def save_report(rep):
    with lock:
        REPORT.write_text(json.dumps(rep, indent=1))
        rows = ["| model | kind | result | minutes | note |", "|---|---|---|---|---|"]
        for k, v in rep.items():
            rows.append(f"| {k} | {v.get('kind', '')} | {v['result']} | {v.get('minutes', '')} | {str(v.get('note', ''))[:160]} |")
        (ROOT / "regression_kaggle_report.md").write_text("# Kaggle regression run\n\n" + "\n".join(rows) + "\n")


def lane_dir(lane):
    return ROOT / "projects" / "regression" / f"regtest_{lane}"


def make_opt(kind, model, lane, user, gpu):
    d = S.MODEL_DEFAULTS.get(model, {})
    steps = d.get("steps")
    o = {"variations": 1}
    if steps and "steps" not in d.get("locked", []):
        o["steps"] = str(min(int(steps), STEPS_CAP) if STEPS_CAP else int(steps))
    return {"mode": "prompts", "set": f"regtest_{lane}", "kind": kind, "model": model, "prompts": PROMPT[kind], "opts": o,
            "service": "kaggle", "gpu": gpu, "kaggle_user": user, "batch": "0"}


def audio_csv(lane):
    d = lane_dir(lane)
    d.mkdir(parents=True, exist_ok=True)
    (d / "promptset.json").write_text(json.dumps({"type": "prompts"}))
    import csv
    with open(d / "audio_shots.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["chapter", "shot", "lines_json", "narration", "sfx", "music"])
        w.writerow(["regtest", 1, json.dumps([["NARRATOR", TEST_PROMPT]]), TEST_PROMPT, TEST_PROMPT, TEST_PROMPT])   # narration, sound effects and music all get the same text


def out_files(lane, kind, model):
    base = lane_dir(lane)
    if kind == "image":
        return list((base / "images" / model).glob("image-*.png"))
    if kind == "video":
        return list((base / "videos" / model).glob("shot-*.mp4"))
    return list((base / "audio" / AUDIO[model]).glob("*.wav"))


def judge(files, kind):
    """Newest file must be more than a stub; a flat (all one colour) picture counts as a failure."""
    if not files:
        return False, "no output file"
    f = max(files, key=lambda p: p.stat().st_mtime)
    size = f.stat().st_size
    if size < (20_000 if kind != "audio" else 20_000):
        return False, f"{f.name} is only {size} bytes"
    if kind == "image":
        try:
            from PIL import Image, ImageStat
            im = Image.open(f).convert("L")
            if max(ImageStat.Stat(im).stddev) < 3:
                return False, f"{f.name} is a flat picture"
        except ImportError:
            pass
    return True, f"{f.name} ({size // 1024} KB)"


def run_one(kind, model, lane, user, gpu, timeout_min):
    t0 = time.time()
    before = {p: p.stat().st_mtime for p in out_files(lane, kind, model)}
    if kind == "audio":
        audio_csv(lane)
        argv, env = ["scripts/run_kaggle_model.sh", model, "1", "1"], {"PROJECT": f"regtest_{lane}", "SHOTS_CSV": "audio_shots.csv", "KAGGLE_USER": user, "KAGGLE_ACCELERATOR": gpu}
    else:
        with lock:                                      # prompt_plan appends the CSV row; keep it one lane at a time
            steps = S.prompt_plan(make_opt(kind, model, lane, user, gpu), True)
        argv, env = steps[0]["argv"], steps[0]["env"]
    logp = lane_dir(lane) / "logs"
    logp.mkdir(parents=True, exist_ok=True)
    log = logp / f"regress_{model}.txt"
    try:
        with open(log, "w") as lf:
            p = subprocess.run(argv, cwd=ROOT, env={**S.clean_env(), **env}, stdout=lf, stderr=subprocess.STDOUT, timeout=timeout_min * 60)
        text = log.read_text(errors="replace")
    except subprocess.TimeoutExpired:
        return {"kind": kind, "result": "TIMEOUT", "minutes": round((time.time() - t0) / 60), "note": f"no result after {timeout_min} min (the run may still be going on Kaggle)"}
    completed = "== kernel completed" in text
    files = [f for f in out_files(lane, kind, model) if f not in before or f.stat().st_mtime > before[f]]
    ok, why = judge(files, kind)
    if completed and ok:
        res, note = "PASS", why
    else:
        tail = re.sub(r"\x1b\[[0-9;]*m", "", text)
        m = re.findall(r"(?:FAILED|Error|ERROR|OutOfMemory|out of memory)[^\n]{0,200}", tail)
        res = "FAIL"
        note = ("kernel did not complete; " if not completed else "") + (why if not ok else "") + ((" | " + m[-1]) if m else "")
    return {"kind": kind, "result": res, "minutes": round((time.time() - t0) / 60), "note": note, "log": str(log.relative_to(ROOT))}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--user", help="your Kaggle username (the part after kaggle.com/)")
    ap.add_argument("--only", default="", help="comma-separated model names")
    ap.add_argument("--kinds", default="", help="comma-separated kinds to test: image, video, audio (default: all of them)")
    ap.add_argument("--lanes", type=int, default=1, help="how many runs at the same time, 1 or 2 (Kaggle allows 2 GPU sessions). Default 1")
    ap.add_argument("--keep-going", action="store_true", help="do not stop at the first failure")
    ap.add_argument("--list", action="store_true", help="list the models and exit")
    ap.add_argument("--timeout", type=int, default=90, help="minutes to wait for one model")
    ap.add_argument("--steps-cap", type=int, default=0, help="most steps any model is run with. Default 0 = no limit, every model runs at its real default steps; use a small number (for example 6) for a quick smoke test")
    ap.add_argument("--gpu", default="NvidiaTeslaT4")
    ap.add_argument("--again", action="store_true", help="re-run models that passed before")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    global STEPS_CAP
    STEPS_CAP = a.steps_cap
    if a.list:
        for kind, model in all_models():
            print(f"{model:24s} {kind:6s} {load_report().get(model, {}).get('result', '-')}")
        return
    if not a.user:
        ap.error("--user is required (your Kaggle username)")

    todo = all_models()
    if a.kinds:
        kinds = {x.strip() for x in a.kinds.split(",") if x.strip()}
        if not kinds <= {"image", "video", "audio"}:
            sys.exit("--kinds takes image, video and/or audio")
        todo = [t for t in todo if t[0] in kinds]
    if a.only:
        want = {x.strip() for x in a.only.split(",") if x.strip()}
        todo = [t for t in todo if t[1] in want]
        missing = want - {t[1] for t in todo}
        if missing:
            sys.exit(f"unknown model(s): {', '.join(sorted(missing))}")
    rep = load_report()
    if not a.again:
        # a pass only counts for the prompt it was run with: a new regression_prompt re-runs everything
        todo = [t for t in todo if not (rep.get(t[1], {}).get("result") == "PASS" and rep[t[1]].get("prompt", DEFAULT_PROMPT) == TEST_PROMPT)]
    print(f"prompt: {TEST_PROMPT}", flush=True)
    print(f"{len(todo)} model(s) to test on {a.gpu}: {', '.join(m for _, m in todo)}", flush=True)
    if a.dry_run:
        for kind, model in todo:
            if kind == "audio":
                print(f"  {model}: audio row 1 (audio notebook)")
                continue
            try:
                steps = S.prompt_plan(make_opt(kind, model, "a", a.user, a.gpu), False)
                print(f"  {model}: {steps[0]['label']} -> {' '.join(steps[0]['argv'])}  opts={make_opt(kind, model, 'a', a.user, a.gpu)['opts']}")
            except S.PlanError as e:
                print(f"  {model}: REFUSED by the planner: {e}")
        return

    q = queue.Queue()
    for t in todo:
        q.put(t)

    def worker(lane):
        while not stop.is_set():
            try:
                kind, model = q.get_nowait()
            except queue.Empty:
                return
            print(f"[lane {lane}] START {model}", flush=True)
            try:
                r = run_one(kind, model, lane, a.user, a.gpu, a.timeout)
            except S.PlanError as e:
                r = {"kind": kind, "result": "REFUSED", "note": str(e)[:300]}
            except Exception as e:                      # keep the other models going
                r = {"kind": kind, "result": "ERROR", "note": f"{type(e).__name__}: {e}"[:300]}
            r["prompt"] = TEST_PROMPT
            rep[model] = r
            save_report(rep)
            print(f"[lane {lane}] {r['result']} {model} ({r.get('minutes', '?')} min) {r.get('note', '')[:200]}", flush=True)
            if r["result"] != "PASS" and not a.keep_going:
                stop.set()
                print(f"\nSTOPPED at {model}: fix it, then run the same command again (models that passed are skipped).", flush=True)
                if r.get("log"):
                    try:
                        t = re.sub(r"\x1b\[[0-9;]*m", "", (ROOT / r["log"]).read_text(errors="replace"))
                        tail = t.split("----- end of the Kaggle log")[-1] if "----- end of the Kaggle log" in t else t
                        print(f"--- end of the log ({r['log']}) ---\n" + "\n".join(tail.strip().splitlines()[-30:]) + "\n---", flush=True)
                    except OSError:
                        pass

    threads = [threading.Thread(target=worker, args=("ab"[i % 2] if a.lanes > 1 else "a",)) for i in range(max(1, min(a.lanes, 2)))]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    bad = [m for m, v in rep.items() if v["result"] != "PASS"]
    print(f"\nDone: {sum(1 for v in rep.values() if v['result'] == 'PASS')} passed, {len(bad)} not passed: {', '.join(bad) or 'none'}", flush=True)
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
