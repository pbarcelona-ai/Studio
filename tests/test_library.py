"""M8: immutable assets and path aliases, start over / attempts / restore, the picture library (groups, liked first, verdicts, purposes,
moving versions, search) and reuse (matches, picture / prompt / layout, auto-fill, the "may not match" flag)."""
import csv
import json
import sys

import pytest

import assets
import attempts
import continuity_book as cb
import layout
import library as lib
import pictures as px
from test_pictures import approve_everything_before_pictures, png, render_all


class TestAssets:
    def test_store_once_alias_history_and_resolve(self, tmp_path):
        f = tmp_path / "images" / "a" / "image-0001.png"
        png(f)
        sha = assets.ingest(tmp_path, f)
        assert assets.ingest(tmp_path, f) == sha and len(list((tmp_path / "assets" / "objects").rglob("*.png"))) == 1
        obj = assets.resolve(tmp_path, sha)
        assert obj.read_bytes() == f.read_bytes()
        if sys.platform != "win32":
            assert (obj.stat().st_mode & 0o222) == 0                                # read-only: never changed
        png(f, (1, 2, 3))                                                            # the take is replaced at the same path
        sha2 = assets.ingest(tmp_path, f)
        assert sha2 != sha and [h["sha"] for h in assets.history(tmp_path, "images/a/image-0001.png")] == [sha, sha2]
        assert assets.resolve(tmp_path, "images/a/image-0001.png").read_bytes() == f.read_bytes()
        assert assets.resolve(tmp_path, "images/a/image-0001.png", 0) == obj          # the old content is still found by its old path
        out = assets.copy_out(tmp_path, sha, tmp_path / "copy.png")
        assert out.read_bytes() == obj.read_bytes() and assets.resolve(tmp_path, "0" * 64) is None
        with pytest.raises(ValueError):
            (tmp_path / "x.txt").write_text("x")
            assets.ingest(tmp_path, tmp_path / "x.txt")


@pytest.fixture
def made(fake_root):
    d = fake_root / "projects" / "books" / "door"
    approve_everything_before_pictures(d)
    px.write_prompts(d, "claymation")
    render_all(d, "claymation")
    px.approve(d, "claymation", 1)
    return d


class TestStartOver:
    def test_archive_keep_and_restore(self, made):
        keep_files = {"sources", "production.json"}
        a = attempts.start_over(made, ["sources", "settings", "styles"])
        assert a["n"] == 1 and a["label"].startswith("Attempt 1 – ") and "pictures" in a["moved"] and "shots" in a["moved"] and "readin" in a["moved"]
        assert all((made / k).exists() for k in keep_files) and (made / "styles").is_dir() and not (made / "pictures").exists()
        assert not (made / f"{made.name}.json").exists()                                   # the continuity book was not kept
        arch = made / "attempts" / a["id"]
        assert (arch / "pictures" / "claymation" / "shots.json").is_file() and (arch / "sets" / "door_px_claymation" / "all_images.csv").is_file()
        assert layout.find_dir("door_px_claymation") is None and layout.find_dir("door_ld_claymation") is not None   # look development kept with the styles
        assert attempts.files_of(made, a["id"]) and attempts.attempts(made)[0]["label"] == a["label"]
        out = attempts.restore(made, a["id"])
        assert out["restored"] == a["label"] and out["archived_current_as"].startswith("Attempt 2")
        assert (made / "pictures" / "claymation" / "shots.json").is_file() and layout.find_dir("door_px_claymation") is not None
        assert (made / f"{made.name}.json").is_file() and len(attempts.attempts(made)) == 1
        with pytest.raises(attempts.AttemptError):
            attempts.restore(made, "../x")
        with pytest.raises(attempts.AttemptError, match="cannot keep"):
            attempts.start_over(made, ["everything"])

    def test_another_book_with_a_similar_name_is_not_touched(self, made):
        other = layout.new_dir("doorway_px_claymation", "prompts")
        other.mkdir(parents=True)
        attempts.start_over(made, [])
        assert other.is_dir()


class TestLibrary:
    def test_items_groups_liked_first_and_decisions(self, made):
        px.prepare_regenerate(made, "claymation", 2)                                       # shot 2: one older version
        png(layout.find_dir("door_px_claymation") / "images" / "flux1_schnell" / "image-0002.png", (9, 9, 9))
        idx = lib.refresh(made)
        kinds = {i["purpose"] for i in idx["items"]}
        assert {"keyframe", "reference"} <= kinds
        g = next(x for x in lib.groups(made) if x["group"] == "claymation:S001:2")
        assert len(g["versions"]) == 2 and g["name"] == "S001 shot 2 (claymation)"
        old = g["versions"][1]["key"]
        lib.set_verdict(made, old, "liked")
        g = next(x for x in lib.groups(made) if x["group"] == "claymation:S001:2")
        assert g["versions"][0]["key"] == old and g["liked"] == old                         # the liked version is the default, first
        lib.set_purpose(made, old, "final")
        assert next(i for i in lib.index(made) if i["key"] == old)["purpose"] == "final"
        new_group = lib.move_version(made, old)
        assert new_group.startswith("own:") and len(next(x for x in lib.groups(made) if x["group"] == "claymation:S001:2")["versions"]) == 1
        lib.refresh(made)
        assert next(i for i in lib.index(made) if i["key"] == old)["group"] == new_group     # a refresh keeps the owner's decisions
        with pytest.raises(ValueError):
            lib.set_verdict(made, old, "great")
        with pytest.raises(ValueError):
            lib.set_purpose(made, "nope", "final")

    def test_search(self, made):
        lib.refresh(made)
        assert all(g["style"] == "claymation" for g in lib.search(made, style="claymation"))
        refs = lib.search(made, purpose="reference")
        assert refs and all(v["purpose"] == "reference" for g in refs for v in g["versions"])
        assert lib.search(made, character="MARA") and not lib.search(made, character="NOBODY")
        assert lib.search(made, q="lamp")

    def test_archived_attempts_are_in_the_library(self, made):
        attempts.start_over(made, ["sources", "settings", "styles", "continuity", "screenplay"])
        idx = lib.refresh(made)
        archived = [i for i in idx["items"] if i["attempt"].startswith("Attempt 1")]
        assert len(archived) >= 9 and all(assets.resolve(made, i["id"]) for i in archived)


class TestReuse:
    def test_matches_reuse_three_ways_and_auto_fill(self, made):
        lib.refresh(made)
        ms = lib.matches(made, "claymation", "S002", 1)
        assert ms and ms[0]["match"] >= ms[-1]["match"] and all((m["shot"] or {}).get("scene") != "S002" or m["shot"]["shot"] != 1 or m["attempt"] != "current" for m in ms)
        best = next(m for m in ms if m["kind"] == "image" and m["purpose"] == "keyframe")
        setdir = layout.find_dir("door_px_claymation")
        rv = lib.reuse(made, "claymation", "S002", 1, best["key"], "picture")
        assert rv["reused_from"]["how"] == "picture" and (setdir / "images" / "reused" / "image-0004.png").read_bytes() == assets.resolve(made, best["id"]).read_bytes()
        assert px.status(made)["shots"][3]["versions"]                                       # the shot's own picture became a version
        lib.reuse(made, "claymation", "S002", 2, best["key"], "prompt")
        rows = list(csv.DictReader(open(setdir / "all_images.csv", encoding="utf-8")))
        assert rows[4]["prompt"] == best["prompt"] and rows[4]["seed"] == str(best["seed"])
        lib.reuse(made, "claymation", "S002", 3, best["key"], "layout")
        rows = list(csv.DictReader(open(setdir / "all_images.csv", encoding="utf-8")))
        assert rows[5]["refs"].startswith("layout-0006.png") and rows[5]["prompt"].startswith(px.LOCK_TEXT) and (setdir / "keyframe_refs" / "layout-0006.png").is_file()
        with pytest.raises(ValueError):
            lib.reuse(made, "claymation", "S002", 1, best["key"], "steal")

    def test_auto_reuse_fills_empty_shots(self, made):
        setdir = layout.find_dir("door_px_claymation")
        lib.refresh(made)
        (setdir / "images" / "flux1_schnell" / "image-0007.png").unlink()
        out = lib.auto_reuse(made, "claymation", 0)
        assert [u["row"] for u in out["reused"]] == [7] and out["gpu_seconds_saved"] > 0 and px.status(made)["shots"][6]["image"].startswith("images/reused/")
        assert lib.auto_reuse(made, "claymation", 10.5)["reused"] == []

    def test_may_not_match_after_a_token_change(self, made):
        lib.refresh(made)
        it = next(i for i in lib.index(made) if i["parts"] and i["parts"]["characters"])
        assert not lib.stale(made, it)
        cb.edit(made, "characters", it["parts"]["characters"][0]["name"], {"token": "a different look now, red coat"})
        assert lib.stale(made, it)


class TestRoutes:
    def test_over_http(self, server, book):
        approve_everything_before_pictures(book)
        px.write_prompts(book, "claymation")
        render_all(book, "claymation")
        st, j = server.api("GET", "/api/picture_library?project=demo&refresh=1")
        assert st == 200 and j["groups"] and j["groups"][0]["versions"][0]["thumb"].startswith("/thumb/demo/assets/objects/")
        from conftest import TOKEN
        status, _, body = server.request("GET", j["groups"][0]["versions"][0]["thumb"], headers={"X-Studio-Token": TOKEN})
        assert status == 200 and body[:3] == b"\xff\xd8\xff"                                 # a JPEG thumbnail of the stored picture
        st, j = server.api("GET", "/api/shot_matches?project=demo&scene=S001&shot=2")
        assert st == 200 and j["matches"]
        st, j = server.api("POST", "/api/shot_reuse", {"project": "demo", "scene": "S001", "shot": 2, "key": j["matches"][0]["key"], "how": "prompt"})
        assert st == 200 and j["review"]["reused_from"]["how"] == "prompt"
        st, j = server.api("POST", "/api/auto_reuse", {"project": "demo", "min_score": 11})
        assert st == 400
        st, j = server.api("POST", "/api/start_over", {"project": "demo", "keep": ["sources", "settings", "styles"]})
        assert st == 200 and j["attempt"]["n"] == 1 and len(j["attempts"]) == 1
        st, j = server.api("GET", f"/api/attempt_files?project=demo&id={j['attempt']['id']}")
        assert st == 200 and any(f.startswith("pictures/") for f in j["files"])
        st, j = server.api("POST", "/api/attempt_restore", {"project": "demo", "id": json.loads(json.dumps(attempts.attempts(book)[0]))["id"]})
        assert st == 200 and (book / "pictures").is_dir()
