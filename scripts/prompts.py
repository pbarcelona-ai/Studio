"""Shared prompt extraction and service rotation for the generation helpers."""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PROJECTS = ROOT / "projects"
BOOKS = PROJECTS / "books"
ADAM_ROOT = BOOKS / "adam_eve" / "production_notes"
BOOK1 = ADAM_ROOT / "Book_1_First_Book_of_Adam_and_Eve"
BOOK2 = ADAM_ROOT / "Book_2_Second_Book_of_Adam_and_Eve"
ENOCH = BOOKS / "enoch" / "production_notes"

SERVICES = [
    ("Krea", 60, "https://krea.ai/video"),
    ("Kling", 66, "https://klingai.com"),
    ("Pika", 150, "https://pika.art"),
    ("Luma", 30, "https://lumalabs.ai/dream-machine"),
]

_FENCE = re.compile(r"```[^\n]*\n(.*?)```", re.DOTALL)


def adam_shots(md_path):
    """Return the fenced shot prompts under '## Video-generation prompts'."""
    content = Path(md_path).read_text()
    if "## Video-generation prompts" not in content:
        return []
    section = content.split("## Video-generation prompts", 1)[1].split("\n## ", 1)[0]
    return [m.strip() for m in _FENCE.findall(section) if m.strip()]


def enoch_prompt(md_path):
    """Return the single 'Ready-to-paste video prompt' for an Enoch chapter."""
    content = Path(md_path).read_text()
    if "## Ready-to-paste video prompt" not in content:
        return None
    section = content.split("## Ready-to-paste video prompt", 1)[1].split("\n## ", 1)[0]
    return section.strip() or None


def chapter_files(book_path, start=1, end=None):
    """Yield (number, path) for chapter-NNN.md files in range, skipping the prologue."""
    for p in sorted(book_path.glob("chapter-[0-9][0-9][0-9].md")):
        n = int(p.stem.split("-")[1])
        if n >= start and (end is None or n <= end):
            yield n, p


def adam_eve_chapters():
    """Yield (label, path) for Book 1 then Book 2 with ONE continuous numbering.

    adam_eve-001..079 are Book 1 chapters 1-79; adam_eve-080..101 are Book 2 chapters 1-22.
    """
    n = 0
    for book in (BOOK1, BOOK2):
        for _, path in chapter_files(book):
            n += 1
            yield f"adam_eve-{n:03d}", path
