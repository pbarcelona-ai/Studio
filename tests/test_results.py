"""Get results: which Kaggle runs belong to a book and kind, what is already here, and the fetch steps for the rest (studio_app/results.py)."""
import subprocess
from pathlib import Path

import pytest

from studio_app import results as res
from studio_app.common import PlanError

ROOT = Path(__file__).resolve().parent.parent


def fit(name, tail):
    return subprocess.run(["bash", "-c", f'. "{ROOT}/scripts/kaggle_names.sh"; kaggle_fit "$0" "$1"', name, tail], capture_output=True, text=True, check=True).stdout


def test_tail_of_plain_cut_and_old_names():
    assert res.tail_of("demo-ltx-video-1-40", "demo") == "ltx-video-1-40"
    assert res.tail_of("old-demo-ltx-video-1-40", "demo") == "ltx-video-1-40"
    assert res.tail_of("other-ltx-video-1-40", "demo") is None
    long = "genesis_jasher_jubilees_adam_eve"
    for tail in ("-image-flux2-klein-4b-keyframes-1-40", "-image-flux2-klein-4b-keyframes-81-120", "-ltx-video-fast-i2v-1-12"):
        slug = fit(long.replace("_", "-"), tail)
        assert len(slug) <= 50 and res.tail_of(slug, long) == tail[1:]
    assert res.tail_of(fit("genesis-jasher-jubilees-adam-eve", "-ltx-video-1-4"), "genesis_other_book") is None


def test_kind_of():
    assert res.kind_of("image-flux2-klein-4b-keyframes-81-120") == ("keyframes", "flux2_klein_4b", "-keyframes", 81, 120)
    assert res.kind_of("image-sdxl-1-4") == ("image", "sdxl", "", 1, 4)
    assert res.kind_of("audio-kokoro-chapters-1-3") == ("audio", "kokoro", "-chapters", 1, 3)
    assert res.kind_of("ltx-video-fast-i2v-1-12") == ("video", "ltx_video_fast_i2v", "", 1, 12)
    assert res.kind_of("no-rows") is None


@pytest.fixture()
def kaggle(monkeypatch, book):
    runs = [{"ref": "pat/demo-image-flux-keyframes-1-4", "slug": "demo-image-flux-keyframes-1-4", "last_run": "2026-11-14"},
            {"ref": "pat/demo-ltx-video-1-4", "slug": "demo-ltx-video-1-4", "last_run": ""},
            {"ref": "pat/demo-audio-kokoro-1-4", "slug": "demo-audio-kokoro-1-4", "last_run": ""},
            {"ref": "pat/other-ltx-video-1-4", "slug": "other-ltx-video-1-4", "last_run": ""}]
    status = {"pat/demo-image-flux-keyframes-1-4": "COMPLETE", "pat/demo-ltx-video-1-4": "RUNNING", "pat/demo-audio-kokoro-1-4": "COMPLETE"}
    monkeypatch.setattr(res.shutil, "which", lambda *a, **k: "/usr/bin/kaggle")
    monkeypatch.setattr(res, "kaggle_runs", lambda limit, with_status: runs)
    monkeypatch.setattr(res, "kaggle_status_of", lambda kg, ref: status[ref])
    return book


def test_results_know_what_is_here(kaggle):
    kf = kaggle / "images" / "flux_keyframes"
    kf.mkdir(parents=True)
    (kf / "image-0001.png").write_text("p")
    au = kaggle / "audio" / "kokoro"
    au.mkdir(parents=True)
    for n in range(1, 5):
        (au / f"narration-{n:04d}.wav").write_text("w")
    d = res.results_data("demo", "any")
    by = {r["kind"]: r for r in d["runs"]}
    assert set(by) == {"keyframes", "video", "audio"} and by["keyframes"]["have"] == 1 and by["keyframes"]["needs"]
    assert by["audio"]["have"] == 4 and not by["audio"]["needs"] and by["video"]["needs"] and by["video"]["status"] == "RUNNING"
    assert [r["kind"] for r in res.results_data("demo", "keyframes")["runs"]] == ["keyframes"]


def test_steps_fetch_finished_runs_and_wait_for_running_ones(kaggle):
    au = kaggle / "audio" / "kokoro"
    au.mkdir(parents=True)
    for n in range(1, 5):
        (au / f"narration-{n:04d}.wav").write_text("w")           # the sound is all here already
    steps, opt = res.results_steps({"project": "demo", "kind": "any"})
    argvs = [s["argv"] for s in steps]
    assert argvs == [["scripts/fetch_kaggle_run.sh", "demo-image-flux-keyframes-1-4", "--project", "demo"],
                     ["scripts/fetch_kaggle_run.sh", "demo-ltx-video-1-4", "--wait", "--project", "demo"]]
    assert opt["queue"] and opt["keep_going"]
    with pytest.raises(PlanError, match="Nothing to get"):
        res.results_steps({"project": "demo", "kind": "audio"})


def test_checks(kaggle, monkeypatch):
    with pytest.raises(PlanError, match="kind"):
        res.results_data("demo", "nope")
    with pytest.raises(PlanError, match="pick a book"):
        res.results_data("../x", "any")
    monkeypatch.setattr(res.shutil, "which", lambda *a, **k: None)
    assert res.results_data("demo", "any") == {"runs": [], "kaggle": False}
    with pytest.raises(PlanError, match="not installed"):
        res.results_steps({"project": "demo", "kind": "any"})


def test_routes(server, kaggle, monkeypatch):
    from studio_app.jobs import JOB
    started = []
    monkeypatch.setattr(JOB, "start", lambda steps, opt, queue=False: started.append((steps, queue)) or 0)
    status, data = server.api("GET", "/api/results?project=demo&kind=keyframes")
    assert status == 200 and data["runs"][0]["slug"] == "demo-image-flux-keyframes-1-4"
    status, data = server.api("POST", "/api/get_results", {"project": "demo", "kind": "keyframes"})
    assert status == 200 and data["runs"] == ["Fetch results of demo-image-flux-keyframes-1-4"] and started[0][1] is True
