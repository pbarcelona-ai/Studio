"""The shot list follows the screenplay's scene order (shot_order.py), approval covers the order, and what was made follows its shot."""
import json

import adaptation as ad
import screenplay as sp
import shot_order
from bookkit import build_movies
from conftest import write_csv
from studio_app.projects import read_csv_rows
from test_adaptation import GOOD, make_plan


def rows_for(chapters_shots):
    return [{"chapter": f"demo-{c:03d}", "shot": str(s), "prompt": f"chapter {c} shot {s} a quiet garden"} for c, n in chapters_shots for s in range(1, n + 1)]


def moved_plan():
    plan = make_plan()
    sc = plan["scenes"]
    sc.insert(0, sc.pop(1))                      # S002 (chapter 3) now comes first, like a flashback moved up
    return plan


def test_order_follows_the_plan():
    rows = rows_for([(1, 2), (2, 2), (3, 2), (4, 1), (5, 1), (6, 1)])
    assert shot_order.order(make_plan(), rows) == list(range(9))
    o = shot_order.order(moved_plan(), rows)
    assert [rows[i]["chapter"] for i in o][:2] == ["demo-003", "demo-003"] and sorted(o) == list(range(9))


def test_out_of_order_and_build(book):
    ad.save(book, moved_plan())
    rows = rows_for([(1, 2), (2, 2), (3, 2)])
    assert "S002 should start at shot 1" in shot_order.out_of_order(book, rows)
    o = shot_order.order(ad.load(book), rows)
    assert shot_order.out_of_order(book, [rows[i] for i in o]) == ""
    assert shot_order.out_of_order(book, []) == ""


def test_files_follow_their_shots(book):
    old = rows_for([(1, 2), (3, 1)])
    new = [old[2], old[0], old[1]]
    new[2] = {**new[2], "prompt": "something else entirely now"}            # shot 1#2 was rewritten
    kf = book / "images" / "flux_keyframes"
    (kf / "takes").mkdir(parents=True)
    for n in (1, 2, 3):
        (kf / f"image-{n:04d}.png").write_text(f"pic{n}")
    (kf / "takes" / "image-0003-t1.png").write_text("old3")
    (book / "videos" / "ltx_chapters").mkdir(parents=True)
    (book / "videos" / "ltx_chapters" / "shot-0001.mp4").write_text("chapter film")
    (book / "face_check.json").write_text(json.dumps({"rows": {"1": {"status": "same"}, "2": {"status": "x"}}}))
    (book / "critic.json").write_text("{}")
    r = shot_order.follow(book, old, new)
    assert r == {"moved": 3, "set_aside": 1}
    assert (kf / "image-0001.png").read_text() == "pic3" and (kf / "image-0002.png").read_text() == "pic1" and not (kf / "image-0003.png").exists()
    assert (kf / "takes" / "image-0001-t1.png").read_text() == "old3"
    assert [p.read_text() for p in (book / "replaced").rglob("image-0002.png")] == ["pic2"]
    assert (book / "videos" / "ltx_chapters" / "shot-0001.mp4").read_text() == "chapter film"
    assert json.loads((book / "face_check.json").read_text())["rows"] == {"2": {"status": "same"}}
    assert not (book / "critic.json").exists()
    assert shot_order.follow(book, new, new) == {"moved": 0, "set_aside": 0}


def test_same_shot():
    assert shot_order.same_shot("A woman walks in a garden at dawn", "a woman walks slowly in the garden at dawn, soft light")
    assert not shot_order.same_shot("a woman walks in a garden", "a river at night with boats")
    assert shot_order.same_shot("", "")


def test_approval_covers_the_scene_order(book):
    (book / "chapters.json").write_text(json.dumps({"chapters": [{"n": n, "title": f"C{n}", "words": 100} for n in range(1, 7)]}))
    ad.save(book, make_plan())
    for s in ad.load(book)["scenes"]:
        sp.save_scene(book, s["id"], GOOD, edited=False)
    sp.approve(book, ad.load(book))
    fp = sp.fingerprint(book)
    plan = ad.load(book)
    plan["scenes"].insert(0, plan["scenes"].pop(1))
    ad.save(book, plan)
    st = sp.status(book, ad.load(book))
    assert not st["approved"] and st["reordered"] and sp.fingerprint(book) != fp
    sp.approve(book, ad.load(book))
    assert sp.status(book, ad.load(book))["approved"]


def test_movies_follow_runs_of_chapters(book):
    rows = rows_for([(3, 2), (1, 2), (3, 1)])                               # chapter 3 appears twice, apart
    write_csv(book / "all_shots.csv", rows)
    write_csv(book / "audio_shots.csv", [{"chapter": r["chapter"], "shot": r["shot"], "narration": "words " * 10} for r in rows])
    plan = build_movies(book, 100)
    assert plan["shots"][0]["rows"] == [1, 5] and plan["shots"][0]["chapters"] == ["demo-003", "demo-001", "demo-003"]
    assert read_csv_rows(book / "all_shots.csv")[0]["chapter"] == "demo-003"


def test_build_puts_shots_in_scene_order_and_moves_the_pictures(book, run_script):
    ad.save(book, moved_plan())
    (book / "scripts").mkdir(exist_ok=True)
    for c in (1, 2, 3):
        shots = [{"n": s, "prompt": f"chapter {c} shot {s} a quiet garden", "speaker": "NARRATOR", "narration": f"line {c}.{s}", "sfx": "wind", "music": "calm"}
                 for s in (1, 2)]
        (book / "scripts" / f"chapter-{c:03d}.json").write_text(json.dumps({"chapter": c, "shots": shots}))
    write_csv(book / "all_shots.csv", rows_for([(1, 2), (2, 2), (3, 2)]))       # the old list, in chapter order
    kf = book / "images" / "flux_keyframes"
    kf.mkdir(parents=True)
    for n in range(1, 7):
        (kf / f"image-{n:04d}.png").write_text(f"pic{n}")
    code, out = run_script("book_build.py", "demo")
    assert code in (None, 0), out
    rows = read_csv_rows(book / "all_shots.csv")
    assert [r["chapter"][-1] + r["shot"] for r in rows] == ["31", "32", "11", "12", "21", "22"]
    assert "scene order" in out and "4" in out
    assert [(kf / f"image-{n:04d}.png").read_text() for n in range(1, 7)] == ["pic5", "pic6", "pic1", "pic2", "pic3", "pic4"]
    assert shot_order.out_of_order(book, rows) == ""
