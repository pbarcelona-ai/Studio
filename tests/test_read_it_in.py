"""M3: READ IT IN (Section 5) end to end with a scripted crew, resume, the two-pass coverage, thin sources, an existing screenplay, the
critique loop, the hand-over to the Studio's plan + screenplay, the screenplay exports and the routes."""
import json
import zipfile

import pytest

import adaptation
import read_it_in as ri
import screenplay
import screenplay_export as sx
import sources as src

STORY = ("Mara keeps the lighthouse on the black rock. Every night she climbs the stairs and lights the lamp. "
         "One winter a door appears in the sea at low tide. She rows out to it alone. Behind the door is her brother, who drowned ten years ago. "
         "He asks her to come with him. She must choose between the light and her brother. ")


def scripted(pdir, log):
    """The fake crew, recording who was asked what."""
    fake = ri.fake_ask(pdir)

    def ask(prompt, role, step, validate):
        log.append((role, step))
        return fake(prompt, role, step, validate)
    return ask


@pytest.fixture
def idea_book(tmp_path):
    src.store(tmp_path, src.from_idea(STORY, "The Door in the Sea"), True)
    return tmp_path


class TestPipeline:
    def test_a_whole_run_from_an_idea(self, idea_book):
        log, said = [], []
        out = ri.ReadItIn(idea_book, scripted(idea_book, log), said.append).run()
        roles = [r for r, _ in log]
        assert roles[:2] == ["story_analyst", "development_executive"]                         # thin source: the story is grown first
        assert roles.count("screenwriter") >= 6 and "script_doctor" in roles and "director" in roles
        assert out["scenes"] == 3 and out["rounds"] == 2 and out["scores"] == {"script_doctor": 8, "director": 8}
        assert said[0].startswith("[1/9]") and any("writing act 2 of 3" in s for s in said) and said[-1].startswith("Done:")
        rd = idea_book / "readin"
        for f in ("coverage.json", "development.json", "plan.json", "beats.json", "treatment.md", "screenplay.json", "critique.json", "summary.json"):
            assert (rd / f).is_file(), f
        plan = adaptation.load(idea_book)
        assert plan["source"] == "read_it_in" and [s["id"] for s in plan["scenes"]] == ["S001", "S002", "S003"]
        sc = screenplay.load_scene(idea_book, "S001")
        assert sc["heading"].startswith("INT.") and sc["elements"][1] == {"type": "dialogue", "text": "We go now.", "character": "MARA"}
        blocks = json.loads((rd / "screenplay.json").read_text())["scenes"]
        assert set(blocks[0]["block"]) == set(ri.BLOCK_KEYS)

    def test_a_second_run_carries_on_and_a_change_starts_again(self, idea_book):
        ri.ReadItIn(idea_book, scripted(idea_book, [])).run()
        log = []
        ri.ReadItIn(idea_book, scripted(idea_book, log)).run()
        assert log == []                                                                        # nothing changed: no AI calls at all
        src.store(idea_book, src.from_idea("A new ending: she brings him home.", "Ending"), True)
        ri.ReadItIn(idea_book, scripted(idea_book, log)).run()
        assert log and log[0][0] == "story_analyst"
        log.clear()
        ri.ReadItIn(idea_book, scripted(idea_book, log)).run(force=True)
        assert log

    def test_a_stopped_screenplay_carries_on_by_act(self, idea_book):
        calls = []
        fake = ri.fake_ask(idea_book)

        def flaky(prompt, role, step, validate):
            calls.append(step)
            if step == "read it in: screenplay act 2" and calls.count(step) == 1:
                raise RuntimeError("the AI is busy")
            return fake(prompt, role, step, validate)
        with pytest.raises(RuntimeError):
            ri.ReadItIn(idea_book, flaky).run()
        before = len(calls)
        ri.ReadItIn(idea_book, flaky).run()
        again = calls[before:]
        assert "read it in: screenplay act 1" not in again and "read it in: screenplay act 2" in again and "read it in: coverage" not in again

    def test_a_long_book_is_read_in_two_passes(self, tmp_path, monkeypatch):
        chapters = []
        for n in range(1, 5):
            body = f"Chapter {n} begins. " + STORY * 10
            (tmp_path / "chapters").mkdir(exist_ok=True)
            (tmp_path / "chapters" / f"chapter-{n:03d}.txt").write_text(body)
            chapters.append({"n": n, "title": f"Chapter {n}"})
        (tmp_path / "chapters.json").write_text(json.dumps({"chapters": chapters}))
        monkeypatch.setattr(ri, "TWO_PASS_TOKENS", 500)
        log, said = [], []
        ri.ReadItIn(tmp_path, scripted(tmp_path, log), said.append).run()
        assert [s for _, s in log].count("read it in: chapter summary") == 4
        assert "[2/9] Your story analyst is reading chapter 3 of 4" in said
        assert "development_executive" not in [r for r, _ in log]                              # a real book is not thin
        assert len(json.loads((tmp_path / "readin" / "summaries.json").read_text())) == 4
        log.clear()
        (tmp_path / "readin" / "state.json").unlink()
        ri.ReadItIn(tmp_path, scripted(tmp_path, log), said.append).run()
        assert "read it in: chapter summary" not in [s for _, s in log]                        # the summaries are cached

    def test_an_existing_screenplay_is_only_critiqued(self, tmp_path):
        from test_sources import FOUNTAIN
        (tmp_path / "s.fountain").write_text(FOUNTAIN.replace(".THE CELLAR", "INT. CELLAR - NIGHT"))
        src.store(tmp_path, src.from_file(tmp_path / "s.fountain"), True)
        log = []
        out = ri.ReadItIn(tmp_path, scripted(tmp_path, log)).run()
        steps = [s for _, s in log]
        assert not any("beat sheet" in s or "treatment" in s or "screenplay act" in s for s in steps) and "read it in: coverage" in steps
        assert out["scenes"] == 3 and screenplay.load_scene(tmp_path, "S002")["heading"] == "EXT. GARDEN - CONTINUOUS"

    def test_the_critique_stops_when_both_are_happy(self, idea_book):
        fake = ri.fake_ask(idea_book)

        def happy(prompt, role, step, validate):
            if "critique" in step:
                d = {"score": 9, "notes": []}
                validate(d)
                return d
            return fake(prompt, role, step, validate)
        assert ri.ReadItIn(idea_book, happy).run()["rounds"] == 1

    def test_nothing_to_read_and_undescribed_pictures(self, tmp_path):
        with pytest.raises(ri.ReadError, match="nothing to read"):
            ri.ReadItIn(tmp_path, ri.fake_ask(tmp_path)).run()
        (tmp_path / "p.png").write_bytes(b"\x89PNG\r\n\x1a\n" + b"\0" * 3000)
        src.store(tmp_path, src.from_idea("an idea"), True)
        src.store(tmp_path, src.from_pictures([tmp_path / "p.png"]), True, [tmp_path / "p.png"])
        with pytest.raises(ri.ReadError, match="Describe"):
            ri.ReadItIn(tmp_path, ri.fake_ask(tmp_path)).run()

    def test_the_cli_with_the_fake_engine(self, fake_root, capsys):
        d = fake_root / "projects" / "books" / "door"
        src.store(d, src.from_idea(STORY), True)
        assert ri.main(["door", "--engine", "fake"]) == 0 and "Done:" in capsys.readouterr().out
        assert ri.main(["no_such_book", "--engine", "fake"]) == 1


class TestValidators:
    @pytest.mark.parametrize("fn,bad", [
        (ri.check_coverage, {"logline": "x", "genre": "g", "tone": "t", "themes": ["a"], "characters": [{"name": "A"}], "key_events": ["e"], "length": "long"}),
        (ri.check_plan, {"kept": [{"event": "x"}], "ending": "e"}),
        (ri.beats_checker(False), {"acts": [{"name": "A", "share": 1, "beats": [{"name": "Opening image", "description": "d"}]}]}),
        (ri.beats_checker(True), {"acts": [{"name": "Ep 1", "share": 1, "beats": [{"name": "Hook", "description": "d"}]}]}),
        (ri.check_treatment, {"treatment": "too short"}),
        (ri.check_scenes, {"scenes": [{"heading": "KITCHEN", "elements": [{"type": "action", "text": "x"}], "block": {}}]}),
        (ri.check_scenes, {"scenes": [{"heading": "INT. KITCHEN - DAY", "elements": [{"type": "action", "text": "x"}], "block": {"characters": []}}]}),
        (ri.check_notes, {"score": 11, "notes": []}),
        (ri.check_notes, {"score": 5, "notes": [{"scene": 1}]}),
    ])
    def test_bad_replies_are_sent_back(self, fn, bad):
        with pytest.raises(ValueError):
            fn(bad)


class TestExports:
    @pytest.fixture
    def written(self, idea_book):
        ri.ReadItIn(idea_book, ri.fake_ask(idea_book)).run()
        return idea_book

    def test_every_format(self, written):
        made = sx.export(written)
        assert sorted(p.name for p in made) == ["readin_notes.pdf", "screenplay.docx", "screenplay.fdx", "screenplay.fountain", "screenplay.pdf"]
        ex = written / "exports"
        fountain = (ex / "screenplay.fountain").read_text()
        assert fountain.startswith("Title: ") and "#1#" in fountain and "\nMARA\nWe go now.\n" in fountain
        back = src.parse_fountain(fountain)
        assert [s["heading"].split(" #")[0] for s in back] == [s["heading"] for s in sx.load(written)[1]]
        fdx_back = src.parse_fdx((ex / "screenplay.fdx").read_bytes())
        assert [s["heading"] for s in fdx_back] == [s["heading"] for s in sx.load(written)[1]]
        with zipfile.ZipFile(ex / "screenplay.docx") as z:
            doc, styles = z.read("word/document.xml").decode(), z.read("word/styles.xml").decode()
        assert "Courier New" in styles and 'w:left="2160"' in doc and "We go now." in doc
        assert (ex / "screenplay.pdf").read_bytes().startswith(b"%PDF-1.4") and (ex / "readin_notes.pdf").read_bytes().rstrip().endswith(b"%%EOF")

    def test_the_pdf_reads_back(self, written):
        pypdf = pytest.importorskip("pypdf")
        sx.export(written, ("pdf",))
        r = pypdf.PdfReader(str(written / "exports" / "screenplay.pdf"))
        assert len(r.pages) == 2 and "WRITTEN BY" in r.pages[0].extract_text().upper()
        body = r.pages[1].extract_text()
        assert "1 INT. PLACE 1 - DAY 1" in body and "MARA" in body

    def test_pages_break_cleanly(self):
        scenes = [{"heading": f"INT. ROOM {i} - DAY", "elements": [{"type": "action", "text": "word " * 200}, {"type": "dialogue", "character": "A", "text": "hi", "note": "softly"}]}
                  for i in range(1, 9)]
        pages = sx.paginate(sx.page_lines(scenes))
        assert len(pages) > 2 and all(len(p) <= sx.LINES_PER_PAGE for p in pages)
        for p in pages:
            assert p[-1][2] != "heading" and p[-1][2] != "cue"                             # never a heading or a cue alone at the foot
        assert max(len(t) for p in pages for x, t, k in p if k == "action") <= sx.ACTION[1]
        assert sx.to_pdf("Title (with) back\\slash", scenes).count(b"/Type /Page ") == len(pages) + 1

    def test_no_screenplay_yet(self, tmp_path):
        with pytest.raises(ValueError, match="Read it in"):
            sx.export(tmp_path)


class TestRoutes:
    def test_step_results_exports_and_download(self, server, book):
        from studio_app import readin_routes
        step = readin_routes.readin_step({"project": "demo", "engine": "fake", "force": True})
        assert step["argv"] == ["python3", "read_it_in.py", "demo", "--engine", "fake", "--force"]
        assert readin_routes.readin_step({"project": "demo", "engine": "claude", "claude_model": "opus"})["argv"][3:] == ["--engine", "claude", "--model", "opus"]
        st, j = server.api("GET", "/api/readin?project=demo")
        assert st == 200 and j["script"] == "" and j["exports"] == []
        st, j = server.api("POST", "/api/readin_export", {"project": "demo"})
        assert st == 400 and "Read it in" in j["error"]
        src.store(book, src.from_idea(STORY), True)
        ri.ReadItIn(book, ri.fake_ask(book)).run()
        st, j = server.api("GET", "/api/readin?project=demo")
        assert j["summary"]["scenes"] == 3 and j["coverage"]["logline"] and "INT. PLACE 1 - DAY" in j["script"] and len(j["critique"]) == 2
        st, j = server.api("POST", "/api/readin_export", {"project": "demo", "formats": ["pdf", "fountain"]})
        assert st == 200 and [e["name"] for e in j["exports"]] == ["screenplay.pdf", "screenplay.fountain"]
        st, j = server.api("POST", "/api/readin_export", {"project": "demo", "formats": ["exe"]})
        assert st == 400
        from conftest import TOKEN
        status, hdrs, body = server.request("GET", f"/download/demo/exports/screenplay.pdf?t={TOKEN}", headers={"X-Studio-Token": TOKEN})
        assert status == 200 and body.startswith(b"%PDF") and "attachment" in hdrs.get("Content-Disposition", "")
        status, _, _ = server.request("GET", "/download/demo/exports/screenplay.pdf")
        assert status == 403
        status, _, _ = server.request("GET", "/download/demo/demo.json", headers={"X-Studio-Token": TOKEN})
        assert status == 404                                                                    # only files in exports/, of the download kinds
