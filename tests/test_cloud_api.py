"""Tests for direct Cloud API execution (scripts/run_cloud_api.py)."""
import pytest

import layout
import run_cloud_api as rca
from runner_common import RunError


@pytest.fixture()
def mock_keys(tmp_path, monkeypatch):
    keys_file = tmp_path / "cloud_keys.json"
    monkeypatch.setattr(rca, "CLOUD_KEYS_FILE", keys_file)
    monkeypatch.delenv("FAL_KEY", raising=False)
    monkeypatch.delenv("REPLICATE_API_TOKEN", raising=False)
    return keys_file


def test_keys_file_loading_and_saving(mock_keys):
    assert rca.load_api_keys() == {}
    rca.save_api_keys(fal_key="fal_test_123", replicate_token="rep_test_456")
    keys = rca.load_api_keys()
    assert keys["fal"] == "fal_test_123"
    assert keys["replicate"] == "rep_test_456"


def test_keys_env_override(mock_keys, monkeypatch):
    rca.save_api_keys(fal_key="file_key")
    monkeypatch.setenv("FAL_KEY", "env_key")
    assert rca.load_api_keys()["fal"] == "env_key"


def test_missing_api_key_raises_error(tmp_path):
    out_dir = tmp_path / "images" / "flux1_schnell"
    row = {"prompt": "a futuristic spaceship in space"}
    with pytest.raises(RunError, match="Fal.ai API key is missing"):
        rca.generate_row("flux1_schnell", row, 1, out_dir, keys={})


def test_generate_image_row_success(tmp_path, monkeypatch):
    out_dir = tmp_path / "images" / "flux1_schnell"
    row = {"prompt": "a beautiful forest", "width": "512", "height": "512", "steps": "4", "seed": "42"}

    # Mock API call and download
    monkeypatch.setattr(rca, "call_fal_api", lambda ep, payload, key: {"images": [{"url": "https://example.com/test.png"}]})

    def fake_download(url, dest):
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text("fake_png_data")
        return dest

    monkeypatch.setattr(rca, "download_file", fake_download)

    res = rca.generate_row("flux1_schnell", row, 1, out_dir, keys={"fal": "mock_key"})
    assert res.is_file()
    assert res.name == "image-0001.png"
    assert res.read_text() == "fake_png_data"


def test_generate_video_row_success(tmp_path, monkeypatch):
    out_dir = tmp_path / "videos" / "ltx_video"
    row = {"prompt": "a dog running in a park", "seed": "100"}

    monkeypatch.setattr(rca, "call_fal_api", lambda ep, payload, key, timeout=180: {"video": {"url": "https://example.com/test.mp4"}})

    def fake_download(url, dest):
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text("fake_mp4_data")
        return dest

    monkeypatch.setattr(rca, "download_file", fake_download)

    res = rca.generate_row("ltx_video", row, 2, out_dir, keys={"fal": "mock_key"})
    assert res.is_file()
    assert res.name == "shot-0002.mp4"


def test_generate_i2v_requires_keyframe(tmp_path):
    out_dir = tmp_path / "videos" / "ltx_video_i2v"
    row = {"prompt": "a dog barking"}
    with pytest.raises(RunError, match="Keyframe directory required"):
        rca.generate_row("ltx_video_i2v", row, 1, out_dir, keys={"fal": "mock_key"}, keyframe_dir=None)


def test_main_cli_execution(tmp_path, monkeypatch):
    # Set up project and CSV
    book_dir = tmp_path / "projects" / "books" / "demo_book"
    book_dir.mkdir(parents=True)
    csv_path = book_dir / "all_images.csv"
    csv_path.write_text("prompt,seed,width,height\nfirst image,1,512,512\nsecond image,2,512,512\n", encoding="utf-8")

    monkeypatch.setenv("PROJECT", "demo_book")
    monkeypatch.setattr(layout, "project_dir", lambda p: book_dir)
    monkeypatch.setattr(rca, "load_api_keys", lambda: {"fal": "mock_key"})
    monkeypatch.setattr(rca, "call_fal_api", lambda ep, payload, key: {"images": [{"url": "https://example.com/mock.png"}]})
    monkeypatch.setattr(rca, "download_file", lambda url, dest: dest.write_text("mock") or dest)

    monkeypatch.setattr(rca.sys, "argv", ["run_cloud_api.py", "flux1_schnell", "1", "2"])
    rca.main()

    img1 = book_dir / "images" / "flux1_schnell" / "image-0001.png"
    img2 = book_dir / "images" / "flux1_schnell" / "image-0002.png"
    assert img1.is_file()
    assert img2.is_file()


def test_generate_image_with_character_reference(tmp_path, monkeypatch):
    out_dir = tmp_path / "images" / "flux1_dev"
    refs_dir = tmp_path / "keyframe_refs"
    refs_dir.mkdir(parents=True)
    ref_img = refs_dir / "ref-hero.png"
    ref_img.write_bytes(b"\x89PNG\r\n\x1a\nfakeimage")

    row = {"prompt": "hero walking in city", "refs": "ref-hero.png", "strength": "0.6"}
    captured = {}

    def fake_call(ep, payload, key):
        captured["endpoint"] = ep
        captured["payload"] = payload
        return {"images": [{"url": "https://example.com/steered.png"}]}

    monkeypatch.setattr(rca, "call_fal_api", fake_call)
    monkeypatch.setattr(rca, "download_file", lambda url, dest: dest.write_text("ok") or dest)

    res = rca.generate_row("flux1_dev", row, 1, out_dir, keys={"fal": "mock_key"}, refs_dir=refs_dir)
    assert res.is_file()
    assert captured["endpoint"] == "fal-ai/flux/dev/image-to-image"
    assert captured["payload"]["image_url"].startswith("data:image/png;base64,")
    assert captured["payload"]["strength"] == 0.6
