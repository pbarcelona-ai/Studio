"""catalog.json (models, GPUs) must stay well-formed; the network check lives in scripts/check_catalog.py."""
import check_catalog
from studio_app.config import CATALOG, GPUS, KAGGLE_GPU_GB, UPSCALE_MODELS, UPSCALE_SUFFIXES


def test_catalog_is_well_formed():
    assert check_catalog.problems_in_catalog(CATALOG) == []


def test_problems_are_reported():
    bad = {"hf_models": ["a"], "hf_vision_models": ["b"], "gpus": {"x": [["only-id"]]}}
    msgs = check_catalog.problems_in_catalog(bad)
    assert any("vision model b" in m for m in msgs) and any("not [id, label]" in m for m in msgs) and any("kaggle_gpu_gb" in m for m in msgs)


def test_derived_tables():
    assert KAGGLE_GPU_GB["NvidiaTeslaT4"] == 15
    assert all(isinstance(g, tuple) and len(g) == 2 for v in GPUS.values() for g in v)
    assert set(UPSCALE_SUFFIXES) == {"_" + k.removeprefix("upscale_") for k in UPSCALE_MODELS}


def test_every_space_has_the_fields_the_runner_needs():
    import hf_spaces
    for key, sp in hf_spaces.SPACES.items():
        assert {"kind", "space", "style", "api", "defaults", "status"} <= set(sp), key
        assert sp["status"] in ("checked", "api"), key
