"""M5: style cards, style translations, prompt assembly in code (identical structure for every style), look development and its gate."""
import csv

import pytest

import continuity_book as cb
import production
import read_it_in as ri
import shot_list as sl
import sources as src
import styles
from test_read_it_in import STORY


@pytest.fixture
def lookbook(fake_root):
    d = fake_root / "projects" / "books" / "door"
    src.store(d, src.from_idea(STORY), True)
    ri.ReadItIn(d, ri.fake_ask(d)).run()
    cb.write(d, cb.fake_ask(d))
    production.save(d, {"styles": [{"id": "claymation"}, {"id": "realistic"}], "master": "claymation"})
    return d


class TestCards:
    def test_card_and_translations(self, lookbook):
        ask = styles.fake_ask(lookbook)
        card = styles.write_card(lookbook, "claymation", ask)
        assert set(styles.CARD_KEYS) <= set(card) and card["name"] == "Claymation" and card["prefix"].startswith("Claymation")
        tr = styles.write_translations(lookbook, "claymation", ask)
        assert set(tr["characters"]) == {c["name"] for c in cb.load(lookbook)["characters"]} and tr["props"]

    def test_bad_replies(self, lookbook):
        with pytest.raises(ValueError, match="needs 'palette'"):
            styles.check_card(dict.fromkeys(styles.CARD_KEYS, "x") | {"palette": ""})
        check = styles.translation_checker(cb.load(lookbook))
        with pytest.raises(ValueError, match="missing"):
            check({"characters": {}, "locations": {}, "props": {}})

    def test_unknown_style_and_missing_parts(self, lookbook):
        with pytest.raises(styles.StyleError, match="not one of this book"):
            styles.write_card(lookbook, "anime", styles.fake_ask(lookbook))
        with pytest.raises(styles.StyleError, match="no style card"):
            styles.card_of(lookbook, "realistic")
        with pytest.raises(styles.StyleError, match="bad style id"):
            styles.sdir(lookbook, "../x")

    def test_edits(self, lookbook):
        ask = styles.fake_ask(lookbook)
        styles.write_card(lookbook, "claymation", ask)
        styles.write_translations(lookbook, "claymation", ask)
        assert styles.edit_card(lookbook, "claymation", {"palette": "pastel", "bogus": "x"})["palette"] == "pastel"
        with pytest.raises(ValueError):
            styles.edit_card(lookbook, "claymation", {"prefix": ""})
        styles.edit_translation(lookbook, "claymation", "characters", "MARA", "plasticine skin, felt coat")
        assert styles.translations_of(lookbook, "claymation")["characters"]["MARA"] == "plasticine skin, felt coat"
        with pytest.raises(styles.StyleError):
            styles.edit_translation(lookbook, "claymation", "characters", "NOBODY", "x")


class TestAssembly:
    def test_the_same_shot_in_two_styles(self, lookbook):
        ask = styles.fake_ask(lookbook)
        for sid in ("claymation", "realistic"):
            styles.write_card(lookbook, sid, ask)
            styles.write_translations(lookbook, sid, ask)
        styles.edit_translation(lookbook, "claymation", "characters", "MARA", "plasticine skin with faint fingerprints")
        book = cb.load(lookbook)
        shot = {"type": "MCU", "lens_mm": 50, "height": "eye", "angle": "straight", "movement": "push in", "composition": "rule of thirds",
                "action": "She lights the lamp.", "expression": "set jaw", "lighting": "warm practical", "characters": ["Mara"], "props": ["lamp"]}
        loc = book["locations"][0]["name"]
        a = styles.assemble(shot, loc, styles.card_of(lookbook, "claymation"), styles.translations_of(lookbook, "claymation"), book)
        b = styles.assemble(shot, loc, styles.card_of(lookbook, "realistic"), styles.translations_of(lookbook, "realistic"), book)
        for x in (a, b):                                     # the WHAT is the same in both
            assert x["parts"]["camera"] == "MCU shot, 50mm lens, eye height, straight, push in, rule of thirds"
            assert x["parts"]["action"] == "She lights the lamp. set jaw"
            assert x["parts"]["characters"][0]["identity"] == book["characters"][0]["token"] and x["parts"]["location"]["name"] == loc
            assert x["parts"]["props"][0]["name"] == "the lamp" and "text, subtitles" in x["negative"]
        assert a["parts"]["prefix"] != b["parts"]["prefix"] and "fingerprints" in a["prompt"] and "fingerprints" not in b["prompt"]
        order = [a["prompt"].index(p) for p in (a["parts"]["prefix"], "MCU shot", "She lights the lamp", book["characters"][0]["token"][:20],
                                                   "warm practical", a["parts"]["lighting_language"], a["parts"]["suffix"])]
        assert order == sorted(order)                         # Section 7.3 order

    def test_unknown_people_are_left_out(self):
        card = dict.fromkeys(styles.CARD_KEYS, "x")
        out = styles.assemble({"type": "WS", "action": "a", "characters": ["GHOST"]}, "nowhere", card, {}, {"characters": [], "locations": []})
        assert out["parts"]["characters"] == [] and out["parts"]["location"] is None


class TestLookDev:
    def test_prompt_set_status_pick_and_gate(self, lookbook):
        ask = styles.fake_ask(lookbook)
        styles.write_card(lookbook, "claymation", ask)
        with pytest.raises(styles.StyleError, match="translations"):
            styles.write_lookdev(lookbook, "claymation")
        styles.write_translations(lookbook, "claymation", ask)
        r = styles.write_lookdev(lookbook, "claymation")
        book = cb.load(lookbook)
        assert r["items"] == len(book["characters"]) * 3 + len(book["locations"]) and r["rows"] == r["items"] * 4 and r["set"] == "door_ld_claymation"
        import layout
        setdir = layout.find_dir(r["set"])
        assert setdir.parent.name == "prompts" and (setdir / "promptset.json").is_file()
        rows = list(csv.DictReader(open(setdir / "all_images.csv", encoding="utf-8")))
        assert len(rows) == r["rows"] and rows[0]["prompt"].startswith("Claymation") and "front view" in rows[0]["prompt"] and int(rows[0]["height"]) > int(rows[0]["width"])
        assert len({x["seed"] for x in rows}) == len(rows)
        (setdir / "images" / "flux1_schnell").mkdir(parents=True)
        (setdir / "images" / "flux1_schnell" / "image-0002.png").write_bytes(b"png")
        st = styles.lookdev_status(lookbook, "claymation")
        first = st["items"][0]
        assert st["rendered"] == 1 and first["candidates"][1]["image"] == "images/flux1_schnell/image-0002.png" and first["pick"] is None
        styles.pick(lookbook, "claymation", first["key"], 2)
        assert styles.lookdev_status(lookbook, "claymation")["items"][0]["pick"] == 2
        with pytest.raises(styles.StyleError):
            styles.pick(lookbook, "claymation", first["key"], 99)
        assert styles.summary(lookbook)["gate"]["approved"] is False

    def test_long_book_names_fit(self, tmp_path):
        p = tmp_path / ("a" * 40)
        assert len(styles.lookdev_set(p, "watercolour")) == 40 and styles.lookdev_set(p, "watercolour").endswith("_ld_watercolour")


class TestRoutes:
    def test_over_http(self, server, book):
        src.store(book, src.from_idea(STORY), True)
        ri.ReadItIn(book, ri.fake_ask(book)).run()
        st, j = server.api("POST", "/api/styles_write", {"project": "demo", "engine": "fake"})
        assert st == 400 and "continuity book first" in j["error"]
        cb.write(book, cb.fake_ask(book))
        production.save(book, {"styles": [{"id": "anime"}]})
        ask = styles.fake_ask(book)
        styles.write_card(book, "anime", ask)
        styles.write_translations(book, "anime", ask)
        styles.write_lookdev(book, "anime")
        st, j = server.api("GET", "/api/styles?project=demo")
        assert j["styles"][0]["id"] == "anime" and j["styles"][0]["master"] and j["styles"][0]["lookdev"]["rows"] > 0
        st, j = server.api("POST", "/api/style_card_edit", {"project": "demo", "style": "anime", "fields": {"grade": "teal and orange"}})
        assert st == 200 and j["styles"][0]["card"]["grade"] == "teal and orange"
        st, j = server.api("POST", "/api/lookdev_approve", {"project": "demo"})
        assert st == 400 and "pick the best" in j["error"]
        for it in styles.lookdev_status(book, "anime")["items"]:
            styles.pick(book, "anime", it["key"], it["candidates"][0]["row"])
        st, j = server.api("POST", "/api/lookdev_approve", {"project": "demo"})
        assert st == 200 and j["gate"]["approved"]
        st, j = server.api("POST", "/api/lookdev_render", {"project": "demo", "style": "anime", "service": "nowhere"})
        assert st == 400
        sl.write(book, sl.fake_ask(book), lambda t: None)
        st, j = server.api("GET", "/api/prompt_preview?project=demo&style=anime&scene=S001&shot=2")
        assert st == 200 and j["parts"]["camera"].startswith("MCU shot") and j["prompt"]
        st, j = server.api("GET", "/api/prompt_preview?project=demo&style=anime&scene=S009&shot=1")
        assert st == 400
