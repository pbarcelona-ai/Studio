"""M7: other styles from the approved master frames (same seed, master frame first among the references, img2img settings), the Script
Supervisor's consistency check with up to 3 tries then a flag, per-style gates, the comparison view and the comparison PDF."""
import csv

import pytest

import book_exports as bx
import consistency as cs
import gates
import layout
import pictures as px
import production
import styles
from test_pictures import approve_everything_before_pictures, png, render_all


@pytest.fixture
def two_styles(fake_root):
    d = fake_root / "projects" / "books" / "door"
    approve_everything_before_pictures(d)
    production.save(d, {"styles": [{"id": "claymation"}, {"id": "anime"}], "master": "claymation"})
    ask = styles.fake_ask(d)
    styles.write_card(d, "anime", ask)
    styles.write_translations(d, "anime", ask)
    styles.write_lookdev(d, "anime")
    st = styles.lookdev_status(d, "anime")
    setdir = layout.find_dir(st["set"])
    for it in st["items"]:
        png(setdir / "images" / "flux1_schnell" / f"image-{it['candidates'][0]['row']:04d}.png", (10, 200, 10))
        styles.pick(d, "anime", it["key"], it["candidates"][0]["row"])
    gates.approve(d, "lookdev", styles.gate_data(d))
    px.write_prompts(d, "claymation")
    render_all(d, "claymation")
    return d


def approve_master(d):
    for row in range(1, len(px.status(d, "claymation")["shots"]) + 1):
        px.approve(d, "claymation", row)
    px.approve_all_ready(d, "claymation")


class TestStructureLock:
    def test_needs_approved_master_pictures(self, two_styles):
        with pytest.raises(px.PictureError, match="master style's pictures first"):
            px.write_prompts(two_styles, "anime")

    def test_same_seed_master_first_and_img2img_settings(self, two_styles):
        approve_master(two_styles)
        out = px.write_prompts(two_styles, "anime")
        setdir = layout.find_dir(out["set"])
        rows = list(csv.DictReader(open(setdir / "all_images.csv", encoding="utf-8")))
        master_rows = list(csv.DictReader(open(layout.find_dir(px.set_name(two_styles, "claymation")) / "all_images.csv", encoding="utf-8")))
        assert [r["seed"] for r in rows] == [r["seed"] for r in master_rows]                        # the same seed in every style
        assert rows[0]["refs"].split("|")[0] == "master-0001.png" and rows[0]["init_image"] == "master-0001.png" and rows[0]["strength"] == "0.55"
        assert (setdir / "keyframe_refs" / "master-0001.png").read_bytes() == (layout.find_dir(px.set_name(two_styles, "claymation")) / "images/flux1_schnell/image-0001.png").read_bytes()
        assert rows[0]["prompt"].startswith(px.LOCK_TEXT) and "Anime" in rows[0]["prompt"] and "Claymation" not in rows[0]["prompt"]
        shots = px._read(px.pdir_of(two_styles, "anime") / "shots.json")["shots"]
        assert shots[0]["structure"] == {"method": "reference", "master": "master-0001.png", "strength": 0.55}
        assert px.gate_step(two_styles, "anime") == "pictures_anime" and px.gate_step(two_styles, "claymation") == "pictures"


class TestConsistency:
    def test_low_scores_get_three_tries_then_a_flag(self, two_styles):
        approve_master(two_styles)
        px.write_prompts(two_styles, "anime")
        render_all(two_styles, "anime")
        bad = {2}
        ask = cs.fake_ask(lambda image: 3 if any(f"pair-{r}.png" in image for r in bad) else 9)
        said = []
        r = cs.run(two_styles, "anime", ask, said.append)
        assert r["again"] == [2] and r["flagged"] == [] and r["checked"] == 9 and said[-1].startswith("Done:")
        res = cs.load(two_styles, "anime")
        assert res["1"]["score"] == 9 and res["2"]["pending"] and res["2"]["tries"] == 1
        assert px.status(two_styles, "anime")["shots"][1]["image"] == "" and px.status(two_styles, "anime")["shots"][1]["versions"]
        for tries in (2, 3):
            render_all(two_styles, "anime")
            r = cs.run(two_styles, "anime", ask, said.append)
        assert r["flagged"] == [2] and r["again"] == [] and cs.load(two_styles, "anime")["2"]["tries"] == 3
        assert "comparing shot 1 of 1" in " ".join(said)                                             # only the re-rendered shot is checked again

    def test_the_master_is_not_checked(self, two_styles):
        with pytest.raises(px.PictureError, match="reference"):
            cs.run(two_styles, "claymation", cs.fake_ask())

    def test_side_by_side(self, tmp_path):
        png(tmp_path / "a.png")
        png(tmp_path / "b.png", (0, 0, 0))
        from PIL import Image
        out = cs.side_by_side(tmp_path / "a.png", tmp_path / "b.png", tmp_path / "pair.png")
        with Image.open(out) as im:
            assert im.height == 512 and im.width > 1024 and im.getpixel((10, 10)) == (200, 80, 40) and im.getpixel((im.width - 10, 10)) == (0, 0, 0)

    def test_bad_replies(self):
        for bad in ({"score": 11}, {"score": "x"}, {"score": 5, "differences": "x"}):
            with pytest.raises(ValueError):
                cs.check_reply(bad)


class TestComparison:
    def test_pdf_and_route(self, server, book):
        approve_everything_before_pictures(book)
        px.write_prompts(book, "claymation")
        render_all(book, "claymation")
        production.save(book, {"styles": [{"id": "claymation"}, {"id": "anime"}], "master": "claymation"})      # a new style unapproves the look development
        st, j = server.api("GET", "/api/style_compare?project=demo")
        assert [s["id"] for s in j["styles"]] == ["claymation", "anime"] and len(j["rows"]) == 9
        assert j["rows"][0]["cells"]["claymation"]["image"] and j["rows"][0]["cells"]["anime"]["image"] == ""
        made = bx.export(book, "claymation", ("comparison",))
        pypdf = pytest.importorskip("pypdf")
        r = pypdf.PdfReader(str(made[0]))
        assert len(r.pages) == 2 and "style comparison" in r.pages[0].extract_text()
        st, j = server.api("POST", "/api/consistency_check", {"project": "demo", "style": "claymation", "engine": "fake"})
        assert st == 400 and "other styles" in j["error"]
        st, j = server.api("POST", "/api/pictures_render_again", {"project": "demo", "style": "anime"})
        assert st == 400 and "waiting" in j["error"]
        st, j = server.api("GET", "/api/pictures?project=demo&style=anime")
        assert j["style"] == "anime" and j["master"] == "claymation" and j["styles"] == ["claymation", "anime"] and j["consistency"] == {}


def test_gate_names():
    assert gates.known("pictures_anime") and gates.known("clips") and not gates.known("nope") and not gates.known("pictures_../x")
