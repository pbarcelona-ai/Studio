"""The routes that start jobs (M4-M15), with the job runner recording the job instead of running it: each builds the right step, checks
its inputs, and refuses what it must."""
import pytest

import edl
import gates
import pictures as px
import sound_design as sd
import sources as src
from test_pictures import approve_everything_before_pictures, render_all
from test_read_it_in import STORY


@pytest.fixture
def jobs(monkeypatch):
    from studio_app import jobs as jobmod
    started = []

    def start(steps, opt, queue=False):
        started.append((steps, opt, queue))
        return 0
    monkeypatch.setattr(jobmod.JOB, "start", start)
    return started


@pytest.fixture
def ready(book):
    approve_everything_before_pictures(book)
    return book


def argv(jobs):
    return [s["argv"] for steps, _, _ in jobs for s in steps]


class TestStartingJobs:
    def test_breakdown_and_styles(self, server, ready, jobs):
        assert server.api("POST", "/api/continuity_book", {"project": "demo", "engine": "fake"})[0] == 200
        assert server.api("POST", "/api/shot_list", {"project": "demo", "engine": "fake", "force": True})[0] == 200
        assert server.api("POST", "/api/styles_write", {"project": "demo", "engine": "fake", "style": "claymation"})[0] == 200
        st, j = server.api("POST", "/api/styles_write", {"project": "demo", "style": "nope"})
        assert st == 400
        a = argv(jobs)
        assert a[0][:3] == ["python3", "continuity_book.py", "demo"] and a[1][-1] == "--force" and a[2][3:5] == ["--style", "claymation"]

    def test_pictures_renders(self, server, ready, jobs):
        server.api("POST", "/api/pictures_prompts", {"project": "demo"})
        body = {"project": "demo", "service": "kaggle", "gpu": "NvidiaTeslaT4", "kaggle_user": "pat", "image_model": "flux2_klein_4b"}
        st, j = server.api("POST", "/api/pictures_render", body)
        assert st == 200 and argv(jobs)[-1][:2] == ["scripts/run_kaggle_model.sh", "image_flux2_klein_4b"]
        assert jobs[-1][0][0]["env"]["PROJECT"] == "door_px_claymation".replace("door", "demo")
        for bad in ({"service": "moon"}, {"image_model": "nope"}, {"kaggle_user": "!"}):
            assert server.api("POST", "/api/pictures_render", {**body, **bad})[0] == 400
        st, j = server.api("POST", "/api/lookdev_render", {**body, "style": "claymation"})
        assert st == 200 and argv(jobs)[-1][1] == "image_flux2_klein_4b"
        render_all(ready)
        st, j = server.api("POST", "/api/picture_action", {**body, "row": 2, "action": "regenerate"})
        assert st == 200 and px.status(ready)["shots"][1]["versions"]
        st, j = server.api("POST", "/api/consistency_check", {"project": "demo", "style": "claymation"})
        assert st == 400

    def test_sound_edit_clips_and_film(self, server, ready, jobs):
        assert server.api("POST", "/api/sound_plan", {"project": "demo", "engine": "fake"})[0] == 200
        sd.write_plan(ready, sd.fake_ask(ready), lambda t: None)
        assert server.api("POST", "/api/audiobook_render", {"project": "demo"})[0] == 200
        server.api("POST", "/api/sound_approve", {"project": "demo"})
        assert server.api("POST", "/api/audiobook_make", {"project": "demo"})[0] == 200
        assert server.api("POST", "/api/animatic", {"project": "demo", "size": "1280x720", "subtitles": True})[0] == 200
        assert argv(jobs)[-1][-1] == "--subtitles" and "1280x720" in argv(jobs)[-1]
        assert server.api("POST", "/api/animatic", {"project": "demo", "size": "99x99"})[0] == 400
        assert server.api("POST", "/api/clips_motion", {"project": "demo", "engine": "fake"})[0] == 200
        gates.approve(ready, "edit", edl.assemble(ready)["cuts"])
        st, j = server.api("POST", "/api/film_render", {"project": "demo"})
        assert st == 400 and "clips" in j["error"]
        st, j = server.api("POST", "/api/edl_approve", {"project": "demo"})
        assert st == 200 and j["gate"]["approved"]
        for op, extra in (("split", {"id": "v0001", "at": 2}), ("volume", {"target": "voice", "volume": 0.5}), ("snap", {}), ("duck", {"db": 9}),
                          ("transition", {"id": "v0003", "kind": "dissolve"}), ("copy_cut", {"name": "short"}), ("use_cut", {"name": "main"}), ("reassemble", {})):
            assert server.api("POST", "/api/edl_edit", {"project": "demo", "op": op, **extra})[0] == 200, op

    def test_clips_render_checks(self, server, ready, jobs):
        px.write_prompts(ready)
        render_all(ready)
        for row in range(1, 10):
            px.approve(ready, "claymation", row)
        px.approve_all_ready(ready)
        import clips
        clips.write_motion(ready, clips.fake_ask(), lambda t: None)
        body = {"project": "demo", "service": "kaggle", "gpu": "NvidiaTeslaT4", "kaggle_user": "pat", "video_model": "ltx_video_fast_i2v"}
        st, j = server.api("POST", "/api/clips_render", body)
        assert st == 200 and jobs[-1][0][0]["env"]["KEYFRAME_MODEL"] == "pictures"
        assert server.api("POST", "/api/clips_render", {**body, "video_model": "wan"})[0] == 400
        assert server.api("POST", "/api/clips_render", {**body, "first": 5, "last": 2})[0] == 400
        st, j = server.api("GET", "/api/clips?project=demo&style=claymation")
        assert st == 200 and len(j["clips"]) == 9
        assert server.api("POST", "/api/clips_approve", {"project": "demo"})[0] == 400

    def test_series_marketing_queue_media_v1(self, server, ready, jobs):
        assert server.api("POST", "/api/series_split", {"project": "demo", "episodes": 3, "engine": "fake"})[0] == 200
        assert argv(jobs)[-1][3:5] == ["--episodes", "3"]
        assert server.api("POST", "/api/series_next", {"project": "demo"})[0] == 400
        assert server.api("POST", "/api/marketing_plan", {"project": "demo", "engine": "fake"})[0] == 200
        st, j = server.api("POST", "/api/queue_add", {"projects": ["demo"], "engine": "fake"})
        assert st == 200 and j["queued"] == ["demo"]
        src.store(ready, src.from_idea(STORY), True)
        assert server.api("POST", "/api/media_understand", {"project": "demo", "id": "s002"})[0] == 400        # an idea is not a video
        st, j = server.api("POST", "/api/v1/run", {"project": "demo", "stop_at": ["shotlist"], "service": "kaggle", "gpu": "NvidiaTeslaT4",
                                                    "kaggle_user": "pat", "image_model": "flux2_klein_4b", "confirm_spend": True, "engine": "fake"})
        a = argv(jobs)[-1]
        assert st == 200 and a[:3] == ["python3", "autopilot.py", "demo"] and "--confirm-spend" in a and a[a.index("--stop-at") + 1] == "shotlist"
        assert server.api("POST", "/api/v1/run", {"project": "demo", "gpu": "a;b"})[0] == 400
        st, j = server.api("POST", "/api/v1/styles", {"project": "demo", "style": "noir", "engine": "fake"})
        assert st == 200 and "noir" in j["styles"]
        st, j = server.api("POST", "/api/v1/queue", {"projects": ["demo"], "engine": "fake"})
        assert st == 200
        st, j = server.api("POST", "/api/v1/projects", {"name": "auto_one", "sources": [{"kind": "idea", "text": STORY}], "rights": True, "mode": "autopilot",
                                                         "engine": "fake"})
        assert st == 200 and j["autopilot"]
        st, j = server.api("GET", "/api/history?project=demo")
        mid = j["moments"][0]["id"]
        assert server.api("POST", "/api/v1/branch", {"project": "demo", "moment": mid, "name": "demo_v1b"})[1]["project"] == "demo_v1b"
        assert server.api("GET", "/api/v1/exports?project=demo")[0] == 200
