"""M15: Autopilot from an idea to the downloads (stopping where the owner asked, carrying on after), the spending check, parallel style
renders, the cost ledger (estimate vs. actual), and the job lock."""
import re
import threading

import pytest

import autopilot as ap
import consistency
import continuity_book as cb
import layout
import ledger
import marketing
import production
import read_it_in as ri
import shot_list as sl
import sound_design as sd
import sources as src
import styles
from test_clips import make_clip
from test_pictures import png
from test_read_it_in import STORY


def fake_text(pdir):
    fakes = [ri.fake_ask(pdir), cb.fake_ask(pdir), sl.fake_ask(pdir), styles.fake_ask(pdir), sd.fake_ask(pdir), marketing.fake_ask()]
    from clips import fake_ask as clip_fake

    def ask(prompt, roles, step, validate):
        if step.startswith("clips: motion"):
            return clip_fake()(prompt, roles, step, validate)
        for f in fakes:
            try:
                return f(prompt, roles, step, validate)
            except (ValueError, KeyError, IndexError, ri.ReadError):
                continue
        raise AssertionError(f"no fake for {step}")
    return ask


class FakeGpu:
    """Writes the pictures and clips a runner would bring back; records the calls and how many ran at once."""

    def __init__(self):
        self.calls, self.now, self.most, self.lock = [], 0, 0, threading.Lock()

    def __call__(self, target, model, first, last, csv_name, extra):
        import time
        with self.lock:
            self.now += 1
            self.most = max(self.most, self.now)
            self.calls.append((target, model, first, last))
        time.sleep(0.05)
        d = layout.find_dir(target)
        for row in range(first, last + 1):
            if csv_name == "all_images.csv":
                png(d / "images" / "flux2_klein_4b" / f"image-{row:04d}.png", (row * 9 % 255, 40, 90))
            else:
                make_clip(d / "videos" / model / f"shot-{row:04d}.mp4", 1.0)
        with self.lock:
            self.now -= 1


@pytest.fixture
def idea_book(fake_root):
    pytest.importorskip("imageio_ffmpeg")
    d = fake_root / "projects" / "books" / "door"
    src.store(d, src.from_idea(STORY, "Door"), True)
    production.save(d, {"products": ["screenplay", "storyboard", "film"], "target_minutes": 1, "styles": [{"id": "claymation"}, {"id": "anime"}],
                        "master": "claymation"})
    return d


class TestAutopilot:
    def test_stops_where_asked_then_makes_everything(self, idea_book):
        gpu, said = FakeGpu(), []
        pilot = ap.Autopilot(idea_book, fake_text(idea_book), consistency.fake_ask(), gpu, ["shotlist"], service="fake", image_model="flux2_klein_4b",
                             say=said.append)
        with pytest.raises(ap.Waiting, match="shot list"):
            pilot.run()
        assert (idea_book / "readin" / "summary.json").is_file() and sl.load(idea_book)["scenes"] and gpu.calls == []
        import gates
        gates.approve(idea_book, "shotlist", sl.gate_data(sl.load(idea_book)))                # the owner approves; Autopilot carries on
        out = ap.Autopilot(idea_book, fake_text(idea_book), consistency.fake_ask(), gpu, ["shotlist"], service="fake", say=said.append).run()
        assert "film_claymation.mp4" in out["made"] and "film_anime.mp4" in out["made"] and "storyboard_claymation.pdf" in out["made"]
        models = {c[1] for c in gpu.calls}
        assert "image_flux2_klein_4b" in models and "ltx_video_fast_i2v" in models
        assert gpu.most >= 2                                                                   # styles render side by side
        assert any(m["kind"] == "autopilot" for m in __import__("history").moments(idea_book)) and said[-1].startswith("Done:")
        assert ap.Autopilot(idea_book, fake_text(idea_book), consistency.fake_ask(), gpu, [], service="fake").run()["made"]   # a re-run carries on, renders nothing new
        assert len([c for c in gpu.calls if c[1] == "ltx_video_fast_i2v"]) == 2

    def test_spending_check(self, idea_book):
        st = production.load(idea_book)
        pilot = ap.Autopilot(idea_book, fake_text(idea_book), None, FakeGpu(), [], service="paid_service")
        with pytest.raises(ap.Waiting, match="over your limit"):
            pilot.spending_check(st)
        ap.Autopilot(idea_book, fake_text(idea_book), None, FakeGpu(), [], confirm_spend=True, service="paid_service").spending_check(st)
        ap.Autopilot(idea_book, fake_text(idea_book), None, FakeGpu(), [], service="kaggle").spending_check(st)          # free GPUs: $0

    def test_cli_options(self, fake_root, capsys):
        assert ap.main(["nope", "--stop-at", "teatime"]) == 1 and "--stop-at" in capsys.readouterr().out


class TestLedger:
    def test_estimate_vs_actual(self, idea_book):
        ap.Autopilot(idea_book, fake_text(idea_book), consistency.fake_ask(), FakeGpu(), [], service="fake").run()
        import pictures as px
        px.prepare_regenerate(idea_book, "claymation", 1)
        r = ledger.report(idea_book)
        a = r["actual"]
        assert a["regenerations"] == 1 and a["styles"][0]["pictures"] >= 1 and a["styles"][0]["clips"] >= 1 and a["gpu_hours"] > 0
        assert r["estimate"]["gpu_hours"] > 0 and r["spend_limit"] == 0
        ledger.record(idea_book, "pictures", 0.25, regeneration=True)
        assert ledger.report(idea_book)["actual"]["paid_dollars"] == 0.25
        with pytest.raises(ValueError):
            ledger.record(idea_book, "x", -1)


def test_text_of_waiting():
    assert re.search("review", str(ap.Waiting("Waiting for your review at x")))
