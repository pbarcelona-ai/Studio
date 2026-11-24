"""Unit tests for scripts/local_runners/model_packs.py and bundled apps/packs."""
from __future__ import annotations

import json
from pathlib import Path
import sys

import pytest

_ROOT = Path(__file__).resolve().parents[1]
_SCRIPTS = _ROOT / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from local_runners import model_packs  # noqa: E402


def test_token_validation_and_storage(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("STUDIO_DATA_DIR", str(tmp_path))
    monkeypatch.delenv("HF_TOKEN", raising=False)

    assert model_packs.looks_like_token("hf_" + "a" * 26) is False
    assert model_packs.looks_like_token("hf_" + "a" * 27) is True

    valid_tok = "hf_" + "k" * 30
    saved_path = model_packs.save_token(valid_tok)
    assert saved_path.is_file()
    assert model_packs.get_token() == (valid_tok, "studio")

    model_packs.forget_token()
    assert model_packs.get_token() == ("", "")


def test_bundled_packs_catalog_loads_cleanly() -> None:
    catalog = model_packs.load_pack_catalog(_ROOT / "packs")
    assert "core" in catalog
    assert "image" in catalog
    assert "video-ltx25" in catalog
    assert catalog["core"]["download_gb"] == 0

    smoke = json.loads((_ROOT / "apps" / "smoke" / "app.json").read_text(encoding="utf-8"))
    assert smoke["min_vram_gb"] == 0
    assert "mac_metal" in smoke["platforms"]
    assert "win_cuda" in smoke["platforms"]
