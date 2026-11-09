"""book_ingest.py (text input) and migrate_layout.py (old flat layout -> new)."""
import json
import sys

import pytest

import migrate_layout as ml


def chapters_text(n=4, words=500):
    return "\n\n".join(f"CHAPTER {i}\n\n" + " ".join(["word"] * words) for i in range(1, n + 1))


class TestIngest:
    def test_splits_on_chapter_headings(self, fake_root, run_script, tmp_path):
        src = tmp_path / "b.txt"
        src.write_text("Front matter here.\n\n" + chapters_text())
        code, out = run_script("book_ingest.py", "newbook", str(src))
        d = fake_root / "projects" / "books" / "newbook"
        idx = json.loads((d / "chapters.json").read_text())
        assert code is None and idx["method"] == "chapter" and [c["n"] for c in idx["chapters"]] == [1, 2, 3, 4] and "split by: chapter" in out
        assert (d / "front_matter.txt").read_text() == "Front matter here." and (d / "chapters" / "chapter-004.txt").read_text().startswith("word")
        assert (d / "source" / "b.txt").exists() and (d / "source_text.txt").exists()

    def test_roman_numerals_and_psalms(self, fake_root, run_script, tmp_path):
        src = tmp_path / "r.txt"
        src.write_text("\n\n".join(f"{r}\n\n" + " ".join(["w"] * 500) for r in ("I", "II", "III", "IV")))
        run_script("book_ingest.py", "romans", str(src))
        assert json.loads((fake_root / "projects" / "books" / "romans" / "chapters.json").read_text())["method"] == "roman"
        src.write_text("\n\n".join(f"PSALM {i}\n\n" + " ".join(["w"] * 300) for i in range(1, 5)))
        run_script("book_ingest.py", "psalms", str(src))
        assert json.loads((fake_root / "projects" / "books" / "psalms" / "chapters.json").read_text())["method"] == "psalm"

    def test_no_headings_cuts_sections(self, fake_root, run_script, tmp_path):
        src = tmp_path / "p.txt"
        src.write_text("\n\n".join(" ".join(["para"] * 100) for _ in range(12)))
        code, out = run_script("book_ingest.py", "plain", str(src), "--section-words", "400")
        idx = json.loads((fake_root / "projects" / "books" / "plain" / "chapters.json").read_text())
        assert idx["method"] == "sections" and len(idx["chapters"]) == 3 and idx["chapters"][0]["title"] == "Section 1" and "no chapter headings" in out

    def test_short_chapters_are_reported(self, fake_root, run_script, tmp_path):
        src = tmp_path / "s.txt"
        src.write_text(chapters_text(4, 500).replace("CHAPTER 3\n\n" + " ".join(["word"] * 500), "CHAPTER 3\n\nshort"))
        assert "chapters with under 40 words" in run_script("book_ingest.py", "shorty", str(src))[1]

    def test_errors(self, fake_root, run_script, tmp_path):
        assert "PDF not found" in run_script("book_ingest.py", "nobook", str(tmp_path / "missing.pdf"))[0]
        tiny = tmp_path / "t.txt"
        tiny.write_text("too few")
        assert "too short" in run_script("book_ingest.py", "tinybook", str(tiny))[0]

    def test_text_in_a_pdf_shape_is_rejected_when_scanned(self, fake_root, run_script, tmp_path):
        from pypdf import PdfWriter
        w = PdfWriter()
        w.add_blank_page(100, 100)
        pdf = tmp_path / "scan.pdf"
        with open(pdf, "wb") as f:
            w.write(f)
        assert "scanned" in run_script("book_ingest.py", "scanned", str(pdf))[0]


class TestMigrateLayout:
    @pytest.fixture()
    def old(self, tmp_path):
        root = tmp_path / "repo"
        p = root / "projects"
        (p / "adam_eve" / "references" / "adam").mkdir(parents=True)
        (p / "adam_eve" / "references" / "adam" / "ref_01.png").write_bytes(b"png")
        (p / "adam_eve" / "chapters.json").write_text("{}")
        (p / "char_adam").mkdir()
        (p / "char_adam" / "promptset.json").write_text("{}")
        (p / "xv").mkdir()
        (p / "xv" / "promptset.json").write_text("{}")
        (p / "mystery").mkdir()
        (root / "characters" / "main").mkdir(parents=True)
        (root / "characters" / "main" / "adam.json").write_text(json.dumps({"reference_images": ["projects/adam_eve/references/adam/ref_01.png"]}))
        (root / "scripts" / "projects" / "xv").mkdir(parents=True)
        (root / "scripts" / "projects" / "xv" / "stray.txt").write_text("s")
        (root / "scripts" / "projects" / "unknown").mkdir()
        return root

    def run(self, monkeypatch, capsys, root, *extra):
        monkeypatch.setattr(sys, "argv", ["migrate_layout.py", "--root", str(root), *extra])
        ml.main()
        return capsys.readouterr().out

    def test_dry_run_changes_nothing(self, old, monkeypatch, capsys):
        before = sorted(str(p) for p in old.rglob("*"))
        out = self.run(monkeypatch, capsys, old)
        assert "DRY RUN" in out and "run again with --apply" in out and "left alone (not a book or a prompt set): projects/mystery" in out
        assert sorted(str(p) for p in old.rglob("*")) == before

    def test_apply_moves_everything_and_rewrites_paths(self, old, monkeypatch, capsys):
        out = self.run(monkeypatch, capsys, old, "--apply")
        p = old / "projects"
        assert (p / "books" / "adam_eve" / "chapters.json").exists() and (p / "characters" / "char_adam" / "promptset.json").exists()
        assert (p / "prompts" / "xv" / "stray.txt").exists() and (p / "characters" / "main" / "references" / "adam" / "ref_01.png").exists()
        assert not (old / "characters").exists() and not (old / "scripts" / "projects" / "xv").exists()
        token = json.loads((p / "characters" / "main" / "adam.json").read_text())
        assert token["reference_images"] == ["projects/characters/main/references/adam/ref_01.png"] and "paths rewritten" in out
        assert "no matching project): scripts/projects/unknown" in out

    def test_running_again_is_a_no_op(self, old, monkeypatch, capsys):
        self.run(monkeypatch, capsys, old, "--apply")
        out = self.run(monkeypatch, capsys, old, "--apply")
        assert "0 move(s), 0 identical duplicate(s), 0 conflict(s), 0 file(s)" in out

    def test_duplicates_are_dropped_and_conflicts_kept(self, tmp_path):
        a, b, c, d = tmp_path / "a", tmp_path / "b", tmp_path / "c", tmp_path / "d"
        a.write_text("same"); b.write_text("same"); c.write_text("one"); d.write_text("two")
        m = ml.Mover(True)
        m.move(a, b)
        m.move(c, d)
        assert not a.exists() and c.exists() and d.read_text() == "two" and len(m.duplicates) == 1 and len(m.conflicts) == 1

    def test_rewrite_paths(self):
        assert ml.rewrite_paths("projects/xv/a", [("projects/xv/", "projects/prompts/xv/")]) == "projects/prompts/xv/a"
