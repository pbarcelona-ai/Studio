"""What each picture shows is remembered (picture_record.py), and "Match old pictures" checks every shot (old_pictures.match_all)."""
import os
import time

import pytest

import picture_record as pr
import review
from conftest import write_csv
from studio_app.common import PlanError
from studio_app.old_pictures import match_all

PROMPTS = ["a woman walks in a garden", "a mountain at dawn", "he raises his hand", "a river at night"]   # the demo book's shots, in order


def _kf_csv(book, prompts):
    write_csv(book / "keyframes.csv", [{"chapter": "1", "shot": n, "prompt": p} for n, p in enumerate(prompts, 1)])
    old = time.time() - 100
    os.utime(book / "keyframes.csv", (old, old))                 # written before the run that made the pictures


def _pics(book, names, model="flux"):
    kf = book / "images" / f"{model}_keyframes"
    kf.mkdir(parents=True, exist_ok=True)
    for n, text in names.items():
        (kf / f"image-{n:04d}.png").write_text(text)
    return kf


def test_pictures_are_recorded_from_the_list_they_were_made_from(book):
    _kf_csv(book, ["a mountain at dawn", "a woman walks in a garden"])
    kf = _pics(book, {1: "pic of mountain", 2: "pic of garden"})
    assert pr.record_new(book) == 2 and pr.record_new(book) == 0
    assert pr.prompt_of(book, kf / "image-0001.png") == "a mountain at dawn"
    (kf / "takes").mkdir()
    os.replace(kf / "image-0001.png", kf / "takes" / "image-0003-t1.png")      # the record follows the picture, wherever it goes
    assert pr.prompt_of(book, kf / "takes" / "image-0003-t1.png") == "a mountain at dawn"
    assert pr.prompt_of(book, book / "all_shots.csv") is None


def test_without_keyframes_csv_the_shot_list_is_used(book):
    kf = _pics(book, {3: "pic"})
    pr.record_new(book)
    assert pr.prompt_of(book, kf / "image-0003.png") == "he raises his hand"


def test_match_checks_every_shot(book):
    # pictures made when shots 1 and 2 were the other way round; shot 4 has none, but an old one was set aside
    _kf_csv(book, ["a mountain at dawn", "a woman walks in a garden", "he raises his hand"])
    kf = _pics(book, {1: "pic of mountain", 2: "pic of garden", 3: "pic of hand"})
    aside = book / "replaced" / "20260101-000000" / "images" / "flux_keyframes"
    aside.mkdir(parents=True)
    (aside / "image-0001.png").write_text("pic of river")
    write_csv(aside.parent.parent / "all_shots.csv", [{"chapter": "1", "shot": 1, "prompt": "a river at night"}])
    review.set_status(book, ["1#1", "1#3"], "approved")
    r = match_all({"project": "demo", "model": "flux"})
    assert (r["kept"], r["moved"], r["from_old"], r["still_missing"]) == (1, 2, 1, [])
    assert [(kf / f"image-{n:04d}.png").read_text() for n in range(1, 5)] == ["pic of garden", "pic of mountain", "pic of hand", "pic of river"]
    v = review.load(book)
    assert "1#1" not in v and v["1#3"]["status"] == "approved"                  # a changed picture is asked about again; a kept one is not
    again = match_all({"project": "demo", "model": "flux"})
    assert again["kept"] == 4 and again["changed"] == []


def test_a_picture_that_shows_no_shot_is_kept_as_a_take(book):
    _kf_csv(book, ["a dragon over a castle", "a mountain at dawn"])
    kf = _pics(book, {1: "pic of dragon", 2: "pic of mountain"})
    r = match_all({"project": "demo", "model": "flux"})
    assert r["set_aside_as_takes"] == 1 and r["still_missing"] == [1, 3, 4] and r["kept"] == 1
    assert (kf / "takes" / "image-0001-t1.png").read_text() == "pic of dragon" and not (kf / "image-0001.png").exists()
    assert not (kf / ".matching").exists()


def test_match_guards(book, monkeypatch):
    with pytest.raises(PlanError, match="picture maker"):
        match_all({"project": "demo"})                                         # no pictures yet, no maker chosen
    from studio_app.jobs import JOB
    monkeypatch.setattr(JOB, "running", True)
    with pytest.raises(PlanError, match="running"):
        match_all({"project": "demo", "model": "flux"})


def test_route(server, book):
    _pics(book, {1: "p"})
    status, data = server.api("POST", "/api/match_pictures", {"project": "demo"})
    assert status == 200 and data["model"] == "flux" and data["kept"] == 1


def test_a_picture_that_is_moved_while_it_is_recorded_is_skipped(book, monkeypatch):
    _pics(book, {1: "a", 2: "b"})
    real = pr.file_sha

    def flaky(pdir, path, rec):
        if path.name == "image-0001.png":
            raise FileNotFoundError(path)
        return real(pdir, path, rec)
    monkeypatch.setattr(pr, "file_sha", flaky)
    assert pr.record_new(book) == 1                                           # the other one is recorded; the moving one waits for next time
    monkeypatch.setattr(pr, "file_sha", real)
    assert pr.record_new(book) == 1
