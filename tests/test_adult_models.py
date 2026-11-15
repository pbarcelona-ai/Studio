"""Adult-content models are hidden and refused until switched on."""
import pytest

from studio_app import config
from studio_app.common import PlanError
from studio_app.gpus import check_models, model_blocker

ADULT_VIDEO, ADULT_IMAGE = "wan22_t2v_a14b_lora", "noobai_xl"


@pytest.fixture(autouse=True)
def off(monkeypatch, fake_root):
    monkeypatch.delenv("STUDIO_ADULT_MODELS", raising=False)


def test_the_set_is_the_two_adult_groups():
    assert {"wan22_t2v_a14b_lora", "hunyuan_video_lora", "noobai_xl", "illustrious_xl", "qwen_image_21_uc"} <= config.ADULT_MODELS and "ltx_video" not in config.ADULT_MODELS


def test_refused_by_default_and_allowed_when_switched_on(monkeypatch):
    assert "switched off" in model_blocker(ADULT_VIDEO, "kaggle", "NvidiaTeslaT4")
    with pytest.raises(PlanError, match="switched off"):
        check_models("kaggle", "NvidiaTeslaT4", [ADULT_IMAGE])
    monkeypatch.setenv("STUDIO_ADULT_MODELS", "1")
    assert "switched off" not in str(model_blocker(ADULT_VIDEO, "kaggle", "NvidiaTeslaT4"))


def test_status_hides_them(server, monkeypatch):
    out = server.api("GET", "/api/status")[1]
    assert ADULT_VIDEO not in out["video_models"] and ADULT_IMAGE not in out["image_models"] and "ltx_video" in out["video_models"]
    assert all(g[0] != config.ADULT_GROUP for g in out["video_groups"] + out["image_groups"]) and out["adult_models"]["enabled"] is False


def test_the_switch_persists_and_shows_them(server):
    assert server.api("POST", "/api/adult_models", {"enabled": True})[1] == {"enabled": True}
    out = server.api("GET", "/api/status")[1]
    assert ADULT_VIDEO in out["video_models"] and ADULT_IMAGE in out["image_models"] and out["adult_models"]["enabled"] is True
    assert any(g[0] == config.ADULT_GROUP for g in out["video_groups"])
    assert server.api("POST", "/api/adult_models", {"enabled": False})[1] == {"enabled": False}
    assert ADULT_VIDEO not in server.api("GET", "/api/status")[1]["video_models"]


def test_running_one_is_refused_when_off(server, book):
    st, out = server.api("POST", "/api/plan", {"project": "demo", "granularity": "shots", "service": "kaggle", "gpu": "NvidiaTeslaT4", "kaggle_user": "tester",
                                                "video_models": [ADULT_VIDEO], "movies": {"mode": "all"}, "steps": {"video": True}})
    assert st == 400 and "switched off" in out["error"]
