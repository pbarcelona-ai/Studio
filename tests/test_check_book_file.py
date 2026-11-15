"""scripts/check_book_file.py: a readable summary of how a book file is read."""
import check_book_file as cb


def test_text_file_summary(tmp_path):
    f = tmp_path / "b.txt"
    f.write_text("CHAPTER I\n\n" + "word " * 50 + "\n\nCHAPTER II\n\n" + "more " * 50)
    code, lines = cb.describe(f)
    assert code == 0 and lines[0].startswith("b.txt: text") and any("front matter" in x for x in lines)


def test_many_sections_are_cut_off(tmp_path, monkeypatch):
    f = tmp_path / "b.txt"
    f.write_text("x")
    book = cb.bf.BookText(kind="epub", pages=["a b c"], sections=[(f"S{i}", "w w") for i in range(45)], notes=["cover set aside"], ocr_pages=2)
    monkeypatch.setattr(cb.bf, "read_book", lambda p: book)
    code, lines = cb.describe(f, limit=3)
    text = "\n".join(lines)
    assert code == 0 and "45 section(s)" in text and "and 42 more" in text and "note: cover set aside" in text and "2 page(s) had no text" in text


def test_unreadable_file_is_reported(tmp_path):
    f = tmp_path / "b.epub"
    f.write_bytes(b"not a zip")
    code, lines = cb.describe(f)
    assert code == 1 and "cannot read b.epub" in lines[0]


def test_main_usage_and_run(tmp_path, capsys):
    assert cb.main(["x"]) == 2
    f = tmp_path / "b.txt"
    f.write_text("hello there, " * 40)
    assert cb.main(["x", str(f)]) == 0 and "b.txt" in capsys.readouterr().out
