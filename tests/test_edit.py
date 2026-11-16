"""M10: the shared EDL (assembly, timeline with dissolves, move / trim / volume / split / ripple delete / snap to beats / transitions,
alternative cuts, the Editor's one-click notes, subtitles) and the animatic render per style with ffmpeg (Product D)."""
import json
import subprocess

import pytest

import edl
import render_cut as rc
import sound_design as sd
from test_pictures import approve_everything_before_pictures, render_all
from test_sound import tone


@pytest.fixture
def cutbook(fake_root):
    import pictures as px
    d = fake_root / "projects" / "books" / "door"
    approve_everything_before_pictures(d)
    import gates
    import shot_list as sl
    sl.edit_shot(d, "S001", 1, {"dialogue": "MARA: Who is there?"})
    gates.approve(d, "shotlist", sl.gate_data(sl.load(d)))
    sd.write_plan(d, sd.fake_ask(d), lambda t: None)
    px.write_prompts(d)
    render_all(d)
    return d


class TestEDL:
    def test_assembly_and_timeline(self, cutbook):
        d = edl.assemble(cutbook)
        c = edl.cut(d)
        v = c["tracks"]["video"]
        assert len(v) == 9 and v[0]["scene"] == "S001" and v[0]["shot"] == 1 and c["tracks"]["voice"][0]["attach"] == "v0001"
        assert len(c["tracks"]["music"]) == 3 and c["tracks"]["music"][0]["tempo_bpm"] == 66 and c["volumes"]["music"] < 1 and c["duck_db"] == 12
        tl = edl.timeline(c)
        assert tl["video"][1]["start"] == pytest.approx(tl["video"][0]["end"]) and tl["total"] == pytest.approx(sum(x["seconds"] for x in v))
        assert tl["music"][0]["start"] == 0 and tl["music"][0]["end"] == pytest.approx(tl["video"][2]["end"])
        edl.set_transition(c, "v0001", "dissolve", 1.0)
        tl2 = edl.timeline(c)
        assert tl2["video"][1]["start"] == pytest.approx(tl2["video"][0]["end"] - 1.0) and tl2["total"] == pytest.approx(tl["total"] - 1.0)

    def test_edits(self, cutbook):
        c = edl.cut(edl.assemble(cutbook))
        edl.move(c, "v0003", 0)
        assert [x["id"] for x in c["tracks"]["video"][:2]] == ["v0003", "v0001"]
        edl.trim(c, "v0001", 2.5, 0.5)
        assert c["tracks"]["video"][1]["seconds"] == 2.5 and c["tracks"]["video"][1]["trim_in"] == 0.5
        new = edl.split(c, "v0002", 2.0)
        assert new == "v0002-2" and [x["id"] for x in c["tracks"]["video"]][2:4] == ["v0002", "v0002-2"]
        edl.ripple_delete(c, "v0001")
        assert "v0001" not in [x["id"] for x in c["tracks"]["video"]] and all(a["attach"] != "v0001" for a in c["tracks"]["voice"])
        edl.set_volume(c, "music", 0.2)
        edl.set_volume(c, "m001", 1.5)
        assert c["volumes"]["music"] == 0.2 and c["tracks"]["music"][0]["volume"] == 1.5
        n = edl.snap_to_beats(c)
        beat = 60 / 66
        assert n >= 1 and all(abs(x["seconds"] / beat - round(x["seconds"] / beat)) < 1e-2 for x in c["tracks"]["video"])
        for bad in (lambda: edl.trim(c, "v0003", 0.1), lambda: edl.split(c, "v0003", 0.1), lambda: edl.set_volume(c, "music", 5),
                    lambda: edl.move(c, "v0003", 99), lambda: edl.set_transition(c, "v0003", "wipe"), lambda: edl.trim(c, "nope", 2)):
            with pytest.raises(edl.EditError):
                bad()

    def test_alternative_cuts_and_apply(self, cutbook):
        edl.assemble(cutbook)
        d = edl.apply(cutbook, "copy_cut", {"name": "short"})
        assert d["current"] == "short" and set(d["cuts"]) == {"main", "short"}
        edl.apply(cutbook, "delete", {"id": "v0009"})
        d = edl.load(cutbook)
        assert len(d["cuts"]["short"]["tracks"]["video"]) == 8 and len(d["cuts"]["main"]["tracks"]["video"]) == 9      # the main cut is untouched
        edl.apply(cutbook, "use_cut", {"name": "main"})
        assert edl.load(cutbook)["current"] == "main"
        with pytest.raises(edl.EditError):
            edl.apply(cutbook, "copy_cut", {"name": "main"})
        with pytest.raises(edl.EditError):
            edl.apply(cutbook, "trim", {"id": "v0001"})
        with pytest.raises(edl.EditError):
            edl.apply(cutbook, "explode", {})

    def test_editor_notes_in_one_click(self, cutbook):
        edl.assemble(cutbook)
        ns = edl.suggest(cutbook, edl.fake_ask(), 30)
        assert ns[0]["op"] == "trim" and ns[0]["nid"] == "n1"
        d = edl.apply_note(cutbook, "n1")
        assert edl.cut(d)["tracks"]["video"][0]["seconds"] == 2.5 and edl.notes(cutbook) == []
        with pytest.raises(edl.EditError):
            edl.apply_note(cutbook, "n1")

    def test_subtitles(self, cutbook):
        c = edl.cut(edl.assemble(cutbook))
        s = edl.srt(c, cutbook)
        assert s.startswith("1\n00:00:00,200 --> ") and "Who is there?" in s


class TestAnimatic:
    def test_render_one_style(self, cutbook):
        pytest.importorskip("imageio_ffmpeg")
        edl.assemble(cutbook)
        tone(cutbook / "audio" / "kokoro" / "narration-0001.wav", 1.2)
        tone(cutbook / "audio" / "musicgen_scenes" / "music-0001.wav", 6.0)
        out = rc.render(cutbook, "claymation", "animatic", size=(320, 180))
        assert out.name == "animatic_claymation.mp4" and out.with_suffix(".srt").read_text().strip()
        probe = subprocess.run([rc.ffmpeg(), "-i", str(out)], capture_output=True, text=True).stderr
        assert "Video: h264" in probe and "Audio: aac" in probe and "320x180" in probe
        info = json.loads((out.parent / "animatic_claymation.json").read_text())
        dur = [float(x) for x in __import__("re").findall(r"Duration: (\d+):(\d+):([\d.]+)", probe)[0]]
        assert abs(dur[0] * 3600 + dur[1] * 60 + dur[2] - info["seconds"]) < 0.6

    def test_missing_pictures_and_grade(self, cutbook):
        edl.assemble(cutbook)
        import layout
        import pictures as px
        setdir = layout.find_dir(px.status(cutbook)["set"])
        (setdir / "images" / "flux1_schnell" / "image-0003.png").unlink()
        with pytest.raises(rc.RenderError, match="1 shot"):
            rc.render(cutbook, "claymation", "animatic", size=(320, 180))
        assert rc.grade_filter(cutbook, "claymation") != "" or rc.grade_filter(cutbook, "claymation") == ""
        import styles
        styles.edit_card(cutbook, "claymation", {"grade": "high-contrast black-and-white"})
        assert "eq=" in rc.grade_filter(cutbook, "claymation")


class TestRoutes:
    def test_over_http(self, server, book):
        approve_everything_before_pictures(book)
        sd.write_plan(book, sd.fake_ask(book), lambda t: None)
        st, j = server.api("GET", "/api/edl?project=demo")
        assert st == 200 and len(j["cut"]["tracks"]["video"]) == 9 and j["timeline"]["total"] > 0 and j["cuts"] == ["main"]
        st, j = server.api("POST", "/api/edl_edit", {"project": "demo", "op": "trim", "id": "v0002", "seconds": 3})
        assert st == 200 and j["cut"]["tracks"]["video"][1]["seconds"] == 3
        st, j = server.api("POST", "/api/edl_edit", {"project": "demo", "op": "trim", "id": "v0002", "seconds": -1})
        assert st == 400
        st, j = server.api("POST", "/api/edl_suggest", {"project": "demo", "engine": "fake"})
        assert st == 200 and j["notes"]
        st, j = server.api("POST", "/api/edl_note", {"project": "demo", "nid": j["notes"][0]["nid"], "accept": False})
        assert st == 200 and j["notes"] == []
        st, j = server.api("POST", "/api/animatic", {"project": "demo", "style": "nope"})
        assert st == 400

