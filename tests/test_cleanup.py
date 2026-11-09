"""The Trash mover must only touch files inside the project folder and must keep what it moves."""
from pathlib import Path

import pytest

from studio_app import cleanup
from studio_app.common import PlanError


@pytest.fixture()
def tree(tmp_path, monkeypatch):
    root = tmp_path / "studio"
    (root / "projects" / "demo").mkdir(parents=True)
    (root / "projects" / "demo" / "a.mp4").write_bytes(b"12345")
    (tmp_path / "outside.txt").write_text("keep me")
    monkeypatch.setattr(cleanup, "ROOT", root)
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path / "home"))
    return tmp_path


def test_moves_into_a_trash_folder_and_keeps_the_bytes(tree):
    res = cleanup.move_to_trash(["projects/demo/a.mp4"], "test")
    assert res["moved"] == 1 and res["bytes"] == 5
    moved = Path(res["trash"]) / "projects" / "demo" / "a.mp4"
    assert moved.read_bytes() == b"12345" and not (tree / "studio" / "projects" / "demo" / "a.mp4").exists()


@pytest.mark.parametrize("rel", ["../outside.txt", "projects/../../outside.txt", "/etc/hosts", "projects/demo/missing.mp4", ""])
def test_refuses_anything_outside_or_missing(tree, rel):
    assert cleanup.move_to_trash([rel], "test") == {"moved": 0, "bytes": 0, "trash": ""}
    assert (tree / "outside.txt").read_text() == "keep me"


def test_cleanup_delete_needs_a_known_group(tree):
    with pytest.raises(PlanError, match="at least one group"):
        cleanup.cleanup_delete(["../../etc", "nonsense"])
