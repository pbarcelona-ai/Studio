"""Colour grading: the filter, the saved grades, the per-scene rows, the mix with the real ffmpeg, and the API."""
import csv
import subprocess

import pytest

import grade as g

imageio_ffmpeg = pytest.importorskip("imageio_ffmpeg")
FFMPEG = imageio_ffmpeg.get_ffmpeg_exe()


class TestFilter:
    def test_values_and_filter(self):
        assert g.filter_for(None) == "" and g.filter_for({"preset": "none"}) == "" and g.values({"preset": "warm", "temperature": 0.5})["temperature"] == 0.5
        f = g.filter_for({"preset": "night"})
        assert f.startswith("eq=brightness=-0.120:contrast=1.100:saturation=0.850,colorbalance=") and f.endswith(",")
        assert "colorbalance" not in g.filter_for({"saturation": 0.5}) and g.filter_for({"saturation": 0.5}) == "eq=brightness=0.000:contrast=1.000:saturation=0.500,"

    def test_check_spec(self):
        assert g.check_spec({"preset": "warm", "exposure": "0.1", "tint": ""}) == {"preset": "warm", "exposure": 0.1} and g.check_spec({"preset": "none"}) == {}
        for bad in ("x", {"preset": "sepia"}, {"exposure": 2}, {"saturation": -1}, {"contrast": "abc"}):
            with pytest.raises(g.GradeError):
                g.check_spec(bad)

    def test_every_preset_is_a_valid_ffmpeg_filter(self, tmp_path):
        clip = tmp_path / "in.mp4"
        subprocess.run([FFMPEG, "-y", "-loglevel", "error", "-f", "lavfi", "-i", "color=c=gray:s=32x32:r=5:d=0.4", "-pix_fmt", "yuv420p", str(clip)], check=True)
        for name in g.PRESETS:
            f = g.filter_for({"preset": name, "tint": 0.3})
            r = subprocess.run([FFMPEG, "-y", "-loglevel", "error", "-i", str(clip), "-vf", f + "null", str(tmp_path / f"{name}.mp4")], capture_output=True, text=True)
            assert r.returncode == 0, (name, r.stderr)


class TestStore:
    def test_set_clear_and_rows(self, tmp_path):
        (tmp_path / "audio_shots.csv").write_text("chapter,shot,scene\ndemo-001,1,demo-S001\ndemo-001,2,demo-S001\ndemo-001,3,demo-S002\ndemo-001,4,\n")
        g.set_grade(tmp_path, "default", {"preset": "vivid"})
        g.set_grade(tmp_path, "S001", {"preset": "night"})
        rows = g.row_filters(tmp_path)
        assert set(rows) == {1, 2, 3, 4} and rows[1] == rows[2] != rows[3] == rows[4]                 # S002 and the shot with no scene get the default
        g.set_grade(tmp_path, "S001", {})
        g.set_grade(tmp_path, "default", {})
        assert g.row_filters(tmp_path) == {} and g.load(tmp_path) == {"default": {}, "scenes": {}}
        for bad in ("", "S1", "../x"):
            with pytest.raises(g.GradeError):
                g.set_grade(tmp_path, bad, {"preset": "warm"})
        (tmp_path / "grading.json").write_text("[1]")
        assert g.load(tmp_path) == {"default": {}, "scenes": {}}

    def test_no_scene_column_means_the_default_for_everyone(self, tmp_path):
        (tmp_path / "audio_shots.csv").write_text("chapter,shot\ndemo-001,1\ndemo-001,2\n")
        g.set_grade(tmp_path, "default", {"preset": "cool"})
        assert set(g.row_filters(tmp_path)) == {1, 2}


def mean_rgb(video):
    r = subprocess.run([FFMPEG, "-loglevel", "error", "-i", str(video), "-frames:v", "1", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], capture_output=True)
    px = r.stdout
    n = len(px) // 3
    return tuple(sum(px[i::3]) / n for i in range(3))


class TestMix:
    @pytest.fixture()
    def gray_film(self, book, tmp_path):
        v = book / "videos" / "ltx_video"
        v.mkdir(parents=True)
        for n in (1, 2):
            subprocess.run([FFMPEG, "-y", "-loglevel", "error", "-f", "lavfi", "-i", "color=c=0x808080:s=64x48:r=12:d=1", "-pix_fmt", "yuv420p", str(v / f"shot-{n:04d}.mp4")], check=True)
        with open(book / "audio_shots.csv", "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["chapter", "shot", "lines_json", "narration", "sfx", "music", "scene"])
            for i, scene in ((1, "demo-S001"), (2, "demo-S002")):
                w.writerow(["1", i, "[]", "", "", "", scene])
        return book

    def test_a_graded_scene_changes_colour_and_the_other_does_not(self, gray_film, run_script):
        g.set_grade(gray_film, "S001", {"preset": "golden_hour"})
        code, out = run_script("mix_film.py", "--project", "demo", "--model", "ltx_video", "--grade", "--sync", "trim", "--no-loudnorm", "--out", "g.mp4")
        assert code is None and "grade: 1 shot(s) graded" in out
        film = gray_film / "films" / "g.mp4"
        r, _, b = mean_rgb(film)
        assert r - b > 8                                             # the first shot (scene S001) turned warm: red above blue
        code, out = run_script("mix_film.py", "--project", "demo", "--model", "ltx_video", "--sync", "trim", "--no-loudnorm", "--out", "plain.mp4")
        r2, _, b2 = mean_rgb(gray_film / "films" / "plain.mp4")
        assert abs(r2 - b2) < 3                                       # without --grade the same shot stays gray


class TestApi:
    def test_read_and_edit(self, server, book):
        import adaptation as ad
        from test_adaptation import make_plan
        ad.save(book, make_plan())
        out = server.api("GET", "/api/grading?project=demo")[1]
        assert "warm" in out["presets"] and [s["id"] for s in out["scenes"]] == ["S001", "S002", "S003", "S004"] and out["default"] == {}
        out = server.api("POST", "/api/grading", {"project": "demo", "scene": "S002", "grade": {"preset": "noir"}})[1]
        assert out["scenes"][1]["grade"] == {"preset": "noir"}
        out = server.api("POST", "/api/grading", {"project": "demo", "scene": "default", "grade": {"temperature": 0.3}})[1]
        assert out["default"] == {"temperature": 0.3}
        for body in ({"scene": "S1", "grade": {}}, {"scene": "S001", "grade": {"preset": "sepia"}}):
            assert server.api("POST", "/api/grading", {"project": "demo", **body})[0] == 400
        assert server.api("GET", "/api/grading?project=ghost")[0] == 400

    def test_the_sound_flags_carry_grade(self):
        from studio_app.generation import sound_flags
        assert sound_flags({"grade": True}, False) == ["--grade"] and sound_flags({}, True, True) == ["--music-scenes"] and sound_flags({"duck": False, "grade": True}, True) == ["--no-duck", "--music-bed", "--grade"]
