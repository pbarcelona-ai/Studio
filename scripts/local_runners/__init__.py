"""Unified local GPU inference runners, router, model-pack manager, asset cache, and memory lease arbitrator."""
from .asset_cache import AssetCache, asset_cache_enabled, compute_cache_key, default_max_total_bytes
from .base import LocalRunner, ProgressCallback
from .comfyui_runner import ComfyUIRunner, parse_ws_preview_frame, relay_ws_preview_frame
from .gpu_lease import (
    DEFAULT_48G_THRESHOLD_GB,
    LeaseManager,
    LeaseResult,
    acquire_llm_lease,
    acquire_media_lease,
    get_default_manager,
)
from .pantry import Meter, Pantry, apply_inputs, model_key, pick_outputs, resolve_values, validate_app
from .router import LocalAudioRunner, select_runner
from .sd_cli_runner import SdCliRunner, describe_exit_code, pick_binary_asset, rank_windows_assets
from .wan2gp_runner import Wan2GPProgressParser, Wan2GPRunner, normalize_mcp_url
from .wan_diffusers_runner import WanDiffusersRunner, free_wan_pipelines

__all__ = [
    "AssetCache",
    "ComfyUIRunner",
    "DEFAULT_48G_THRESHOLD_GB",
    "LeaseManager",
    "LeaseResult",
    "LocalAudioRunner",
    "LocalRunner",
    "Meter",
    "Pantry",
    "ProgressCallback",
    "SdCliRunner",
    "Wan2GPProgressParser",
    "Wan2GPRunner",
    "WanDiffusersRunner",
    "acquire_llm_lease",
    "acquire_media_lease",
    "apply_inputs",
    "asset_cache_enabled",
    "compute_cache_key",
    "default_max_total_bytes",
    "describe_exit_code",
    "free_wan_pipelines",
    "get_default_manager",
    "model_key",
    "normalize_mcp_url",
    "parse_ws_preview_frame",
    "pick_binary_asset",
    "pick_outputs",
    "rank_windows_assets",
    "relay_ws_preview_frame",
    "resolve_values",
    "select_runner",
    "validate_app",
]
