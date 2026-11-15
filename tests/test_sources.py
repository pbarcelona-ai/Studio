"""M2: every story source (documents incl. RTF / ODT, ideas, pictures, comics, websites with SSRF protection, screenplays, media), the
project's source list with its rights tick, chunking, chapters from sources, and the format / products / styles step with its estimate."""
import io
import json
import socket
import zipfile

import pytest

import book_formats
import production
import sources as src

FOUNTAIN = """Title: The Lamp
Author: Me

INT. KITCHEN - NIGHT

Rain on the window. MARA (30s) lights a lamp.

MARA
(whispering)
Is anyone there?

EXT. GARDEN - CONTINUOUS

The lamp swings in the dark.

CUT TO:

.THE CELLAR

Silence.
"""

FDX = b"""<?xml version="1.0" encoding="UTF-8"?><FinalDraft DocumentType="Script"><Content>
<Paragraph Type="Scene Heading"><Text>INT. KITCHEN - NIGHT</Text></Paragraph>
<Paragraph Type="Action"><Text>Rain. </Text><Text>Mara lights a lamp.</Text></Paragraph>
<Paragraph Type="Character"><Text>MARA (V.O.)</Text></Paragraph>
<Paragraph Type="Parenthetical"><Text>(quietly)</Text></Paragraph>
<Paragraph Type="Dialogue"><Text>Is anyone there?</Text></Paragraph>
<Paragraph Type="Scene Heading"><Text>ext. garden - day</Text></Paragraph>
<Paragraph Type="Transition"><Text>CUT TO:</Text></Paragraph>
</Content></FinalDraft>"""

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 3000


def make_odt(path, paras):
    with zipfile.ZipFile(path, "w") as z:
        body = "".join(f'<text:h text:outline-level="1">{t}</text:h>' if h else f"<text:p>{t}</text:p>" for h, t in paras)
        z.writestr("content.xml", '<?xml version="1.0"?><office:document-content xmlns:office="urn:oasis:names:tc:opendocument:xmlns:office:1.0" '
                   f'xmlns:text="urn:oasis:names:tc:opendocument:xmlns:text:1.0"><office:body><office:text>{body}</office:text></office:body></office:document-content>')


class TestFormats:
    def test_rtf(self, tmp_path):
        bs = chr(92)
        rtf = "{" + bs + "rtf1" + bs + "ansi{" + bs + "fonttbl{" + bs + "f0 Arial;}}{" + bs + "*" + bs + "generator x;}" + bs + "f0 Once upon a time " + bs + "b a fox" + bs + \
            "b0  went to the caf" + bs + "'e9." + bs + "par It cost 5 " + bs + "u8364? today." + bs + "par}"
        (tmp_path / "a.rtf").write_text(rtf, encoding="latin-1")
        b = book_formats.read_book(tmp_path / "a.rtf")
        assert b.kind == "rtf" and b.pages[0] == "Once upon a time a fox went to the café.\n\nIt cost 5 € today."
        (tmp_path / "bad.rtf").write_text("not rtf at all here")
        with pytest.raises(book_formats.BookReadError, match="not an RTF"):
            book_formats.read_book(tmp_path / "bad.rtf")

    def test_odt_with_chapters(self, tmp_path):
        paras = []
        for n in range(1, 4):
            paras += [(True, f"Chapter {n}"), (False, f"The story of part {n} goes on for a few words here.")]
        make_odt(tmp_path / "b.odt", paras)
        b = book_formats.read_book(tmp_path / "b.odt")
        assert b.kind == "odt" and [t for t, _ in b.sections] == ["Chapter 1", "Chapter 2", "Chapter 3"]


class TestAdapters:
    def test_idea(self):
        d = src.from_idea("  A lighthouse keeper finds a door in the sea.  ")
        assert d.kind == "idea" and d.title == "A lighthouse keeper finds a door" and d.text.endswith("sea.")
        with pytest.raises(src.SourceError):
            src.from_idea("   ")

    def test_document_and_a_screenplay_in_disguise(self, tmp_path):
        (tmp_path / "story.txt").write_text("It was a dark night. " * 30)
        d = src.from_file(tmp_path / "story.txt")
        assert d.kind == "document" and d.metadata["format"] == "text"
        (tmp_path / "script.txt").write_text(FOUNTAIN.replace(".THE CELLAR", "INT. CELLAR - NIGHT"))
        assert src.from_file(tmp_path / "script.txt").kind == "screenplay"

    def test_fountain(self, tmp_path):
        scenes = src.parse_fountain(FOUNTAIN)
        assert [s["heading"] for s in scenes] == ["INT. KITCHEN - NIGHT", "EXT. GARDEN - CONTINUOUS", "THE CELLAR"]
        kinds = [(e["type"], e.get("character", "")) for e in scenes[0]["elements"]]
        assert kinds == [("action", ""), ("character", ""), ("parenthetical", "MARA"), ("dialogue", "MARA")]
        assert scenes[1]["elements"][-1] == {"type": "transition", "text": "CUT TO:"}
        (tmp_path / "s.fountain").write_text(FOUNTAIN)
        d = src.from_file(tmp_path / "s.fountain")
        assert d.kind == "screenplay" and d.metadata["scene_count"] == 3 and "1  INT. KITCHEN - NIGHT" in d.text and "\t\t\tMARA" in d.text

    def test_fdx(self, tmp_path):
        scenes = src.parse_fdx(FDX)
        assert [s["heading"] for s in scenes] == ["INT. KITCHEN - NIGHT", "EXT. GARDEN - DAY"]
        assert scenes[0]["elements"][0]["text"] == "Rain. Mara lights a lamp." and scenes[0]["elements"][3] == {"type": "dialogue", "text": "Is anyone there?", "character": "MARA"}
        with pytest.raises(src.SourceError):
            src.parse_fdx(b'<!DOCTYPE x [<!ENTITY a "b">]><x/>')

    def test_pictures_are_checked(self, tmp_path):
        (tmp_path / "a.png").write_bytes(PNG)
        (tmp_path / "fake.jpg").write_bytes(b"not a picture")
        assert src.from_pictures([tmp_path / "a.png"], comic=True).kind == "comic"
        with pytest.raises(src.SourceError, match="not a picture"):
            src.from_pictures([tmp_path / "fake.jpg"])
        with pytest.raises(src.SourceError, match="cannot be used"):
            src.from_file(tmp_path / "x.exe")

    def test_media_kept_for_later(self, tmp_path):
        (tmp_path / "clip.mp4").write_bytes(b"\x00" * 100)
        d = src.from_file(tmp_path / "clip.mp4")
        assert d.kind == "media" and d.metadata["transcribed"] is False


class TestStore:
    def test_rights_list_remove_and_limits(self, tmp_path, monkeypatch):
        with pytest.raises(src.SourceError, match="right to use"):
            src.store(tmp_path, src.from_idea("an idea"), agreed=False)
        e = src.store(tmp_path, src.from_idea("an idea about a fox", "Fox"), agreed=True)
        assert e["id"] == "s001" and e["rights"]["agreed"] and e["rights"]["at"] and src.load_index(tmp_path)[0]["title"] == "Fox"
        (tmp_path / "p.png").write_bytes(PNG)
        e2 = src.store(tmp_path, src.from_pictures([tmp_path / "p.png"]), agreed=True, files=[tmp_path / "p.png"])
        assert e2["id"] == "s002" and e2["images"] == ["sources/s002/p.png"] and not e2["described"] and (tmp_path / "sources/s002/p.png").is_file()
        assert src.summary(tmp_path)["needs_description"] == ["s002"]
        src.remove(tmp_path, "s001")
        assert [s["id"] for s in src.load_index(tmp_path)] == ["s002"] and not (tmp_path / "sources/s001").exists()
        assert src.store(tmp_path, src.from_idea("again"), agreed=True)["id"] == "s003"
        monkeypatch.setattr(src, "MAX_WORDS", 5)
        with pytest.raises(src.SourceError, match="at most"):
            src.store(tmp_path, src.from_idea("one two three four five six"), agreed=True)
        with pytest.raises(src.SourceError):
            src.remove(tmp_path, "s999")

    def test_chunks(self):
        text = "\n\n".join(f"Paragraph {i} " + "word " * 98 for i in range(30))          # 3,000 words
        parts = src.chunks(text, max_tokens=1330, overlap_tokens=133)                    # ~1000 words, ~100 overlap
        assert 3 <= len(parts) <= 5 and all(src.words(p) <= 1100 for p in parts)
        assert parts[1].split()[:5] == parts[0].split()[-100:][:5]                         # each piece starts with the end of the one before
        assert src.chunks("x " * 5000, max_tokens=1330, overlap_tokens=0)[0].count("x") == 1000

    def test_mixed_sources_become_chapters(self, tmp_path):
        (tmp_path / "b.odt").parent.mkdir(exist_ok=True)
        make_odt(tmp_path / "b.odt", [x for n in range(1, 4) for x in ((True, f"Chapter {n}"), (False, f"Part {n} of the story is told here in words."))])
        src.store(tmp_path, src.from_file(tmp_path / "b.odt"), agreed=True)
        src.store(tmp_path, src.from_idea("A new ending where the fox wins.", "New ending"), agreed=True)
        (tmp_path / "s.fountain").write_text(FOUNTAIN)
        src.store(tmp_path, src.from_file(tmp_path / "s.fountain"), agreed=True)
        assert src.write_chapters(tmp_path) == 3 + 1 + 3
        idx = json.loads((tmp_path / "chapters.json").read_text())
        assert idx["method"] == "sources" and [c["title"] for c in idx["chapters"]][:4] == ["Chapter 1", "Chapter 2", "Chapter 3", "New ending"]
        merged = (tmp_path / "source_text.txt").read_text()
        assert "=== SOURCE s002 (idea: New ending) ===" in merged and "=== SOURCE s003 (screenplay" in merged
        assert "sections.json" in {p.name for p in (tmp_path / "sources" / "s001").iterdir()} and "section_text" not in json.dumps(src.load_index(tmp_path))

    def test_no_text_yet(self, tmp_path):
        (tmp_path / "p.png").write_bytes(PNG)
        src.store(tmp_path, src.from_pictures([tmp_path / "p.png"]), agreed=True, files=[tmp_path / "p.png"])
        with pytest.raises(src.SourceError, match="Describe"):
            src.write_chapters(tmp_path)


class TestDescribe:
    def test_pictures_and_comics(self, tmp_path):
        for n in (1, 2):
            (tmp_path / f"p{n}.png").write_bytes(PNG)
        src.store(tmp_path, src.from_pictures([tmp_path / "p1.png"]), agreed=True, files=[tmp_path / "p1.png"])
        src.store(tmp_path, src.from_pictures([tmp_path / "p2.png"], comic=True), agreed=True, files=[tmp_path / "p2.png"])
        calls = []

        def llm(prompt, system, engine, validate, image):
            calls.append((str(system)[:40], image))
            if "comic" in prompt:
                d = {"panels": [{"n": 1, "text": "Help!", "action": "A fox falls"}], "story": "The fox falls.", "characters": [{"name": "Fox", "look": "red"}]}
            else:
                d = {"characters": [{"name": "Girl", "look": "yellow coat"}], "setting": "a pier", "mood": "lonely", "story": "She waits for a boat."}
            validate(d)
            return d
        sysf = lambda role, pdir, step: f"[{role}] {step}"                                # noqa: E731
        e = src.describe(tmp_path, "s001", llm, sysf)
        assert e["described"] and "She waits for a boat." in src.document(tmp_path, "s001").text and e["metadata"]["characters"][0]["name"] == "Girl"
        src.describe(tmp_path, "s002", llm, sysf)
        assert 'Panel 1: A fox falls — "Help!"' in src.document(tmp_path, "s002").text
        assert all(c[0].startswith("[story_analyst]") for c in calls) and calls[0][1].endswith("p1.png")
        with pytest.raises(ValueError):
            src._check_description({"story": ""})
        src.store(tmp_path, src.from_idea("x"), agreed=True)
        with pytest.raises(src.SourceError, match="only pictures"):
            src.describe(tmp_path, "s003", llm, sysf)


class TestWebsites:
    @pytest.mark.parametrize("ip", ["127.0.0.1", "10.0.0.5", "192.168.1.1", "169.254.169.254", "::1", "fd00::1", "::ffff:127.0.0.1", "0.0.0.0", "224.0.0.1"])
    def test_private_addresses_are_refused(self, monkeypatch, ip):
        fam = socket.AF_INET6 if ":" in ip else socket.AF_INET
        monkeypatch.setattr(socket, "getaddrinfo", lambda *a, **k: [(fam, socket.SOCK_STREAM, 6, "", (ip, 80))])
        with pytest.raises(src.SourceError, match="private or internal"):
            src.safe_get("http://evil.example/")

    def test_one_bad_address_among_good_ones_is_refused(self, monkeypatch):
        monkeypatch.setattr(socket, "getaddrinfo", lambda *a, **k: [(socket.AF_INET, 1, 6, "", ("93.184.216.34", 80)), (socket.AF_INET, 1, 6, "", ("10.1.1.1", 80))])
        with pytest.raises(src.SourceError, match="private"):
            src.safe_get("http://mixed.example/")

    @pytest.mark.parametrize("url", ["file:///etc/passwd", "ftp://x.org/a", "gopher://x", "http://user:pw@x.org/", "javascript:alert(1)", "http:///nohost"])
    def test_only_plain_http_and_https(self, url):
        with pytest.raises(src.SourceError):
            src.check_url(url)

    def test_article_extraction(self):
        page = """<html><head><title>Site</title><meta property="og:title" content="The Fox Tale"></head><body>
          <nav><p>Home About Contact Subscribe to our newsletter today please now</p></nav>
          <article><h1>The Fox Tale</h1><p>""" + "The fox ran through the snow at dawn and stopped. " * 6 + """</p>
          <img src="/img/fox.jpg" alt="a fox"><img src="/logo.png"><p>""" + "Then the river froze and the fox crossed it slowly. " * 4 + """</p></article>
          <footer><p>Copyright 2026 all rights reserved by the company and partners.</p></footer><script>var x = 1;</script></body></html>"""
        title, text, imgs = src.extract_article(page, "https://stories.example/tales/fox")
        assert title == "The Fox Tale" and "fox ran through the snow" in text and "newsletter" not in text and "Copyright" not in text and "var x" not in text
        assert imgs == [("https://stories.example/img/fox.jpg", "a fox")]

    def test_from_url_with_robots_and_pictures(self, tmp_path):
        page = "<html><body><article><p>" + "A long story about a fox in the snow at night. " * 10 + '</p><img src="a.png"></article></body></html>'
        got = []

        def get(url, limit=0):
            got.append(url)
            if url.endswith("/robots.txt"):
                return url, "text/plain", b"User-agent: *\nDisallow: /private/\n"
            if url.endswith("a.png"):
                return url, "image/png", PNG
            return url, "text/html; charset=utf-8", page.encode()
        doc, files = src.from_url("https://s.example/tale", tmp_path, get=get)
        assert doc.kind == "website" and doc.metadata["url"] == "https://s.example/tale" and len(files) == 1 and files[0].read_bytes() == PNG
        with pytest.raises(src.SourceError, match="robots.txt"):
            src.from_url("https://s.example/private/x", tmp_path, get=get)
        with pytest.raises(src.SourceError, match="not a web page"):
            src.from_url("https://s.example/x.pdf", tmp_path, get=lambda u, limit=0: (u, "text/plain", b"User-agent: *\nAllow: /") if "robots" in u else (u, "application/pdf", b"%PDF"))

    def test_redirect_to_a_private_address_is_refused(self, monkeypatch):
        class Conn:
            def __init__(self, host, ip, port, timeout):
                self.host = host

            def request(self, *a, **k):
                pass

            def getresponse(self):
                r = io.BytesIO(b"")
                r.status, r.reason = 302, "Found"
                r.getheader = lambda k, d=None: "http://inside.example/admin" if k == "Location" else d
                return r

            def close(self):
                pass
        addrs = {"outside.example": "93.184.216.34", "inside.example": "10.0.0.1"}
        monkeypatch.setattr(socket, "getaddrinfo", lambda host, *a, **k: [(socket.AF_INET, 1, 6, "", (addrs[host], 80))])
        monkeypatch.setattr(src, "_PinnedHTTP", Conn)
        with pytest.raises(src.SourceError, match="private"):
            src.safe_get("http://outside.example/")


class TestProduction:
    def test_defaults_dependencies_and_notes(self):
        d, notes = production.normalise({"products": ["marketing"], "styles": [{"id": "claymation"}, {"id": "anime"}], "master": "anime"})
        assert d["products"] == ["screenplay", "storyboard", "film", "marketing"] and len(notes) == 2 and "trailer" in notes[0]
        assert [s["id"] for s in d["styles"]] == ["anime", "claymation"] and d["master"] == "anime"
        d2, n2 = production.normalise({"styles": []})
        assert d2["master"] == "realistic" and "Realistic" in n2[0]

    @pytest.mark.parametrize("bad", [{"aspect": "2:1"}, {"rating": "18"}, {"tier": "best"}, {"target_minutes": "nan"}, {"target_minutes": 0},
                                     {"styles": [{"id": "../x"}]}, {"styles": [{"id": f"s{i}x", "text": "t"} for i in range(9)]}])
    def test_bad_values(self, bad):
        with pytest.raises(ValueError):
            production.normalise(bad)

    def test_custom_style_and_estimate(self):
        d, _ = production.normalise({"products": ["screenplay", "storyboard", "film"], "target_minutes": 2, "tier": "draft",
                                     "styles": [{"id": "realistic"}, {"id": "custom_ink", "name": "My ink", "text": "brush ink on rice paper"}]})
        assert d["styles"][1] == {"id": "custom_ink", "name": "My ink", "text": "brush ink on rice paper"}
        e = production.estimate(d)
        assert e["shots"] == 30 and e["styles"][0]["pictures"] == 30 and e["styles"][0]["clips"] == 30 and e["styles"][0]["calls"] == 78
        assert e["dollars"] == 0 and e["gpu_hours"] > 0 and e["styles"][1]["name"] == "My ink"
        assert production.estimate(d, paid=True)["dollars"] > 0

    def test_save_and_load_follow_the_recipe(self, tmp_path):
        import crew
        crew.set_recipe(tmp_path, "vertical_microdrama")
        d = production.load(tmp_path)
        assert d["recipe"] == "vertical_microdrama" and d["aspect"] == "9:16"
        production.save(tmp_path, {**d, "styles": [{"id": "anime"}], "rating": "8"})
        assert production.load(tmp_path)["rating"] == "8"
        crew.set_recipe(tmp_path, "feature_film")
        d3 = production.load(tmp_path)
        assert d3["aspect"] == "16:9" and d3["styles"] == [{"id": "anime"}]                  # the new recipe's settings, the styles kept
        assert production.estimate(d3)["seconds_per_shot"] == 4.0 and production.estimate(d)["seconds_per_shot"] == 2.5


class TestRoutes:
    def test_sources_and_production_over_http(self, server, book):
        st, j = server.api("POST", "/api/source_add", {"project": "demo", "kind": "idea", "text": "A fox finds a door.", "rights": True})
        assert st == 200 and j["added"]["kind"] == "idea"
        st, j = server.api("POST", "/api/source_add", {"project": "demo", "kind": "idea", "text": "No tick."})
        assert st == 400 and "right" in j["error"]
        st, j = server.api("POST", "/api/source_upload?project=demo&filename=s.fountain&rights=1", raw=FOUNTAIN.encode(),
                           headers={"Content-Type": "application/octet-stream"})
        assert st == 200 and j["added"]["kind"] == "screenplay" and j["total_words"] > 0
        st, j = server.api("POST", "/api/source_upload?project=demo&filename=s.fountain", raw=b"x", headers={"Content-Type": "application/octet-stream"})
        assert st == 400 and "right" in j["error"]
        st, j = server.api("POST", "/api/source_upload?project=demo&filename=run.exe&rights=1", raw=b"x", headers={"Content-Type": "application/octet-stream"})
        assert st == 400
        st, j = server.api("GET", "/api/sources?project=demo")
        assert [s["kind"] for s in j["sources"]] == ["idea", "screenplay"]
        st, j = server.api("POST", "/api/sources_to_chapters", {"project": "demo"})
        assert st == 200 and j["chapters"] == 4
        st, j = server.api("POST", "/api/source_remove", {"project": "demo", "id": "s001"})
        assert st == 200 and len(j["sources"]) == 1
        st, j = server.api("POST", "/api/source_add", {"project": "brand_new", "kind": "idea", "text": "Start from one line.", "rights": True})
        assert st == 200 and (book.parent / "brand_new" / "sources" / "index.json").is_file()
        st, j = server.api("GET", "/api/production?project=demo")
        assert st == 200 and j["settings"]["products"][0] == "screenplay" and j["catalog"]["styles"][1]["id"] == "claymation"
        st, j = server.api("POST", "/api/production", {"project": "demo", "products": ["animatic"], "styles": [{"id": "noir"}], "target_minutes": 5})
        assert st == 200 and "storyboard" in j["settings"]["products"] and j["notes"] and j["estimate"]["shots"] == 75
        st, j = server.api("POST", "/api/production", {"project": "demo", "aspect": "7:1"})
        assert st == 400
