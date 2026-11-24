"""The guided flow (seven screens) and the provider groups, driven in jsdom; plus the /api/providers data."""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

from conftest import TOKEN
from studio_app.providers import providers_data

JS = Path(__file__).resolve().parent / "js"


def test_providers_are_grouped_and_paid_ones_are_unproven(monkeypatch):
    monkeypatch.delenv("STUDIO_LEGACY_CLOUD", raising=False)
    gated = providers_data()
    assert [p["id"] for p in gated["computer"]] == ["computer"]
    assert gated["free"] == [] and gated["paid"] == []
    assert gated["legacy_cloud"] is False
    assert isinstance(gated["gpu_profile"], dict) and "tier" in gated["gpu_profile"]

    monkeypatch.setenv("STUDIO_LEGACY_CLOUD", "1")
    d = providers_data()
    assert [p["id"] for p in d["computer"]] == ["computer"]
    assert {p["id"] for p in d["free"]} == {"kaggle", "colab", "huggingface"}
    assert all(p["proven"] and p["selectable"] for p in d["computer"] + d["free"])
    assert len(d["paid"]) >= 10
    assert all(not p["proven"] and not p["selectable"] and p["url"].startswith("https://") for p in d["paid"])
    assert len({p["id"] for p in d["paid"]}) == len(d["paid"])
    assert not {p["id"] for p in d["paid"]} & {p["id"] for p in d["free"] + d["computer"]}
    assert d["legacy_cloud"] is True


def test_providers_route(server, monkeypatch):
    import urllib.request
    monkeypatch.delenv("STUDIO_LEGACY_CLOUD", raising=False)
    r = urllib.request.urlopen(urllib.request.Request(f"http://127.0.0.1:{server.port}/api/providers", headers={"X-Studio-Token": TOKEN}))
    data = json.loads(r.read())
    assert set(data) == {"computer", "free", "paid", "legacy_cloud", "gpu_profile"}
    assert data["free"] == [] and data["paid"] == [] and data["legacy_cloud"] is False

    monkeypatch.setenv("STUDIO_LEGACY_CLOUD", "1")
    r2 = urllib.request.urlopen(urllib.request.Request(f"http://127.0.0.1:{server.port}/api/providers", headers={"X-Studio-Token": TOKEN}))
    data2 = json.loads(r2.read())
    assert data2["legacy_cloud"] is True
    assert {p["id"] for p in data2["free"]} == {"kaggle", "colab", "huggingface"}
    assert len(data2["paid"]) >= 10


def test_status_legacy_cloud_gating(server, monkeypatch):
    monkeypatch.delenv("STUDIO_LEGACY_CLOUD", raising=False)
    code, st = server.api("GET", "/api/status")
    assert code == 200
    assert st["legacy_cloud"] is False
    assert isinstance(st["gpu_profile"], dict) and "ram_gb" in st["gpu_profile"]
    assert set(st["gpus"]) == {"computer"}
    assert not ({"kaggle", "colab", "huggingface", "cloud_api"} & set(st["gpus"]))
    assert not ({"kaggle", "colab", "huggingface", "cloud_api"} & set(st["gpu_blockers"]))
    assert not ({"kaggle", "colab", "hf", "huggingface"} & set(st["tools"]))

    monkeypatch.setenv("STUDIO_LEGACY_CLOUD", "1")
    code2, st2 = server.api("GET", "/api/status")
    assert code2 == 200
    assert st2["legacy_cloud"] is True
    assert {"computer", "kaggle", "colab", "huggingface", "cloud_api"} <= set(st2["gpus"])
    assert {"kaggle", "colab", "hf", "huggingface"} <= set(st2["tools"])


@pytest.mark.skipif(not shutil.which("node") or not (JS / "node_modules" / "jsdom").is_dir(), reason="node or jsdom is not installed (cd tests/js && npm install)")
def test_film_path_in_the_page(server, film, monkeypatch):
    monkeypatch.setenv("STUDIO_LEGACY_CLOUD", "1")
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
    assert out["step1"]["title"] == "Read the book" and out["step1"]["shown"] == ["Read book", "Add your sources", "Your footage and music"] and "Tools Status" in out["step1"]["more"]
    assert out["firstBook"] == ["", "Pick one…"], "the book list starts with a Pick one line"
    assert out["startOver"] == {"open": True, "underPath": True}, "Start over on the first step opens its keep-choices there"
    assert out["step1"]["buttons"] == ["Read the book", "Start over…"] and out["afterNext"] == "Check the chapters" and out["planStep"] == "plan"
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


@pytest.mark.skipif(not shutil.which("node") or not (JS / "node_modules" / "jsdom").is_dir(), reason="node or jsdom is not installed (cd tests/js && npm install)")
def test_core_fill_gpus_handles_null_st():
    root = JS.parent.parent
    script = r"""
const fs = require("fs");
const path = require("path");
const { JSDOM } = require("jsdom");
const root = process.argv[1];
const html = fs.readFileSync(path.join(root, "web", "index.html"), "utf8");
const coreJs = fs.readFileSync(path.join(root, "web", "static", "js", "core.js"), "utf8");
const dom = new JSDOM(html, { url: "http://127.0.0.1:8775/", runScripts: "dangerously" });
const errors = [];
dom.window.addEventListener("error", e => errors.push(String(e.error || e.message)));
const sc = dom.window.document.createElement("script");
sc.textContent = coreJs;
dom.window.document.head.appendChild(sc);
// ST starts null: fillGpus() must return cleanly without throwing
dom.window.eval("fillGpus()");
const compRadio = dom.window.document.querySelector('input[name="svc"][value="computer"]');
const kagRadio = dom.window.document.querySelector('input[name="svc"][value="kaggle"]');
if (compRadio) {
  compRadio.checked = true;
  compRadio.dispatchEvent(new dom.window.Event("change", { bubbles: true }));
}
dom.window.eval("fillGpus()");
if (kagRadio) kagRadio.checked = true;
// Once ST is populated in gated mode, fillGpus() switches svc to computer and populates #gpu
const sc2 = dom.window.document.createElement("script");
sc2.textContent = `
  ST = {
    gpus: { computer: [["local", "Apple M2 (8 GB)"]] },
    gpu_blockers: { computer: {} },
    auto_cleanup: true,
    legacy_cloud: false
  };
  fillGpus();
`;
dom.window.document.head.appendChild(sc2);
const svcChecked = (dom.window.document.querySelector('input[name="svc"]:checked') || {}).value;
const gpuVal = dom.window.document.getElementById("gpu").value;
console.log(JSON.stringify({ errors, svcChecked, gpuVal }));
"""
    r = subprocess.run(["node", "-e", script, str(root)], cwd=JS, capture_output=True, text=True, timeout=30)
    assert r.returncode == 0, r.stderr
    out = json.loads(r.stdout.strip().splitlines()[-1])
    assert out["errors"] == []
    assert out["svcChecked"] == "computer"
    assert out["gpuVal"] == "local"
