"""The search index: rebuilt from the folders (current pictures, earlier takes, pictures set aside in replaced/), searchable, always derived."""
import sqlite3

import picture_record
import studio_index


def png(path, data=b"x"):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"\x89PNG" + data)


def test_rebuild_and_search(book, tmp_path):
    k = book / "images" / "flux_keyframes"
    png(k / "image-0001.png", b"one")
    png(k / "takes" / "image-0001-t1.png", b"older")
    stamp = book / "replaced" / "20261101-120000"
    png(stamp / "images" / "flux_keyframes" / "image-0002.png", b"aside")
    (stamp / "all_shots.csv").write_text("chapter,shot,prompt\n1,1,a cat on a wall\n1,2,a lighthouse in a storm\n")
    picture_record.remember(book, k / "image-0001.png", "a woman walks in a sunny garden", "flux")
    out = studio_index.rebuild()
    assert out == {"books": 1, "pictures": 3, "path": str(studio_index.db_path())}
    hits = studio_index.search_pictures("garden")
    by_path = {h["path"]: h for h in hits}                 # the take falls back to the shot list now ("a woman walks in a garden")
    assert set(by_path) == {"demo/images/flux_keyframes/image-0001.png", "demo/images/flux_keyframes/takes/image-0001-t1.png"}
    cur, take = by_path["demo/images/flux_keyframes/image-0001.png"], by_path["demo/images/flux_keyframes/takes/image-0001-t1.png"]
    assert cur["current"] and not take["current"] and cur["prompt"] == "a woman walks in a sunny garden" and take["prompt"] == "a woman walks in a garden"
    aside = studio_index.search_pictures("lighthouse storm")
    assert len(aside) == 1 and aside[0]["shot"] == 2 and aside[0]["path"].startswith("demo/replaced/20261101-120000/")
    db = sqlite3.connect(studio_index.db_path())
    assert db.execute("select count(*) from attempt").fetchone()[0] == 1
    assert db.execute("select count(*) from asset where is_selected = 1").fetchone()[0] == 1
    db.close()
    assert studio_index.search_pictures("lighthouse", project="other") == [] and studio_index.search_pictures("") == []


def test_rebuild_is_repeatable_and_ids_are_stable(book):
    png(book / "images" / "flux_keyframes" / "image-0003.png")
    studio_index.rebuild()
    def ids():
        db = sqlite3.connect(studio_index.db_path())
        try:
            return db.execute("select id from asset").fetchall()
        finally:
            db.close()                                     # Windows cannot replace a file that is still open
    first = ids()
    studio_index.rebuild()
    assert ids() == first


def test_no_index_means_no_hits(fake_root):
    assert not studio_index.db_path().exists() and studio_index.search_pictures("anything") == []


def test_background_rebuild_never_raises(fake_root, monkeypatch):
    def boom():
        raise RuntimeError("disk full")
    monkeypatch.setattr(studio_index, "rebuild", boom)
    studio_index.rebuild_in_background().join(5)


def test_unchanged_pictures_are_not_read_again(book, monkeypatch):
    png(book / "images" / "flux_keyframes" / "image-0001.png")
    studio_index.rebuild()
    reads = []
    real = picture_record.file_sha
    monkeypatch.setattr(picture_record, "file_sha", lambda *a: reads.append(a) or real(*a))
    studio_index.rebuild()
    assert reads == []
    png(book / "images" / "flux_keyframes" / "image-0002.png")
    studio_index.rebuild()
    assert len(reads) == 1


def test_swap_retries_while_windows_holds_the_file(tmp_path, monkeypatch):
    calls = []
    real = studio_index.os.replace

    def flaky(a, b):
        calls.append(1)
        if len(calls) < 3:
            raise PermissionError("in use")
        real(a, b)
    monkeypatch.setattr(studio_index.os, "replace", flaky)
    monkeypatch.setattr(studio_index.time, "sleep", lambda s: None)
    (tmp_path / "new").write_text("x")
    studio_index._swap(str(tmp_path / "new"), tmp_path / "db")
    assert len(calls) == 3 and (tmp_path / "db").read_text() == "x"
