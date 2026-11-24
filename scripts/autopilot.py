#!/usr/bin/env python3
"""AUTOPILOT (BOOK_TO_SCREEN_BUILD.md Section 2 rule 4, Sections 10.2, 12; milestone M15): every step from the sources to the downloads.

  python3 autopilot.py <project> [--stop-at script,continuity,shotlist,pictures,cut] [--engine claude|... |fake] [--model M]
                       [--service kaggle|colab|huggingface|computer --gpu G --kaggle-user U --image-model M --video-model M] [--confirm-spend]

The Producer runs the same steps, prompts and data as Review mode, approving each gate itself, except the gates ticked in --stop-at: there it
stops ("waiting for your review at the shot list"); run it again after approving and it carries on. Each step still runs its crew critique.
Every finished step makes a history moment. Before the first paid picture or clip it compares the estimate with the spending limit
(production.json spend_limit, $0 by default) and stops unless --confirm-spend. Style variants render in parallel, up to the service's limit
(LIMITS). GPU renders go through the Studio's usual runners (run_kaggle_model.py ...); tests and demos pass their own `gpu` function.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from collections.abc import Callable, Sequence
from concurrent.futures import ThreadPoolExecutor
from functools import partial
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import adaptation  # noqa: E402
import book_exports  # noqa: E402
import clips  # noqa: E402
import consistency  # noqa: E402
import continuity_book  # noqa: E402
import crew  # noqa: E402
import edl  # noqa: E402
import gates  # noqa: E402
import history  # noqa: E402
import layout  # noqa: E402
import marketing  # noqa: E402
import pictures  # noqa: E402
import production  # noqa: E402
import read_it_in  # noqa: E402
import render_cut  # noqa: E402
import screenplay  # noqa: E402
import shot_list  # noqa: E402
import sound_design  # noqa: E402
import styles  # noqa: E402

STOPS = ("script", "continuity", "shotlist", "pictures", "cut")
LIMITS = {"kaggle": 2, "colab": 1, "huggingface": 1, "computer": 1, "fake": 4}
Gpu = Callable[[str, str, int, int, str, dict], None]          # (prompt set or book, model, first row, last row, csv, extra env)


class Waiting(Exception):
    """Autopilot stopped at a review gate the owner ticked, or before spending money; the message says what to do."""


def state_file(pdir: Path) -> Path:
    return pdir / "autopilot" / "state.json"


def runner_gpu(service: str, gpu: str, user: str) -> Gpu:
    """Render with the Studio's usual runner programs, one at a time per call (the caller decides the parallelism)."""
    from studio_app.config import ROOT
    from studio_app.steps import make_runner, script_argv

    def go(target: str, model: str, first: int, last: int, csv_name: str, extra: dict) -> None:
        argv, env = make_runner(service, gpu, user, target)(model, first, last, csv_name)
        r = subprocess.run(script_argv(argv), cwd=ROOT, env={**os.environ, "PYTHONUTF8": "1", **env, **extra}, check=False)
        if r.returncode != 0:
            raise RuntimeError(f"the {model} run of {target} rows {first}-{last} failed (exit {r.returncode})")
    return go


class Autopilot:
    def __init__(self, pdir: Path, ask_text, ask_image, gpu: Gpu, stop_at: list[str], confirm_spend: bool = False, service: str = "kaggle",
                 image_model: str = "flux2_klein_4b", video_model: str = "ltx_video_fast_i2v", say: Callable[[str], None] = print,
                 audio: Callable[[str], None] | None = None) -> None:
        self.pdir, self.ask, self.ask_image, self.gpu = pdir, ask_text, ask_image, gpu
        self.stop_at, self.confirm, self.service = set(stop_at), confirm_spend, service
        self.image_model, self.video_model, self._say, self.audio = image_model, video_model, say, audio

    def say(self, text: str) -> None:
        state_file(self.pdir).parent.mkdir(parents=True, exist_ok=True)
        state_file(self.pdir).write_text(json.dumps({"at": time.strftime("%Y-%m-%dT%H:%M:%S"), "text": text}), encoding="utf-8")
        self._say(text)

    def moment(self, label: str) -> None:
        history.create(self.pdir, f"autopilot: {label}", "autopilot")

    def gate(self, stop: str, label: str, approve: Callable[[], object], approved: bool) -> None:
        if approved:
            return
        if stop in self.stop_at:
            raise Waiting(f"Waiting for your review at {label}. Approve it, then press Make my film again to carry on.")
        approve()
        self.moment(f"approved {label}")

    # ---------------------------------------------------------------------------------------------- the steps
    def run(self) -> dict:
        p = self.pdir
        st = production.load(p)
        products = set(st["products"])
        self.say("Your producer is starting the film")
        if not (p / "readin" / "summary.json").is_file():
            read_it_in.ReadItIn(p, lambda pr, role, step, v: self.ask(pr, role, step, v), self._say).run()
            self.moment("read it in")
        plan = adaptation.load(p)
        self.gate("script", "the screenplay", lambda: screenplay.approve(p, plan), screenplay.status(p, plan).get("approved", False) if plan else False)
        book = continuity_book.load(p)
        if not book.get("style_neutral"):
            continuity_book.write(p, self.ask)
            book = continuity_book.load(p)
            self.moment("continuity book")
        cb_data = [book.get("characters", []), book.get("locations", []), book.get("props", [])]
        self.gate("continuity", "the continuity book", lambda: gates.approve(p, "continuity", cb_data), gates.approved(p, "continuity", cb_data))
        if not shot_list.load(p).get("scenes"):
            shot_list.write(p, self.ask, self._say)
            self.moment("shot list")
        sl = shot_list.load(p)
        self.gate("shotlist", "the shot list", lambda: gates.approve(p, "shotlist", shot_list.gate_data(sl)), gates.approved(p, "shotlist", shot_list.gate_data(sl)))
        if products & {"storyboard", "illustrated_book", "animatic", "film", "marketing"}:
            self.spending_check(st)
            self.look_development(st)
            self.pictures(st)
        if products & {"animatic", "film", "audiobook", "marketing"}:
            self.sound()
        made: list[str] = []
        if products & {"storyboard", "illustrated_book"}:
            made += [x.name for x in book_exports.export(p, st["master"], tuple(k for k, want in (("storyboard", "storyboard"), ("illustrated", "illustrated_book"),
                                                                                               ("epub", "illustrated_book")) if want in products))]
        if products & {"animatic", "film", "marketing"}:
            e = edl.load(p) or edl.assemble(p)
            self.gate("cut", "the final cut", lambda: gates.approve(p, "edit", edl.load(p)["cuts"]), gates.approved(p, "edit", e["cuts"]))
        if "animatic" in products:
            made += [render_cut.render(p, s["id"], "animatic").name for s in st["styles"]]
        if products & {"film", "marketing"}:
            made += self.film(st)
        if "marketing" in products:
            if not marketing.load(p):
                marketing.write_plan(p, self.ask)
            for s in st["styles"]:
                marketing.render(p, s["id"])
                made.append(f"marketing_{s['id']}")
        if "audiobook" in products and self.audio is not None:
            self.audio("audiobook")
            made.append(Path(sound_design.make_audiobook(p)["m4b"]).name)
        self.moment("finished")
        self.say(f"Done: {', '.join(made) or 'everything up to date'}.")
        return {"made": made}

    def spending_check(self, st: dict) -> None:
        est = production.estimate(st, paid=self.service not in ("kaggle", "colab", "huggingface", "computer", "fake"))
        limit = float(st.get("spend_limit", 0) or 0)
        if est["dollars"] > limit and not self.confirm:
            raise Waiting(f"The pictures and clips would cost about ${est['dollars']:.2f}, over your limit of ${limit:.2f}. Raise the limit or confirm the spend.")

    def _parallel(self, jobs: Sequence[Callable[[], object]]) -> None:
        with ThreadPoolExecutor(max_workers=max(1, LIMITS.get(self.service, 1))) as pool:
            for f in [pool.submit(j) for j in jobs]:
                f.result()

    def look_development(self, st: dict) -> None:
        p = self.pdir
        todo: list[Callable[[], object]] = []
        for s in st["styles"]:
            sid = s["id"]
            if not (styles.sdir(p, sid) / "card.json").is_file():
                styles.write_card(p, sid, self.ask)
            if not styles.translations_of(p, sid):
                styles.write_translations(p, sid, self.ask)
            if not (styles.sdir(p, sid) / "lookdev.json").is_file():
                styles.write_lookdev(p, sid)
            ld = styles.lookdev_status(p, sid)
            if ld["rendered"] < ld["rows"]:
                todo.append(partial(self.gpu, ld["set"], f"image_{self.image_model}", 1, ld["rows"], "all_images.csv", {}))
        if todo:
            self.say(f"Rendering the look development of {len(todo)} style(s)")
            self._parallel(todo)
        for s in st["styles"]:                                  # the producer takes the first rendered variant of each sheet
            for it in styles.lookdev_status(p, s["id"])["items"]:
                if it["pick"] is None:
                    c = next((c for c in it["candidates"] if c["image"]), None)
                    if c:
                        styles.pick(p, s["id"], it["key"], c["row"])
        gates.approve(p, "lookdev", styles.gate_data(p))

    def _render_pictures(self, sid: str) -> None:
        st = pictures.status(self.pdir, sid)
        missing = [x["row"] for x in st["shots"] if not x["image"]]
        if missing:
            self.gpu(st["set"], f"image_{self.image_model}", min(missing), max(missing), "all_images.csv", {})

    def _approve_pictures(self, sid: str) -> None:
        for x in pictures.status(self.pdir, sid)["shots"]:
            if x["image"] and not x["approved"]:
                pictures.approve(self.pdir, sid, x["row"])

    def pictures(self, st: dict) -> None:
        p, master = self.pdir, st["master"]
        if not pictures.status(p, master)["shots"]:
            pictures.write_prompts(p, master)
        self.say("Rendering the master style's pictures")
        self._render_pictures(master)
        self._approve_pictures(master)
        if not gates.approved(p, pictures.gate_step(p, master), pictures.gate_data(p, master)):
            if "pictures" in self.stop_at:
                raise Waiting("Waiting for your review at the pictures. Approve them, then press Make my film again to carry on.")
            pictures.approve_all_ready(p, master)
            self.moment("master pictures")
        others = [s["id"] for s in st["styles"] if s["id"] != master]
        for sid in others:
            if not pictures.status(p, sid)["shots"]:
                pictures.write_prompts(p, sid)
        if others:
            self.say(f"Rendering {len(others)} more style(s) from the master pictures")
            self._parallel([partial(self._render_pictures, sid) for sid in others])
        for sid in others:
            for _ in range(consistency.MAX_TRIES):
                if self.ask_image is None:
                    break
                r = consistency.run(p, sid, self.ask_image, self._say)
                if not r["again"]:
                    break
                self._render_pictures(sid)
            self._approve_pictures(sid)
            if not gates.approved(p, pictures.gate_step(p, sid), pictures.gate_data(p, sid)):
                pictures.approve_all_ready(p, sid)

    def sound(self) -> None:
        p = self.pdir
        if not sound_design.load(p):
            sound_design.write_plan(p, self.ask, self._say)
        if not gates.approved(p, "sound", sound_design.gate_data(p)):
            gates.approve(p, "sound", sound_design.gate_data(p))
            self.moment("sound")
        if self.audio is not None:
            self.audio("kokoro")

    def film(self, st: dict) -> list[str]:
        p = self.pdir
        if not clips.load_motion(p):
            clips.write_motion(p, self.ask, self._say)
        todo: list[Callable[[], object]] = []
        for s in st["styles"]:
            made = clips.prepare(p, s["id"])
            missing = [c["row"] for c in clips.status(p, s["id"])["clips"] if not c["clip"]]
            if missing:
                todo.append(partial(self.gpu, made["set"], self.video_model, min(missing), max(missing), "all_shots.csv", {"KEYFRAME_MODEL": clips.KEYFRAMES}))
        if todo:
            self.say(f"Making the clips of {len(todo)} style(s)")
            self._parallel(todo)
        out = []
        for s in st["styles"]:
            for c in clips.status(p, s["id"])["clips"]:
                if c["clip"] and not c["approved"]:
                    clips.review(p, s["id"], c["row"], approved=True)
            if not gates.approved(p, clips.gate_step(p, s["id"]), clips.gate_data(p, s["id"])):
                clips.approve_all(p, s["id"])
            if "film" in st["products"]:
                out.append(render_cut.render(p, s["id"], "film").name)
        return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("project")
    ap.add_argument("--stop-at", default="")
    ap.add_argument("--engine", default="claude", choices=["claude", "fcc-claude", "codex", "fcc-codex", "hf", "local", "fake"])
    ap.add_argument("--model", default=None)
    ap.add_argument("--service", default="kaggle", choices=list(LIMITS))
    ap.add_argument("--gpu", default="NvidiaTeslaT4")
    ap.add_argument("--kaggle-user", default="")
    ap.add_argument("--image-model", default="flux2_klein_4b")
    ap.add_argument("--video-model", default="ltx_video_fast_i2v")
    ap.add_argument("--confirm-spend", action="store_true")
    a = ap.parse_args(argv)
    stops = [x for x in a.stop_at.split(",") if x]
    if any(x not in STOPS for x in stops):
        print(f"--stop-at is some of {', '.join(STOPS)}", flush=True)
        return 1
    pdir = layout.project_dir(a.project, "book")
    if not pdir.is_dir():
        print(f"no book called {a.project}", flush=True)
        return 1
    if a.engine == "fake":
        text_ask, image_ask = read_it_in.fake_ask(pdir), consistency.fake_ask()

        def ask(prompt, roles, step, validate):
            for fake in (read_it_in.fake_ask(pdir), continuity_book.fake_ask(pdir), shot_list.fake_ask(pdir), styles.fake_ask(pdir), sound_design.fake_ask(pdir),
                         clips.fake_ask(), marketing.fake_ask()):
                try:
                    return fake(prompt, roles, step, validate)
                except (ValueError, KeyError, IndexError, read_it_in.ReadError):
                    continue
            return text_ask(prompt, roles, step, validate)
    else:
        import bookkit

        def ask(prompt, roles, step, validate):
            return bookkit.llm_json(prompt, crew.system(roles, pdir, step), model=a.model, engine=a.engine, validate=validate)

        def image_ask(prompt, roles, step, validate, image):
            return bookkit.llm_json(prompt, crew.system(roles, pdir, step), model=a.model, engine=a.engine, validate=validate, image=image)
    def audio(kind: str) -> None:                              # narration (kokoro) or the audiobook, read aloud on this computer
        from studio_app.config import ROOT
        from studio_app.generation import local_audio_step
        from studio_app.steps import script_argv
        r = subprocess.run(script_argv(local_audio_step(pdir.name, kind)["argv"]), cwd=ROOT, env={**os.environ, "PYTHONUTF8": "1"}, check=False)
        if r.returncode != 0:
            raise RuntimeError(f"reading the {kind} aloud failed (exit {r.returncode})")
    try:
        Autopilot(pdir, ask, image_ask, runner_gpu(a.service, a.gpu, a.kaggle_user), stops, a.confirm_spend, a.service, a.image_model, a.video_model,
                  lambda t: print(t, flush=True), audio=None if a.engine == "fake" else audio).run()
    except Waiting as e:
        print(str(e), flush=True)
        return 0
    except Exception as e:  # noqa: BLE001  every step's own error is already a plain sentence; say it and stop, the work done so far is kept
        print(f"Autopilot stopped: {e}. Press Make my film again to carry on from here.", flush=True)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
