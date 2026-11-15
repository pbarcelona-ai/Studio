"""The guided flow (seven screens) and the provider groups, driven in jsdom; plus the /api/providers data."""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

from conftest import TOKEN
from studio_app.providers import providers_data

JS = Path(__file__).resolve().parent / "js"


def test_providers_are_grouped_and_paid_ones_are_unproven():
    d = providers_data()
    assert [p["id"] for p in d["computer"]] == ["computer"]
    assert {p["id"] for p in d["free"]} == {"kaggle", "colab", "huggingface"}
    assert all(p["proven"] and p["selectable"] for p in d["computer"] + d["free"])
    assert len(d["paid"]) >= 10
    assert all(not p["proven"] and not p["selectable"] and p["url"].startswith("https://") for p in d["paid"])
    assert len({p["id"] for p in d["paid"]}) == len(d["paid"])
    assert not {p["id"] for p in d["paid"]} & {p["id"] for p in d["free"] + d["computer"]}


def test_providers_route(server):
    import urllib.request
    r = urllib.request.urlopen(urllib.request.Request(f"http://127.0.0.1:{server.port}/api/providers", headers={"X-Studio-Token": TOKEN}))
    data = json.loads(r.read())
    assert set(data) == {"computer", "free", "paid"}


@pytest.mark.skipif(not shutil.which("node") or not (JS / "node_modules" / "jsdom").is_dir(), reason="node or jsdom is not installed (cd tests/js && npm install)")
def test_film_path_in_the_page(server, film):
    (film / "chapters").mkdir(exist_ok=True)
    for n in range(1, 7):
        (film / "chapters" / f"chapter-{n:03d}.txt").write_text("It was a long day and the story goes on.")
    r = subprocess.run(["node", "flow.js", f"http://127.0.0.1:{server.port}/?t={TOKEN}"], cwd=JS, capture_output=True, text=True, timeout=120)
    assert r.stdout.strip(), r.stderr[-600:]
    out = json.loads(r.stdout.strip().splitlines()[-1])
    assert out["errors"] == [], out
    assert out["steps"] == 16 and out["names"][0] == "Read the book" and out["names"][-1] == "Share your film" and out["flowOn"]
    assert out["orphans"] == [], "every card of the four main tabs must be in some step"
    assert out["locked"] == ["storyboard", "video", "audio", "cut", "premiere"], out["locked"]
    assert out["step1"]["title"] == "Read the book" and out["step1"]["shown"] == ["Read book"] and "Tools Status" in out["step1"]["more"]
    assert out["step1"]["buttons"] == ["Read the book"] and out["afterNext"] == "Check the chapters" and out["planStep"] == "plan"
    assert out["screenplayButtons"] == ["Write the screenplay", "Approve the screenplay"]
    assert out["kfTitle"] == "Make the pictures" and out["kfNextDisabled"] and "0 of 4" in out["kfTodo"] and out["kfPicker"]
    assert [[k for k, v in s.items() if v] for s in out["stillsRun"]] == [["keyframes"]]
    assert out["stillAt"] == "Make the pictures"                       # the next step's button is locked, so a click does nothing
    # the walk back after a storyboard change
    assert out["again"] == ["screenplay", "continuity", "cast", "look", "write", "build", "where", "keyframes", "storyboard"]
    assert out["lockedAfter"][0] == "continuity" and "storyboard" in out["alert"].lower()
    assert out["flagged"] == 1 and "red outline" in out["flagNote"] and out["approveDisabled"] and out["nextWhileFlagged"]
    assert out["flaggedAfterKeep"] == 0 and out["afterConfirm"] == "Make the story notes" and out["againAfter"][0] == "continuity"
    assert out["restored"] and out["backInFlow"]
    assert out["groups"][0].startswith("On this computer") and out["paid"] >= 10
