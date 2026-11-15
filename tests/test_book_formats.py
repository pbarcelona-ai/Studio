"""book_formats.py: EPUB, DOCX, HTML and scanned-PDF input, and book_ingest.py on top of them."""
import json
import zipfile

import pytest

import book_formats as bf

PARA = " ".join(["word"] * 120)


def make_epub(path, chapters, extra_front=True):
    docs = []
    if extra_front:
        docs += [("Cover", "<h1>Cover</h1><p>x</p>"), ("Copyright", "<h1>Copyright</h1><p>All rights reserved.</p>")]
    docs += [(t, f"<h1>{t}</h1><p>{PARA}</p><p>{PARA}</p>") for t in chapters]
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("mimetype", "application/epub+zip")
        z.writestr("META-INF/container.xml", '<?xml version="1.0"?><container xmlns="urn:oasis:names:tc:opendocument:xmlns:container">'
                   '<rootfiles><rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/></rootfiles></container>')
        items = "".join(f'<item id="i{n}" href="c{n}.xhtml" media-type="application/xhtml+xml"/>' for n in range(len(docs)))
        refs = "".join(f'<itemref idref="i{n}"/>' for n in range(len(docs)))
        z.writestr("OEBPS/content.opf", f'<?xml version="1.0"?><package xmlns="http://www.idpf.org/2007/opf"><manifest>{items}</manifest><spine>{refs}</spine></package>')
        for n, (_, html) in enumerate(docs):
            z.writestr(f"OEBPS/c{n}.xhtml", f"<html><head><title>t</title></head><body>{html}</body></html>")


def make_docx(path, parts):
    """parts: list of (style or None, text)"""
    w = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
    paras = ""
    for style, text in parts:
        ppr = f'<w:pPr><w:pStyle w:val="{style}"/></w:pPr>' if style else ""
        paras += f"<w:p>{ppr}<w:r><w:t>{text}</w:t></w:r></w:p>"
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("word/document.xml", f'<?xml version="1.0"?><w:document xmlns:w="{w}"><w:body>{paras}</w:body></w:document>')


class TestEpub:
    def test_one_file_per_chapter_and_front_matter_is_set_aside(self, tmp_path):
        f = tmp_path / "b.epub"
        make_epub(f, ["The Storm", "The Calm", "The Return"])
        book = bf.read_book(f)
        assert book.kind == "epub" and [t for t, _ in book.sections] == ["The Storm", "The Calm", "The Return"]
        assert "Copyright" in book.front and "Cover" in book.front
        assert book.sections[0][1].startswith("word") and "The Storm" not in book.sections[0][1]

    def test_single_file_epub_splits_on_headings(self, tmp_path):
        f = tmp_path / "s.epub"
        body = "".join(f"<h2>Part {i}</h2><p>{PARA}</p>" for i in range(1, 5))
        with zipfile.ZipFile(f, "w") as z:
            z.writestr("META-INF/container.xml", '<container xmlns="urn:oasis:names:tc:opendocument:xmlns:container"><rootfiles><rootfile full-path="c.opf"/></rootfiles></container>')
            z.writestr("c.opf", '<package xmlns="http://www.idpf.org/2007/opf"><manifest><item id="a" href="a.html" media-type="text/html"/></manifest><spine><itemref idref="a"/></spine></package>')
            z.writestr("a.html", f"<body>{body}</body>")
        assert [t for t, _ in bf.read_book(f).sections] == [f"Part {i}" for i in range(1, 5)]

    def test_rejects_garbage_and_entities(self, tmp_path):
        bad = tmp_path / "bad.epub"
        bad.write_bytes(b"not a zip")
        with pytest.raises(bf.BookReadError, match="not a valid"):
            bf.read_book(bad)
        ent = tmp_path / "ent.epub"
        with zipfile.ZipFile(ent, "w") as z:
            z.writestr("META-INF/container.xml", '<!DOCTYPE x [<!ENTITY a "aaaa">]><container/>')
        with pytest.raises(bf.BookReadError, match="entity"):
            bf.read_book(ent)

    def test_oversized_member_is_refused(self, tmp_path, monkeypatch):
        f = tmp_path / "b.epub"
        make_epub(f, ["A", "B", "C"])
        monkeypatch.setattr(bf, "MAX_MEMBER", 50)
        with pytest.raises(bf.BookReadError, match="too large"):
            bf.read_book(f)


class TestDocx:
    def test_heading_styles_give_chapters(self, tmp_path):
        f = tmp_path / "b.docx"
        make_docx(f, [("Title", "My Book")] + [x for i in range(1, 4) for x in (("Heading1", f"Chapter {i}"), (None, PARA))])
        book = bf.read_book(f)
        assert book.kind == "docx" and [t for t, _ in book.sections] == ["Chapter 1", "Chapter 2", "Chapter 3"] and "My Book" in book.front

    def test_no_headings_gives_plain_text(self, tmp_path):
        f = tmp_path / "p.docx"
        make_docx(f, [(None, PARA), (None, PARA)])
        book = bf.read_book(f)
        assert book.sections is None and bf.words(book.pages[0]) == 240

    def test_missing_document_xml(self, tmp_path):
        f = tmp_path / "x.docx"
        with zipfile.ZipFile(f, "w") as z:
            z.writestr("hello.txt", "hi")
        with pytest.raises(bf.BookReadError, match="missing word/document.xml"):
            bf.read_book(f)


class TestHtml:
    def test_headings_split_and_scripts_are_ignored(self, tmp_path):
        f = tmp_path / "b.html"
        f.write_text("<html><head><title>T</title><script>var x='SECRET';</script></head><body>"
                     + "".join(f"<h2>Chapter {i}</h2><p>{PARA} &amp; more</p>" for i in range(1, 4)) + "</body></html>")
        book = bf.read_book(f)
        assert [t for t, _ in book.sections] == ["Chapter 1", "Chapter 2", "Chapter 3"] and "SECRET" not in book.pages[0] and "& more" in book.pages[0]

    def test_empty_page(self, tmp_path):
        f = tmp_path / "e.html"
        f.write_text("<html><body><script>x</script></body></html>")
        with pytest.raises(bf.BookReadError):
            bf.read_book(f)


def scanned_pdf(path, pages=3):
    from PIL import Image
    ims = [Image.new("RGB", (400, 500), "white") for _ in range(pages)]
    ims[0].save(path, "PDF", save_all=True, append_images=ims[1:])


class TestOcr:
    def test_image_only_pdf_is_read_with_the_engine(self, tmp_path):
        f = tmp_path / "scan.pdf"
        scanned_pdf(f, 3)
        seen = []
        book = bf.read_book(f, engine=lambda im: (seen.append(im.size) or " ".join(["recognised"] * 400)), progress=lambda m: None)
        assert book.ocr_pages == 3 and len(seen) == 3 and "recognised" in book.pages[1] and any("OCR" in n for n in book.notes)

    def test_no_engine_gives_install_hint(self, tmp_path, monkeypatch):
        f = tmp_path / "scan.pdf"
        scanned_pdf(f, 1)
        monkeypatch.setattr(bf, "find_ocr_engine", lambda: None)
        with pytest.raises(bf.BookReadError, match="scanned PDF.*no OCR engine"):
            bf.read_book(f)

    def test_ocr_switched_off_and_empty_result(self, tmp_path):
        f = tmp_path / "scan.pdf"
        scanned_pdf(f, 2)
        with pytest.raises(bf.BookReadError, match="switched off"):
            bf.read_book(f, ocr=False)
        with pytest.raises(bf.BookReadError, match="almost no words"):
            bf.read_book(f, engine=lambda im: "")

    def test_blank_page_without_pictures(self, tmp_path):
        from pypdf import PdfWriter
        w = PdfWriter()
        w.add_blank_page(100, 100)
        f = tmp_path / "blank.pdf"
        with open(f, "wb") as fh:
            w.write(fh)
        with pytest.raises(bf.BookReadError, match="no pictures"):
            bf.read_book(f, engine=lambda im: "text")

    def test_ocr_packages(self, tmp_path, monkeypatch):
        f = tmp_path / "scan.pdf"
        scanned_pdf(f, 2)
        monkeypatch.setattr(bf.shutil, "which", lambda n: None)
        assert bf.ocr_packages(f) == ["pillow", "rapidocr", "onnxruntime"]
        monkeypatch.setattr(bf.shutil, "which", lambda n: "/usr/bin/tesseract")
        assert bf.ocr_packages(f) == ["pillow"]
        assert bf.ocr_packages(tmp_path / "x.epub") == []
        junk = tmp_path / "junk.pdf"
        junk.write_bytes(b"%PDF")
        assert bf.ocr_packages(junk) == ["pillow"]

    def test_tesseract_engine_runs_the_program(self, tmp_path, monkeypatch):
        from PIL import Image
        calls = []

        class R:
            returncode, stdout, stderr = 0, "hello text", ""
        monkeypatch.setattr(bf.subprocess, "run", lambda argv, **kw: (calls.append(argv) or R()))
        out = bf._tesseract_engine("/usr/bin/tesseract")(Image.new("RGB", (10, 10)))
        assert out == "hello text" and calls[0][0] == "/usr/bin/tesseract" and calls[0][2:4] == ["stdout", "-l"]


class TestIngestFormats:
    def test_epub_ingest_uses_the_books_own_chapters(self, fake_root, run_script, tmp_path):
        f = tmp_path / "novel.epub"
        make_epub(f, ["The Storm", "The Calm", "The Return"])
        code, out = run_script("book_ingest.py", "novel", str(f))
        d = fake_root / "projects" / "books" / "novel"
        idx = json.loads((d / "chapters.json").read_text())
        assert code is None and idx["method"] == "structure" and idx["format"] == "epub"
        assert [c["title"] for c in idx["chapters"]] == ["The Storm", "The Calm", "The Return"]
        assert "Copyright" in (d / "front_matter.txt").read_text()

    def test_docx_and_html_ingest(self, fake_root, run_script, tmp_path):
        f = tmp_path / "d.docx"
        make_docx(f, [x for i in range(1, 4) for x in (("Heading1", f"Part {i}"), (None, PARA * 3))])
        assert run_script("book_ingest.py", "dbook", str(f))[0] is None
        h = tmp_path / "h.html"
        h.write_text("".join(f"<h2>Part {i}</h2><p>{PARA * 3}</p>" for i in range(1, 4)))
        run_script("book_ingest.py", "hbook", str(h))
        assert json.loads((fake_root / "projects" / "books" / "hbook" / "chapters.json").read_text())["method"] == "structure"

    def test_scanned_pdf_ingest_with_a_fake_engine(self, fake_root, monkeypatch, run_script, tmp_path):
        f = tmp_path / "scan.pdf"
        scanned_pdf(f, 4)
        monkeypatch.setattr(bf, "find_ocr_engine", lambda: (lambda im: "CHAPTER 1\n" + " ".join(["lorem"] * 500) + "\nCHAPTER 2\n" + " ".join(["ipsum"] * 500) + "\nCHAPTER 3\n" + " ".join(["dolor"] * 500)))
        code, out = run_script("book_ingest.py", "scanbook", str(f))
        idx = json.loads((fake_root / "projects" / "books" / "scanbook" / "chapters.json").read_text())
        assert code is None and idx["ocr_pages"] == 4 and "read with OCR" in out

    def test_unreadable_book_exits_with_the_reason(self, fake_root, run_script, tmp_path):
        bad = tmp_path / "bad.epub"
        bad.write_bytes(b"nope")
        code, _ = run_script("book_ingest.py", "badbook", str(bad))
        assert "not a valid EPUB" in str(code)


class TestOcrStep:
    def test_scanned_pdf_step_pins_python_and_adds_ocr_packages(self, fake_root, monkeypatch):
        from studio_app import steps
        book = fake_root / "projects" / "books" / "demo"
        (book / "source").mkdir(parents=True)
        scanned_pdf(book / "source" / "scan.pdf", 2)
        monkeypatch.setattr(bf.shutil, "which", lambda n: None)
        argv = steps.book_steps({"steps": {"ingest": True}, "pdf": "scan.pdf"}, "demo")[0]["argv"]
        assert argv[:4] == ["uv", "run", "--python", ">=3.11,<3.14"] and argv.count("--with") == 4 and "rapidocr" in argv

    def test_other_formats_need_no_extra_packages(self, fake_root):
        from studio_app import steps
        book = fake_root / "projects" / "books" / "demo"
        (book / "source").mkdir(parents=True)
        make_epub(book / "source" / "b.epub", ["A", "B", "C"])
        s = steps.book_steps({"steps": {"ingest": True}, "pdf": "b.epub"}, "demo")[0]
        assert s["label"].startswith("Read EPUB") and s["argv"][:3] == ["uv", "run", "--with"] and "--python" not in s["argv"]


class TestEdgeCases:
    def test_a_chapter_called_cover_up_is_not_front_matter(self, tmp_path):
        f = tmp_path / "b.epub"
        make_epub(f, ["The Cover-Up", "Notes from the Road", "The End Of It"], extra_front=False)
        assert [t for t, _ in bf.read_book(f).sections] == ["The Cover-Up", "Notes from the Road", "The End Of It"]

    def test_trailing_notes_and_licence_go_to_back_matter(self, tmp_path):
        f = tmp_path / "b.epub"
        make_epub(f, ["One", "Two", "Three", "Four", "Notes", "Project Gutenberg License"], extra_front=False)
        book = bf.read_book(f)
        assert [t for t, _ in book.sections] == ["One", "Two", "Three", "Four"] and "Gutenberg" in book.back

    def test_ocr_engine_failure_is_a_readable_error(self, tmp_path):
        f = tmp_path / "scan.pdf"
        scanned_pdf(f, 1)

        def boom(im):
            raise RuntimeError("model missing")
        with pytest.raises(bf.BookReadError, match="OCR failed on page 1: model missing"):
            bf.read_book(f, engine=boom)

    def test_tesseract_timeout_is_a_readable_error(self, monkeypatch):
        from PIL import Image

        def slow(argv, **kw):
            raise bf.subprocess.TimeoutExpired(argv, 1)
        monkeypatch.setattr(bf.subprocess, "run", slow)
        with pytest.raises(bf.BookReadError, match="5 minutes"):
            bf._tesseract_engine("/x/tesseract")(Image.new("RGB", (5, 5)))

    def test_tesseract_failure_and_language_setting(self, monkeypatch):
        from PIL import Image

        class R:
            returncode, stdout, stderr = 1, "", "no such language"
        seen = []
        monkeypatch.setattr(bf.subprocess, "run", lambda argv, **kw: (seen.append(argv) or R()))
        monkeypatch.setenv("STUDIO_OCR_LANG", "bad lang; rm")
        with pytest.raises(bf.BookReadError, match="no such language"):
            bf._tesseract_engine("/x/tesseract")(Image.new("RGB", (5, 5)))
        assert seen[0][seen[0].index("-l") + 1] == "eng"                # an unsafe value falls back to English

    def test_read_book_rejects_unknown_types(self, tmp_path):
        with pytest.raises(bf.BookReadError, match="Cannot read"):
            bf.read_book(tmp_path / "x.rtf")
