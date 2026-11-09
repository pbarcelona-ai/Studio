"""regress_kaggle.py: the regression runner, with the Kaggle script stubbed out."""
import json
import os
import subprocess
import sys

import pytest

import regress_kaggle as rk


@pytest.fixture()
def rig(tmp_path, monkeypatch):
    monkeypatch.setattr(rk, "ROOT", tmp_path)
    monkeypatch.setattr(rk, "REPORT", tmp_path / "regression_kaggle_report.json")
    monkeypatch.setattr(rk, "STEPS_CAP", 0)
    rk.stop.clear()
    plans = []

    def plan(opt, run):
        plans.append((opt, run))
        return [{"argv": ["scripts/run_kaggle_model.sh", opt["model"], "1", "1"], "env": {"PROJECT": opt["set"]}, "label": f"push {opt['model']}"}]
    monkeypatch.setattr(rk.S, "prompt_plan", plan)
    return tmp_path, plans


def picture(path, noisy=True):
    from PIL import Image, PngImagePlugin
    path.parent.mkdir(parents=True, exist_ok=True)
    info = PngImagePlugin.PngInfo()
    info.add_text("padding", "x" * 30000)                  # a flat picture compresses to nothing: pad it so only its flatness fails
    Image.frombytes("L", (200, 200), os.urandom(40000) if noisy else b"\x80" * 40000).save(path, pnginfo=info)


def fake_kaggle(tmp_path, kind="image", complete=True, make_file=True, hang=False):
    """A stand-in for run_kaggle_model.sh: writes the log, and the output the real run would download."""
    def run(argv, cwd=None, env=None, stdout=None, stderr=None, timeout=None):
        if hang:
            raise subprocess.TimeoutExpired(argv, timeout)
        stdout.write("log line\n" + ("== kernel completed\n" if complete else "ERROR: OutOfMemory while sampling\n"))
        stdout.flush()
        if make_file:
            lane = env["PROJECT"]
            if kind == "image":
                picture(tmp_path / "projects" / "regression" / lane / "images" / argv[1] / "image-0001.png")
            elif kind == "video":
                p = tmp_path / "projects" / "regression" / lane / "videos" / argv[1]
                p.mkdir(parents=True, exist_ok=True)
                (p / "shot-0001.mp4").write_bytes(b"v" * 30000)
            else:
                p = tmp_path / "projects" / "regression" / lane / "audio" / rk.AUDIO[argv[1]]
                p.mkdir(parents=True, exist_ok=True)
                (p / "a.wav").write_bytes(b"w" * 30000)
    return run


class TestHelpers:
    def test_read_prompt_prefers_the_file(self, rig):
        tmp, _ = rig
        assert rk.read_prompt() == rk.DEFAULT_PROMPT
        (tmp / "regression_prompt.txt").write_text("  a  dragon \n over  a lake ")
        assert rk.read_prompt() == "a dragon over a lake"
        (tmp / "regression_prompt.txt").write_text("   ")
        assert rk.read_prompt() == rk.DEFAULT_PROMPT

    def test_model_list_leaves_out_tpu_and_keyframe_models(self):
        models = rk.all_models()
        assert models and {k for k, _ in models} == {"image", "video", "audio"}
        assert not [m for _, m in models if m.startswith("tpu_") or m in rk.S.I2V_MODELS]
        assert [k for k, _ in models][0] == "image"

    def test_make_opt_caps_steps_unless_locked(self, rig, monkeypatch):
        monkeypatch.setitem(rk.S.MODEL_DEFAULTS, "zz", {"steps": 30})
        monkeypatch.setitem(rk.S.MODEL_DEFAULTS, "zl", {"steps": 30, "locked": ["steps"]})
        assert rk.make_opt("image", "zz", "a", "me", "T4")["opts"]["steps"] == "30" and rk.make_opt("image", "zl", "a", "me", "T4")["opts"] == {"variations": 1}
        monkeypatch.setattr(rk, "STEPS_CAP", 6)
        o = rk.make_opt("image", "zz", "b", "me", "T4")
        assert o["opts"]["steps"] == "6" and o["set"] == "regtest_b" and o["kaggle_user"] == "me" and o["service"] == "kaggle"

    def test_audio_csv_uses_the_test_prompt_everywhere(self, rig):
        tmp, _ = rig
        rk.audio_csv("a")
        import csv
        row = list(csv.DictReader(open(tmp / "projects" / "regression" / "regtest_a" / "audio_shots.csv")))[0]
        assert row["narration"] == row["sfx"] == row["music"] == rk.TEST_PROMPT

    def test_judge(self, rig):
        tmp, _ = rig
        assert rk.judge([], "image") == (False, "no output file")
        small = tmp / "s.png"
        small.write_bytes(b"x")
        assert "only 1 bytes" in rk.judge([small], "image")[1]
        flat, noisy = tmp / "flat.png", tmp / "noisy.png"
        picture(flat, noisy=False)
        picture(noisy)
        assert rk.judge([flat], "image") == (False, "flat.png is a flat picture") and rk.judge([noisy], "image")[0]
        clip = tmp / "c.mp4"
        clip.write_bytes(b"v" * 30000)
        assert rk.judge([clip], "video")[0]

    def test_report_files_are_written_in_two_formats(self, rig):
        tmp, _ = rig
        rk.save_report({"m": {"kind": "image", "result": "PASS", "minutes": 3, "note": "ok"}})
        assert rk.load_report()["m"]["result"] == "PASS" and "| m | image | PASS | 3 | ok |" in (tmp / "regression_kaggle_report.md").read_text()
        (rk.REPORT).write_text("{broken")
        assert rk.load_report() == {}


class TestRunOne:
    @pytest.mark.parametrize("kind,model", [("image", "flux1_schnell"), ("video", "ltx_video"), ("audio", "audio_kokoro")])
    def test_pass(self, rig, monkeypatch, kind, model):
        tmp, _ = rig
        monkeypatch.setattr(rk.subprocess, "run", fake_kaggle(tmp, kind))
        if kind == "audio":
            model = next(m for k, m in rk.all_models() if k == "audio")
        monkeypatch.setattr(rk.S, "clean_env", lambda: {})
        r = rk.run_one(kind, model, "a", "me", "T4", 5)
        assert r["result"] == "PASS" and r["kind"] == kind and r["log"].endswith(f"regress_{model}.txt")

    def test_a_kernel_that_did_not_complete_fails_with_the_error_line(self, rig, monkeypatch):
        tmp, _ = rig
        monkeypatch.setattr(rk.subprocess, "run", fake_kaggle(tmp, "image", complete=False, make_file=False))
        r = rk.run_one("image", "flux1_schnell", "a", "me", "T4", 5)
        assert r["result"] == "FAIL" and "kernel did not complete" in r["note"] and "no output file" in r["note"] and "OutOfMemory" in r["note"]

    def test_old_files_do_not_count(self, rig, monkeypatch):
        tmp, _ = rig
        picture(tmp / "projects" / "regression" / "regtest_a" / "images" / "flux1_schnell" / "image-0001.png")
        monkeypatch.setattr(rk.subprocess, "run", fake_kaggle(tmp, make_file=False))
        assert rk.run_one("image", "flux1_schnell", "a", "me", "T4", 5)["result"] == "FAIL"

    def test_timeout(self, rig, monkeypatch):
        tmp, _ = rig
        monkeypatch.setattr(rk.subprocess, "run", fake_kaggle(tmp, hang=True))
        r = rk.run_one("image", "flux1_schnell", "a", "me", "T4", 5)
        assert r["result"] == "TIMEOUT" and "no result after 5 min" in r["note"]


class TestMain:
    def run(self, monkeypatch, *argv):
        monkeypatch.setattr(sys, "argv", ["regress_kaggle.py", *argv])
        with pytest.raises(SystemExit) as e:
            rk.main()
            raise SystemExit(0)
        return e.value.code

    def test_list_and_argument_errors(self, rig, monkeypatch, capsys):
        assert self.run(monkeypatch, "--list") == 0 and "image" in capsys.readouterr().out
        assert self.run(monkeypatch) == 2
        assert "--kinds takes" in self.run(monkeypatch, "--user", "me", "--kinds", "film")
        assert "unknown model(s): nope" in self.run(monkeypatch, "--user", "me", "--only", "nope")

    def test_dry_run_shows_the_plan_and_pushes_nothing(self, rig, monkeypatch, capsys):
        _, plans = rig
        assert self.run(monkeypatch, "--user", "me", "--only", "flux1_schnell,audio_kokoro", "--dry-run") == 0
        out = capsys.readouterr().out
        assert "2 model(s) to test" in out and "flux1_schnell: push flux1_schnell" in out and "audio row 1" in out and plans == [(plans[0][0], False)]

    def test_dry_run_reports_a_refusal(self, rig, monkeypatch, capsys):
        def refuse(opt, run):
            raise rk.S.PlanError("no such model")
        monkeypatch.setattr(rk.S, "prompt_plan", refuse)
        self.run(monkeypatch, "--user", "me", "--only", "flux1_schnell", "--dry-run")
        assert "REFUSED by the planner: no such model" in capsys.readouterr().out

    def test_a_pass_is_remembered_and_skipped_next_time(self, rig, monkeypatch, capsys):
        tmp, plans = rig
        monkeypatch.setattr(rk.subprocess, "run", fake_kaggle(tmp))
        assert self.run(monkeypatch, "--user", "me", "--only", "flux1_schnell") == 0
        assert json.loads(rk.REPORT.read_text())["flux1_schnell"]["result"] == "PASS" and "1 passed" in capsys.readouterr().out
        calls = len(plans)
        self.run(monkeypatch, "--user", "me", "--only", "flux1_schnell")
        assert len(plans) == calls                                      # skipped
        self.run(monkeypatch, "--user", "me", "--only", "flux1_schnell", "--again")
        assert len(plans) == calls + 1

    def test_a_pass_for_another_prompt_does_not_count(self, rig, monkeypatch):
        tmp, plans = rig
        rk.save_report({"flux1_schnell": {"kind": "image", "result": "PASS", "prompt": "an older prompt"}})
        monkeypatch.setattr(rk.subprocess, "run", fake_kaggle(tmp))
        self.run(monkeypatch, "--user", "me", "--only", "flux1_schnell")
        assert len(plans) == 1

    def test_stops_at_the_first_failure_and_shows_the_log_unless_keep_going(self, rig, monkeypatch, capsys):
        tmp, _ = rig
        monkeypatch.setattr(rk.subprocess, "run", fake_kaggle(tmp, complete=False, make_file=False))
        assert self.run(monkeypatch, "--user", "me", "--only", "flux1_schnell,sdxl_turbo") == 1
        out = capsys.readouterr().out
        assert "STOPPED at" in out and "end of the log" in out and "OutOfMemory" in out and out.count("START") == 1
        rk.stop.clear()
        assert self.run(monkeypatch, "--user", "me", "--only", "flux1_schnell,sdxl_turbo", "--keep-going") == 1
        assert capsys.readouterr().out.count("START") == 2

    def test_a_crash_in_one_model_is_recorded_and_two_lanes_work(self, rig, monkeypatch, capsys):
        tmp, _ = rig

        def boom(argv, **kw):
            raise OSError("no such script")
        monkeypatch.setattr(rk.subprocess, "run", boom)
        assert self.run(monkeypatch, "--user", "me", "--only", "flux1_schnell,sdxl_turbo", "--lanes", "2", "--keep-going") == 1
        rep = json.loads(rk.REPORT.read_text())
        assert {v["result"] for v in rep.values()} == {"ERROR"} and "OSError: no such script" in rep["flux1_schnell"]["note"]

    def test_planner_refusal_is_recorded(self, rig, monkeypatch):
        def refuse(opt, run):
            raise rk.S.PlanError("not allowed")
        monkeypatch.setattr(rk.S, "prompt_plan", refuse)
        self.run(monkeypatch, "--user", "me", "--only", "flux1_schnell", "--keep-going")
        assert json.loads(rk.REPORT.read_text())["flux1_schnell"]["result"] == "REFUSED"
