"""M6: the master style's picture prompts from the approved shot list and look development, the per-tile review (approve, note, own
prompt, regenerate with versions, swap), shot layouts, the pictures gate, and the storyboard / illustrated book exports (Products B, C)."""
import csv
import zipfile

import pytest

import book_exports as bx
import continuity_book as cb
import gates
import layout
import pictures as px
import production
import read_it_in as ri
import shot_list as sl
import sources as src
import styles
from test_read_it_in import STORY


def png(path, color=(200, 80, 40)):
    from PIL import Image
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (64, 36), color).save(path)


def approve_everything_before_pictures(d):
    src.store(d, src.from_idea(STORY), True)
    ri.ReadItIn(d, ri.fake_ask(d)).run()
    cb.write(d, cb.fake_ask(d))
    book = cb.load(d)
    gates.approve(d, "continuity", [book.get("characters", []), book.get("locations", []), book.get("props", [])])
    sl.write(d, sl.fake_ask(d), lambda t: None)
    gates.approve(d, "shotlist", sl.gate_data(sl.load(d)))
    production.save(d, {"styles": [{"id": "claymation"}], "master": "claymation"})
    ask = styles.fake_ask(d)
    styles.write_card(d, "claymation", ask)
    styles.write_translations(d, "claymation", ask)
    styles.write_lookdev(d, "claymation")
    st = styles.lookdev_status(d, "claymation")
    setdir = layout.find_dir(st["set"])
    for it in st["items"]:
        c = it["candidates"][0]
        png(setdir / "images" / "flux1_schnell" / f"image-{c['row']:04d}.png")
        styles.pick(d, "claymation", it["key"], c["row"])
    gates.approve(d, "lookdev", styles.gate_data(d))


@pytest.fixture
def ready(fake_root):
    d = fake_root / "projects" / "books" / "door"
    approve_everything_before_pictures(d)
    return d


def render_all(d, sid="claymation"):
    st = px.status(d, sid)
    setdir = layout.find_dir(st["set"])
    for s in st["shots"]:
        png(setdir / "images" / "flux1_schnell" / f"image-{s['row']:04d}.png", (s["row"] * 20 % 255, 90, 120))
    return setdir


class TestPrompts:
    def test_gates_come_first(self, fake_root):
        d = fake_root / "projects" / "books" / "early"
        src.store(d, src.from_idea(STORY), True)
        ri.ReadItIn(d, ri.fake_ask(d)).run()
        with pytest.raises(px.PictureError, match="shot list"):
            px.write_prompts(d)

    def test_one_prompt_per_shot_with_refs_and_seeds(self, ready):
        out = px.write_prompts(ready)
        assert out["style"] == "claymation" and out["rows"] == 9 and out["set"] == "door_px_claymation"
        setdir = layout.find_dir(out["set"])
        rows = list(csv.DictReader(open(setdir / "all_images.csv", encoding="utf-8")))
        assert len(rows) == 9 and rows[0]["prompt"].startswith("Claymation film still") and "MARA" in rows[0]["prompt"].upper()
        assert rows[0]["refs"].startswith("ref-mara.png") and (setdir / "keyframe_refs" / "ref-mara.png").is_file()
        assert rows[0]["seed"] == str(px.seed_of("door", "S001", 1)) and len({r["seed"] for r in rows}) == 9
        shots = px._read(px.pdir_of(ready, "claymation") / "shots.json")["shots"]
        assert shots[0]["parts"]["camera"].startswith("WS shot") and shots[0]["scene"] == "S001"


class TestReview:
    def test_approve_note_prompt_regenerate_swap_and_gate(self, ready):
        px.write_prompts(ready)
        with pytest.raises(px.PictureError, match="render it first"):
            px.approve(ready, "claymation", 1)
        setdir = render_all(ready)
        st = px.status(ready)
        assert all(s["image"] for s in st["shots"]) and st["approved"] == 0
        px.approve(ready, "claymation", 1)
        lay = px.pdir_of(ready, "claymation") / "layouts" / "S001-001"
        assert (lay / "edges.png").is_file() and px._read(lay / "layout.json")["seed"] == px.seed_of("door", "S001", 1)
        px.note(ready, "claymation", 2, "  make it   darker ")
        px.set_prompt(ready, "claymation", 3, "a lamp in the dark, claymation")
        rows = list(csv.DictReader(open(setdir / "all_images.csv", encoding="utf-8")))
        assert rows[2]["prompt"] == "a lamp in the dark, claymation"
        old_seed = rows[3]["seed"]
        px.prepare_regenerate(ready, "claymation", 4)
        st = px.status(ready)
        assert st["shots"][3]["image"] == "" and st["shots"][3]["versions"] == ["versions/image-0004.v1.png"] and st["shots"][1]["note"] == "make it darker"
        assert list(csv.DictReader(open(setdir / "all_images.csv", encoding="utf-8")))[3]["seed"] != old_seed
        a = (setdir / "images/flux1_schnell/image-0005.png").read_bytes()
        b = (setdir / "images/flux1_schnell/image-0006.png").read_bytes()
        px.swap(ready, "claymation", 5, 6)
        assert (setdir / "images/flux1_schnell/image-0005.png").read_bytes() == b and (setdir / "images/flux1_schnell/image-0006.png").read_bytes() == a
        with pytest.raises(px.PictureError, match="not approved"):
            px.approve_all_ready(ready)
        png(setdir / "images" / "flux1_schnell" / "image-0004.png")
        for row in range(1, 10):
            px.approve(ready, "claymation", row)
        px.approve_all_ready(ready)
        assert gates.approved(ready, "pictures", px.gate_data(ready))
        px.note(ready, "claymation", 1, "notes do not change the approval")
        assert gates.approved(ready, "pictures", px.gate_data(ready))
        px.approve(ready, "claymation", 1, False)
        assert not gates.approved(ready, "pictures", px.gate_data(ready))

    def test_bad_rows(self, ready):
        px.write_prompts(ready)
        with pytest.raises(px.PictureError):
            px.note(ready, "claymation", 99, "x")
        with pytest.raises(px.PictureError, match="both shots"):
            px.swap(ready, "claymation", 1, 2)


class TestExports:
    def test_storyboard_and_illustrated_book(self, ready):
        px.write_prompts(ready)
        render_all(ready)
        for row in range(1, 10):
            px.approve(ready, "claymation", row)
        made = bx.export(ready)
        assert sorted(p.name for p in made) == ["illustrated_claymation.epub", "illustrated_claymation.pdf", "storyboard_claymation.pdf"]
        pypdf = pytest.importorskip("pypdf")
        r = pypdf.PdfReader(str(ready / "exports" / "storyboard_claymation.pdf"))
        assert len(r.pages) == 1 + 2                                                    # title + 9 frames at 6 per page
        assert "S001 / shot 1" in r.pages[1].extract_text() and r.pages[1].images
        book = pypdf.PdfReader(str(ready / "exports" / "illustrated_claymation.pdf"))
        assert len(book.pages) == 1 + 3                                                 # title + one page per scene (no page plan yet)
        with zipfile.ZipFile(ready / "exports" / "illustrated_claymation.epub") as z:
            names = z.namelist()
            assert names[0] == "mimetype" and z.getinfo("mimetype").compress_type == zipfile.ZIP_STORED
            assert "OEBPS/p001.xhtml" in names and "OEBPS/img/p001.jpg" in names and 'properties="nav"' in z.read("OEBPS/content.opf").decode()

    def test_the_illustrators_page_plan(self, ready):
        px.write_prompts(ready)
        render_all(ready)
        roles = []
        fake = bx.fake_ask(ready)
        pages = bx.page_plan(ready, "claymation", lambda p, r, s, v: (roles.append(r), fake(p, r, s, v))[1])
        assert roles == ["illustrator"] and [p["picture"] for p in pages] == [1, 3, 5, 7, 9] and bx.page_plan(ready, "claymation") == pages
        with pytest.raises(ValueError):
            bx.check_pages({"pages": [{"picture": "one", "text": "x"}]})

    def test_nothing_yet(self, ready):
        with pytest.raises(bx.ExportError, match="no pictures"):
            bx.export(ready)


class TestRoutes:
    def test_over_http(self, server, book):
        approve_everything_before_pictures(book)
        st, j = server.api("POST", "/api/pictures_prompts", {"project": "demo"})
        assert st == 200 and j["made"]["rows"] == 9 and j["style"] == "claymation"
        render_all(book)
        st, j = server.api("POST", "/api/picture_action", {"project": "demo", "row": 1, "action": "approve"})
        assert st == 200 and j["approved"] == 1
        st, j = server.api("POST", "/api/picture_action", {"project": "demo", "row": 1, "action": "dance"})
        assert st == 400
        st, j = server.api("POST", "/api/picture_action", {"project": "demo", "row": 2, "action": "regenerate", "service": "nowhere"})
        assert st == 400 and px.status(book)["shots"][1]["image"]                        # a bad GPU choice moves nothing aside
        st, j = server.api("POST", "/api/pictures_approve", {"project": "demo"})
        assert st == 400 and "not approved" in j["error"]
        st, j = server.api("POST", "/api/pictures_render", {"project": "demo", "first": 5, "last": 99})
        assert st == 400
        st, j = server.api("POST", "/api/page_plan", {"project": "demo", "engine": "fake"})
        assert st == 200 and j["pages"]
        st, j = server.api("POST", "/api/pictures_export", {"project": "demo", "kinds": ["storyboard"]})
        assert st == 200 and j["exports"][0]["name"] == "storyboard_claymation.pdf"
        from conftest import TOKEN
        status, hdrs, body = server.request("GET", "/download/demo/exports/storyboard_claymation.pdf", headers={"X-Studio-Token": TOKEN})
        assert status == 200 and body.startswith(b"%PDF")
