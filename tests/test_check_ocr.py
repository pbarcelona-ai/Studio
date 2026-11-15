"""scripts/check_ocr.py: the self-test draws a picture-only PDF and counts the words an engine reads back."""
import book_formats as bf
import check_ocr as co


def test_check_counts_words_read_by_the_engine():
    text = " ".join(co.SENTENCES)
    name, found, total = co.check(engine=lambda img: text)
    assert (name, found) == ("given", total) and total > 20


def test_check_reports_a_poor_engine(monkeypatch):
    monkeypatch.setattr(co, "check", lambda: ("fake", 3, 38))
    assert co.main() == 1


def test_main_passes_on_a_good_read(monkeypatch, capsys):
    monkeypatch.setattr(co, "check", lambda: ("fake", 37, 38))
    assert co.main() == 0 and "37 of 38" in capsys.readouterr().out


def test_no_engine_is_explained(monkeypatch, capsys):
    monkeypatch.setattr(bf, "ocr_engine_name", lambda: None)
    assert co.main() == 1 and "tesseract" in capsys.readouterr().out
