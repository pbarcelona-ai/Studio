"""Kaggle runs, status, fetch and the clean-up that deletes notebooks - against a fake `kaggle` program (no network)."""
from types import SimpleNamespace

import pytest

from studio_app import kaggle_cleanup as kc
from studio_app import kaggle_runs as kr
from studio_app.common import PlanError

HEADER = "ref,title,totalVotes,lastRunTime\n"


class FakeKaggle:
    def __init__(self):
        self.calls = []
        self.listing = []                 # (slug, lastRunTime)
        self.status = {}                  # slug -> status word
        self.delete_fails = set()

    def run(self, argv, **kw):
        self.calls.append(argv[1:])
        cmd = argv[1:3]
        if cmd == ["kernels", "list"]:
            body = "".join(f"pat/{s},t,0,{t}\n" for s, t in self.listing)
            return SimpleNamespace(returncode=0, stdout="Warning: something\n" + HEADER + body, stderr="")
        if cmd == ["kernels", "status"]:
            slug = argv[3].split("/")[-1]
            return SimpleNamespace(returncode=0, stdout=f'{argv[3]} has status "KernelWorkerStatus.{self.status.get(slug, "COMPLETE")}"', stderr="")
        if cmd == ["kernels", "delete"]:
            slug = argv[4].split("/")[-1]
            return SimpleNamespace(returncode=1 if slug in self.delete_fails else 0, stdout="", stderr="boom" if slug in self.delete_fails else "")
        if cmd == ["kernels", "output"]:
            return SimpleNamespace(returncode=0, stdout="downloaded", stderr="")
        raise AssertionError(argv)


@pytest.fixture()
def kaggle(book, monkeypatch, tmp_path):
    fake = FakeKaggle()
    for mod in (kr, kc):
        monkeypatch.setattr(mod.subprocess, "run", fake.run) if mod is kr else None
    monkeypatch.setattr(kr.shutil, "which", lambda *a, **k: "/usr/bin/kaggle")
    monkeypatch.setattr(kc, "STATUS_PAUSE", 0, raising=False)
    monkeypatch.setattr(kc.time, "sleep", lambda s: None)
    monkeypatch.setattr(kc, "AUTO_CLEAN_OFF", tmp_path / "home" / "off")
    monkeypatch.setattr(kc.JOB, "running", False)
    return fake


def slug(model, lo, hi):
    return f"demo-{model}-{lo}-{hi}"


class TestRuns:
    def test_lists_only_this_tools_notebooks_with_status_and_project(self, kaggle):
        kaggle.listing = [(slug("ltx-video", 1, 4), "2026-11-02 10:00:00"), ("someone-elses-notebook", "2026-11-01 10:00:00")]
        runs = kr.kaggle_runs()
        assert [r["slug"] for r in runs] == [slug("ltx-video", 1, 4)]
        assert runs[0]["status"] == "COMPLETE" and runs[0]["project"] == "demo" and runs[0]["last_run"] == "2026-11-02 10:00"

    def test_without_status_asks_nothing_more(self, kaggle):
        kaggle.listing = [(slug("ltx-video", 1, 4), "2026-11-02 10:00:00")]
        assert kr.kaggle_runs(with_status=False)[0]["status"] == ""
        assert all(c[:2] != ["kernels", "status"] for c in kaggle.calls)

    def test_error_and_missing_program(self, kaggle, monkeypatch):
        monkeypatch.setattr(kr.shutil, "which", lambda *a, **k: None)
        with pytest.raises(PlanError, match="not installed"):
            kr.kaggle_runs()

    def test_guess_project_prefers_the_longest_name(self, kaggle, book, fake_root):
        (fake_root / "projects" / "books" / "demo_two").mkdir()
        assert kr.guess_project("demo-two-ltx-video-1-4") == "demo_two" and kr.guess_project("demo-ltx-video-1-4") == "demo"
        assert kr.guess_project("unrelated-name") == ""

    def test_kernel_ref_is_validated_because_it_goes_on_a_command_line(self):
        assert kr.kernel_ref(" pat/demo-ltx-video-1-4 ") == "pat/demo-ltx-video-1-4"
        for bad in ("", "no-slash", "a/b c", "../x/y", "pat/UPPER", "pat/x;rm -rf"):
            with pytest.raises(PlanError):
                kr.kernel_ref(bad)

    def test_status_and_output(self, kaggle, fake_root):
        assert kr.kernel_status("pat/demo-x-1-2")["status"] == "COMPLETE"
        out = kr.kernel_output("pat/demo-x-1-2")
        assert out["ok"] and out["dir"] == "my_downloads/demo-x-1-2"

    def test_fetch_step(self, kaggle, book):
        s = kr.fetch_step({"slug": "demo-ltx-video-1-4", "wait": True, "project": "demo"})
        assert s["argv"] == ["scripts/fetch_kaggle_run.sh", "demo-ltx-video-1-4", "--wait", "--project", "demo"] and s["ok_codes"] == (0, 2)
        for bad in ({"slug": "Bad Name"}, {"slug": "demo-ltx-video-1-4", "project": "ghost"}):
            with pytest.raises(PlanError):
                kr.fetch_step(bad)


class TestCleanup:
    def setup_runs(self, kaggle, n=6):
        kaggle.listing = [(slug("ltx-video", i, i), f"2999-01-0{i} 10:00:00") for i in range(1, n + 1)]  # far future: only the run overridden to year 2000 is "old"

    def test_scan_keeps_the_newest_three_and_never_lists_busy_ones_for_deletion(self, kaggle):
        self.setup_runs(kaggle)
        kaggle.status[slug("ltx-video", 2, 2)] = "RUNNING"
        scan = kc.kaggle_cleanup_scan()
        assert [r["slug"][-3:] for r in scan["keep"]] == ["6-6", "5-5", "4-4"]
        assert [r["slug"][-3:] for r in scan["remove"]] == ["3-3", "1-1"] and [r["slug"][-3:] for r in scan["busy"]] == ["2-2"]

    def test_delete_uses_the_servers_own_scan_and_reports_failures(self, kaggle):
        self.setup_runs(kaggle)
        kaggle.delete_fails.add(slug("ltx-video", 1, 1))
        res = kc.kaggle_cleanup_delete()
        assert res["deleted"] == ["pat/" + slug("ltx-video", 3, 3), "pat/" + slug("ltx-video", 2, 2)] and res["failed"][0]["error"] == "boom"

    def test_delete_refused_while_a_job_runs(self, kaggle, monkeypatch):
        monkeypatch.setattr(kc.JOB, "running", True)
        with pytest.raises(PlanError, match="a job is running"):
            kc.kaggle_cleanup_delete()

    def test_results_here_needs_every_row(self, kaggle, book):
        folder = book / "videos" / "ltx_video"
        folder.mkdir(parents=True)
        (folder / "shot-0001.mp4").write_bytes(b"x")
        assert not kc.run_results_here("demo-ltx-video-1-2")
        (folder / "takes").mkdir()
        (folder / "takes" / "shot-0002-t1.mp4").write_bytes(b"x")          # a retaken row counts
        assert kc.run_results_here("demo-ltx-video-1-2")
        assert not kc.run_results_here("demo-upscale-x2-1-1") and not kc.run_results_here("demo-ltx-video-5-2") and not kc.run_results_here("nonsense")

    def test_older_than(self):
        assert kc.run_older_than({"last_run": "2000-01-01 00:00"}, 7)
        assert not kc.run_older_than({"last_run": "2999-01-01 00:00"}, 7) and not kc.run_older_than({"last_run": "garbage"}, 7) and not kc.run_older_than({}, 7)

    def test_auto_plan_only_asks_about_runs_that_could_be_deleted(self, kaggle, book):
        self.setup_runs(kaggle, 5)                       # the 2 oldest are outside the newest 3
        old = kaggle.listing[0]
        kaggle.listing[0] = (old[0], "2000-01-01 00:00:00")          # very old: counts as deletable even though nothing is downloaded
        kaggle.status[old[0]] = "ERROR"          # a failed run that is old enough is removed; a COMPLETE one whose results are not here is kept
        plan = kc.auto_cleanup_plan()
        assert [r["slug"][-3:] for r in plan["remove"]] == ["1-1"] and [r["slug"][-3:] for r in plan["kept_not_downloaded"]] == ["2-2"]
        asked = [c[2].split("/")[-1] for c in kaggle.calls if c[:2] == ["kernels", "status"]]
        assert asked == [slug("ltx-video", 1, 1)]

    def test_delete_notebooks_removes_generated_files(self, fake_root):
        (fake_root / "Studio_Kaggle_x.ipynb").write_text("{}")
        (fake_root / "colab_generate_x.py").write_text("")
        (fake_root / "keep.py").write_text("")
        assert kc.delete_notebooks() == {"notebooks": 1, "scripts": 1} and (fake_root / "keep.py").exists()

    def test_auto_cleanup_respects_the_off_switch(self, kaggle, fake_root, monkeypatch):
        kc.AUTO_CLEAN_OFF.parent.mkdir(parents=True)
        kc.AUTO_CLEAN_OFF.touch()
        (fake_root / "Studio_Kaggle_x.ipynb").write_text("{}")
        kc.auto_cleanup(force=True)
        assert (fake_root / "Studio_Kaggle_x.ipynb").exists()
        kc.AUTO_CLEAN_OFF.unlink()
        kc.auto_cleanup(force=True)
        assert not (fake_root / "Studio_Kaggle_x.ipynb").exists()
