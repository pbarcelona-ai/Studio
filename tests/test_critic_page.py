"""The critic's findings on the Storyboard card can be acted on: show the shot, edit its prompt, reject it, dismiss the finding."""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

from conftest import TOKEN, write_csv
from studio_app.projects import read_csv_rows

JS = Path(__file__).resolve().parent / "js"


@pytest.mark.skipif(not shutil.which("node") or not (JS / "node_modules" / "jsdom").is_dir(), reason="node or jsdom is not installed (cd tests/js && npm install)")
def test_critic_findings_have_buttons_that_work(server, book):
    (book / "chapters").mkdir(exist_ok=True)
    (book / "chapters" / "chapter-001.txt").write_text("It was a long day and the story goes on.")
    audio = read_csv_rows(book / "audio_shots.csv")
    audio[1]["narration"] = " ".join(["word"] * 60)                    # far longer than a 4 s clip: a serious pacing finding on shot 2
    write_csv(book / "audio_shots.csv", audio)
    r = subprocess.run(["node", "critic.js", f"http://127.0.0.1:{server.port}/?t={TOKEN}"], cwd=JS, capture_output=True, text=True, timeout=90)
    assert r.stdout.strip(), r.stderr[-600:]
    out = json.loads(r.stdout.strip().splitlines()[-1])
    assert out["errors"] == [], out
    assert "edit:2" in out["buttons"] and "show:2" in out["buttons"] and "reject:2" in out["buttons"] and "dismiss:2" in out["buttons"]
    assert out["layout"] and set(out["layout"]) == {"crit-msg|crit-ctl/7"}, out["layout"]                  # every finding: 7 controls in the same columns
    assert "object" not in out["status"] and " shots" in out["status"], out["status"]
    assert out["cardShown"] and out["editorOpen"] and out["afterSave"].startswith("Shot 2 saved")
    assert out["verdict"] == "rejected" and out["dismissed"] == 1
    assert read_csv_rows(book / "all_shots.csv")[1]["prompt"] == "a brand new prompt for the shot"
