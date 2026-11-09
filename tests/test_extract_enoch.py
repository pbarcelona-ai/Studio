"""extract_enoch_text.py with a stand-in PDF reader: chapter split, verse numbers, the Charles chapter 91 quirk and ALL-CAPS divine names."""
import json

import pytest

PAGES = [
    "CHAPTER 1\n1. THE words of the blessing of ENOCH.\n2. And he took up his parable.\n17\n",
    "CHAPTER 2\nObserve every thing in heaven’s order -- it does not change.\n",
    "CHAPTER 91\n1. First part [of ninety-one].\n",
    "CHAPTER 93\n1. The book of Enoch <the scribe> ⌈says⌉.\n",
    "CHAPTER 91\n2. Second part about GOD AND THE LORD.\n",
]


@pytest.fixture()
def enoch(fake_root, monkeypatch):
    import pypdf
    d = fake_root / "projects" / "books" / "enoch"
    (d / "source").mkdir(parents=True)
    (d / "source" / "Book-of-Enoch-1-Enoch-Free-PDF-Download.pdf").write_bytes(b"%PDF")
    page = lambda t: type("P", (), {"extract_text": lambda self: t})()      # noqa: E731
    monkeypatch.setattr(pypdf, "PdfReader", lambda path: type("R", (), {"pages": [page(t) for t in PAGES]})())
    return d


def test_extracts_verses_per_chapter(enoch, run_script):
    code, out = run_script("extract_enoch_text.py")
    data = json.loads((enoch / "enoch_verses.json").read_text())
    assert code is None and len(data) == 108 and "empty:" in out
    assert data["1"]["verses"] == ["The words of the blessing of Enoch.", "And he took up his parable."] and "17" not in data["1"]["text"]
    assert data["2"]["verses"] == ["Observe every thing in heaven's order — it does not change."]       # no verse numbers: one verse; -- becomes a dash


def test_chapter_91_parts_are_joined_and_marks_removed(enoch, run_script):
    run_script("extract_enoch_text.py")
    data = json.loads((enoch / "enoch_verses.json").read_text())
    assert data["91"]["verses"][0].startswith("First part of ninety-one") and data["91"]["verses"][1] == "Second part about God and The Lord."
    assert data["93"]["text"] == "The book of Enoch the scribe says."
    assert data["3"]["verses"] == []
