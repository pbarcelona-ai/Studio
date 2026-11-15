"""scripts/kaggle_names.py: notebook and dataset names for Kaggle stay within 50 characters, and long ones stay unique and repeatable."""
import re
import kaggle_names
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def fit(name, tail):
    return kaggle_names.fit(name, tail)


def test_short_names_are_unchanged():
    assert fit("genesis-film", "-image-flux2-klein-4b-keyframes-1-12") == "genesis-film-image-flux2-klein-4b-keyframes-1-12"
    assert fit("genesis-jasher-jubilees-adam-eve", "-prompts") == "genesis-jasher-jubilees-adam-eve-prompts"


def test_the_failing_name_from_the_log_now_fits():
    out = fit("genesis-jasher-jubilees-adam-eve", "-image-flux2-klein-4b-keyframes-1-40")
    assert len(out) <= 50 and out.endswith("-image-flux2-klein-4b-keyframes-1-40") and re.fullmatch(r"[a-z0-9-]+", out)


def test_long_names_stay_different_and_repeatable():
    tail = "-image-flux2-klein-4b-keyframes-1-40"
    a, b = fit("genesis-jasher-jubilees-adam-eve", tail), fit("genesis-jasher-jubilees-adam-eve-two", tail)
    assert a != b and a == fit("genesis-jasher-jubilees-adam-eve", tail)
    assert "--" not in a and len(b) <= 50


def test_the_script_uses_it():
    text = (ROOT / "scripts" / "run_kaggle_model.py").read_text()
    assert "kaggle_names.fit(name" in text


def test_cksum_matches_the_posix_command():
    assert kaggle_names.cksum(b"") == 4294967295 and kaggle_names.cksum(b"genesis-jasher-jubilees-adam-eve") == kaggle_names.cksum(b"genesis-jasher-jubilees-adam-eve")
    assert kaggle_names.cksum(b"a") == 1220704766                       # `printf a | cksum`
