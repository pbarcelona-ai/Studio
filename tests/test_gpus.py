"""Which model can run where: memory lookups and the reasons a combination is refused."""
import pytest

from studio_app import gpus
from studio_app.common import PlanError


@pytest.fixture(autouse=True)
def no_local_gpu(monkeypatch):
    monkeypatch.setattr(gpus, "local_gpus", lambda: [])
    monkeypatch.setattr(gpus, "all_gpus", lambda: [])
    monkeypatch.delenv("HF_TOKEN", raising=False)


def test_gpu_memory_known_and_unknown():
    assert gpus.gpu_memory("kaggle", "NvidiaTeslaT4") == (15, False)
    assert gpus.gpu_memory("kaggle", "NvidiaH100") == (80, True)
    assert gpus.gpu_memory("colab", "T4") == (15, False)
    assert gpus.gpu_memory("colab", "L4") == (22, True)
    assert gpus.gpu_memory("huggingface", "ZeroGPU") == (None, None)


def test_local_gpu_memory_and_ampere_flag(monkeypatch):
    monkeypatch.setattr(gpus, "local_gpus", lambda: [("RTX 4090", 24, "8.9")])
    assert gpus.gpu_memory("computer", "local") == (24, True)
    monkeypatch.setattr(gpus, "local_gpus", lambda: [("gfx1100", 24, "gfx1100")])
    assert gpus.gpu_memory("computer", "local") == (24, None)


def test_upscaler_needs_ampere_and_memory(monkeypatch):
    assert "Ampere" in gpus.model_blocker("upscale_flashvsr", "kaggle", "NvidiaTeslaT4")
    assert gpus.model_blocker("upscale_flashvsr", "kaggle", "NvidiaL4") is None
    assert gpus.model_blocker("upscale_seedvr2_7b", "kaggle", "NvidiaTeslaT4") is None          # 15 GB >= its 12 GB minimum
    monkeypatch.setattr(gpus, "gpu_memory", lambda service, gpu: (4, True))
    assert "at least 8 GB" in gpus.model_blocker("upscale_seedvr2_3b", "kaggle", "NvidiaL4")
    assert "only the Kaggle" in gpus.model_blocker("upscale_x2", "colab", "T4")


def test_image_to_video_and_space_only_models():
    assert "keyframes" in gpus.model_blocker("ltx_video_i2v", "colab", "T4")
    assert gpus.model_blocker("ltx_video_i2v", "kaggle", "NvidiaTeslaT4") is None
    assert "Hugging Face Space" in gpus.model_blocker("pika_h3_flex_i2v", "kaggle", "NvidiaTeslaT4")
    assert gpus.model_blocker("pika_h3_flex_i2v", "huggingface", "ZeroGPU") is None


def test_tpu_rules():
    assert gpus.model_blocker("tpu_wan", "colab", "T4") == "TPU runs are only offered through Kaggle"
    assert gpus.model_blocker("tpu_wan", "kaggle", "NvidiaTeslaT4") == "needs the TPU v5e-8 accelerator"
    assert gpus.model_blocker("ltx_video", "kaggle", "TpuV5E8") == "needs a CUDA GPU, not a TPU"


def test_gated_model_needs_a_token(monkeypatch):
    assert "HF_TOKEN" in gpus.model_blocker("sd35_medium", "computer", "local")
    monkeypatch.setenv("HF_TOKEN", "x")
    assert gpus.model_blocker("sd35_medium", "computer", "local") is None
    assert "Hugging Face token" in gpus.model_blocker("sd35_medium", "kaggle", "NvidiaTeslaT4")


def test_blockers_table_is_consistent():
    table = gpus.blockers()
    assert table["upscale_flashvsr"]["kaggle"]["NvidiaTeslaT4"]
    assert "NvidiaL4" not in table["upscale_flashvsr"]["kaggle"]


def test_suggestions_validate_input():
    with pytest.raises(PlanError, match="choose a look"):
        gpus.suggestions("nonsense", "kaggle", "NvidiaTeslaT4")
    from studio_app import gpus as g
    import model_advisor
    look = next(iter(model_advisor.LOOKS))
    with pytest.raises(PlanError, match="where to run"):
        g.suggestions(look, "kaggle", "NoSuchGpu")
    out = g.suggestions(look, "kaggle", "NvidiaTeslaT4")
    assert out["service"] == "kaggle" and "steps" in out
