"""M11: the Animation Supervisor's motion prompts (once for every style), each style's image-to-video set (start frame = that style's
approved picture, same seed and EDL length), clip review and gates, and the film per style rendered from the EDL (Product E)."""
import csv
import subprocess

import pytest

import clips
import edl
import gates
import layout
import pictures as px
import render_cut as rc
import sound_design as sd
from test_pictures import approve_everything_before_pictures, render_all


def make_clip(path, seconds=2.0):
    path.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run([rc.ffmpeg(), "-y", "-loglevel", "error", "-f", "lavfi", "-i", f"testsrc=size=160x90:rate=24:duration={seconds}", "-c:v", "libx264",
                    "-pix_fmt", "yuv420p", str(path)], check=True)


@pytest.fixture
def pictured(fake_root):
    d = fake_root / "projects" / "books" / "door"
    approve_everything_before_pictures(d)
    sd.write_plan(d, sd.fake_ask(d), lambda t: None)
    px.write_prompts(d)
    render_all(d)
    for row in range(1, 10):
        px.approve(d, "claymation", row)
    px.approve_all_ready(d)
    edl.assemble(d)
    return d


class TestClips:
    def test_motion_needs_approved_pictures(self, fake_root):
        d = fake_root / "projects" / "books" / "door"
        approve_everything_before_pictures(d)
        with pytest.raises(clips.ClipError, match="pictures"):
            clips.write_motion(d, clips.fake_ask())

    def test_motion_prepare_review_gate(self, pictured):
        roles = []
        fake = clips.fake_ask()
        m = clips.write_motion(pictured, lambda p, r, s, v: (roles.append(r), fake(p, r, s, v))[1], lambda t: None)
        assert roles == ["animation_supervisor"] * 3 and m["scenes"]["S001"]["1"]["motion"].startswith("slow push in")
        out = clips.prepare(pictured, "claymation")
        setdir = layout.find_dir(out["set"])
        rows = list(csv.DictReader(open(setdir / "all_shots.csv", encoding="utf-8")))
        shots = px.status(pictured)["shots"]
        assert len(rows) == 9 and rows[0]["seed"] == str(shots[0]["seed"]) and rows[0]["prompt"].endswith("slow push in, her hair moves in the wind")
        assert float(rows[0]["seconds"]) == edl.cut(edl.load(pictured))["tracks"]["video"][0]["seconds"]
        assert (setdir / "images" / "pictures_keyframes" / "image-0001.png").read_bytes() == (setdir / shots[0]["image"]).read_bytes()
        with pytest.raises(clips.ClipError, match="render it first"):
            clips.review(pictured, "claymation", 1, approved=True)
        pytest.importorskip("imageio_ffmpeg")
        for row in range(1, 10):
            make_clip(setdir / "videos" / "ltx_video_fast_i2v" / f"shot-{row:04d}.mp4", 1.0)
        clips.review(pictured, "claymation", 1, approved=True, note="good")
        st = clips.status(pictured, "claymation")
        assert st["clips"][0]["approved"] and st["clips"][0]["note"] == "good" and st["clips"][0]["clip"].startswith("videos/")
        with pytest.raises(clips.ClipError, match="not approved"):
            clips.approve_all(pictured, "claymation")
        for row in range(2, 10):
            clips.review(pictured, "claymation", row, approved=True)
        clips.approve_all(pictured, "claymation")
        assert gates.approved(pictured, "clips", clips.gate_data(pictured, "claymation")) and clips.gate_step(pictured, "claymation") == "clips"

    def test_film_render(self, pictured):
        pytest.importorskip("imageio_ffmpeg")
        clips.write_motion(pictured, clips.fake_ask(), lambda t: None)
        out = clips.prepare(pictured, "claymation")
        setdir = layout.find_dir(out["set"])
        with pytest.raises(rc.RenderError, match="no clip"):
            rc.render(pictured, "claymation", "film", size=(160, 90))
        for row in range(1, 10):
            make_clip(setdir / "videos" / "ltx_video_fast_i2v" / f"shot-{row:04d}.mp4", 2.0)
        c = edl.load(pictured)
        for v in edl.cut(c)["tracks"]["video"]:
            v["seconds"] = 1.0
        edl.set_transition(edl.cut(c), "v0002", "dissolve", 0.4)
        edl.save(pictured, c)
        film = rc.render(pictured, "claymation", "film", size=(160, 90))
        assert film.name == "film_claymation.mp4"
        probe = subprocess.run([rc.ffmpeg(), "-i", str(film)], capture_output=True, text=True).stderr
        assert "160x90" in probe and "Duration: 00:00:08.6" in probe                       # 9 x 1 s, less the 0.4 s dissolve

    def test_needs_motion_and_approved_pictures(self, pictured):
        with pytest.raises(clips.ClipError, match="motion"):
            clips.prepare(pictured, "claymation")


class TestRoutes:
    def test_over_http(self, server, book):
        approve_everything_before_pictures(book)
        st, j = server.api("GET", "/api/clips?project=demo")
        assert st == 200 and not j["motion"] and j["checklist"] == list(clips.CHECKLIST)
        st, j = server.api("POST", "/api/clips_render", {"project": "demo", "service": "kaggle"})
        assert st == 400 and "pictures" in j["error"]
        st, j = server.api("POST", "/api/film_render", {"project": "demo"})
        assert st == 400 and "edit" in j["error"]
        st, j = server.api("POST", "/api/clip_review", {"project": "demo", "row": 99, "note": "x"})
        assert st == 400
