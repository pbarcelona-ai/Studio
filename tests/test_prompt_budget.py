"""compose_prompt keeps the shot description first and inside the video model's 256-token window (the genesis_film run lost its tail to truncation)."""
import csv
import json
from pathlib import Path

import bookkit as bk

SHOT = "A wide slow dolly shot of a bearded man in a rough wool tunic kneeling by a river at dawn while mist rises from the water and birds cross a pink sky"
STYLE = " ".join(f"style{i}" for i in range(60))
GLOBAL = " ".join(f"look{i}" for i in range(40))
CONT = {"visual_style": STYLE, "characters": [{"name": "Adam", "token": "Adam: " + " ".join(f"adam{i}" for i in range(30))},
                                               {"name": "Eve", "token": "Eve: " + " ".join(f"eve{i}" for i in range(30))}],
        "locations": [{"name": "River", "token": " ".join(f"river{i}" for i in range(30))}]}


def test_the_estimate_is_cautious_on_the_prompts_that_were_cut():
    cut = ("A wide shot of a man at the river at dawn, " + "soft light, mist, wool tunic, calm water, " * 24 + "no text, no subtitles, no logos, no watermark")
    assert len(cut) > 900 and bk.est_tokens(cut) > 256
    assert bk.est_tokens("A man walks.") < 12 and bk.est_tokens("") == 0


def test_short_prompts_keep_everything_in_the_new_order():
    out = bk.compose_prompt("She walks", ["Adam"], {"visual_style": "oil painting", "characters": CONT["characters"][:1], "locations": []}, global_positives="cinematic")
    assert out.startswith("She walks, ADAM: ") and out.endswith("oil painting, cinematic, " + bk.NEG_TAIL)


def test_over_budget_drops_the_tail_and_style_first_and_never_the_shot():
    out = bk.compose_prompt(SHOT, ["Adam", "Eve"], CONT, global_positives=GLOBAL, location="River")
    assert out.startswith(SHOT) and bk.est_tokens(out) <= bk.PROMPT_TOKENS and len(out) <= 1000
    assert "ADAM: adam0" in out and "EVE: eve0" in out
    assert bk.NEG_TAIL not in out


def test_the_budget_can_be_tightened_and_a_huge_description_is_cut_last():
    tight = bk.compose_prompt(SHOT, ["Adam", "Eve"], CONT, global_positives=GLOBAL, location="River", max_tokens=60)
    assert tight.startswith(SHOT) and bk.est_tokens(tight) <= 60 and "EVE" not in tight
    huge = bk.compose_prompt(" ".join(["word"] * 400), ["Adam"], CONT)
    assert bk.est_tokens(huge) <= bk.PROMPT_TOKENS and huge.startswith("word")


def test_global_texts_and_shorten(tmp_path):
    assert bk.global_texts(tmp_path) == ("", "")
    (tmp_path / "global_params.json").write_text(json.dumps({"positives": "p", "negatives": "n"}))
    assert bk.global_texts(tmp_path, "anything") == ("p", "n")
    (tmp_path / "global_params.json").write_text("not json")
    assert bk.global_texts(tmp_path) == ("", "")
    assert bk.shorten_words("a b c d e", 3) == "a b c" and bk.shorten_words("a b", 3) == "a b"


def test_recompose_rewrites_saved_scripts_and_book_build_flag(fake_root, run_script):
    d = fake_root / "projects" / "books" / "demo"
    (d / "scripts").mkdir(parents=True)
    (d / "demo.json").write_text(json.dumps({**CONT, "setting": "s", "music_theme": "m"}))
    old = f"{GLOBAL}, {SHOT}, ADAM: adam, {STYLE}, {STYLE}, {bk.NEG_TAIL}"
    shot = {"n": 1, "visual": SHOT, "characters": ["Adam", "Eve"], "narration": "n", "speaker": "NARRATOR", "voice": "", "sfx": "wind", "music": "harp", "negative": "",
            "location": "River", "continues": False, "prompt": old}
    (d / "scripts" / "chapter-001.json").write_text(json.dumps({"chapter": 1, "title": "One", "narration_mode": "condensed", "shots": [shot]}))
    changed, over = bk.recompose_scripts(d)
    new = json.loads((d / "scripts" / "chapter-001.json").read_text())["shots"][0]["prompt"]
    assert (changed, over) == (1, 1) and new.startswith(SHOT) and bk.est_tokens(new) <= bk.PROMPT_TOKENS
    assert bk.recompose_scripts(d) == (0, 0)                                    # stable
    code, out = run_script("book_build.py", "demo", "--recompose")
    assert code is None and "prompts rewritten: 0 changed" in out
    rows = list(csv.DictReader(open(d / "all_shots.csv")))
    assert rows[0]["prompt"].startswith(SHOT) and Path(d / "all_shots.csv").exists()
