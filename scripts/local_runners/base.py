"""Abstract base class for all local GPU inference runners."""
from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable
from typing import Any

ProgressCallback = Callable[[dict[str, Any]], None]


class LocalRunner(ABC):
    """Contract implemented by every local inference backend (ComfyUI, sd-cli, Wan2GP, Audio, WanDiffusers)."""

    name: str = "base"

    @abstractmethod
    def capabilities(self) -> dict[str, Any]:
        """Return supported tasks, models, and hardware requirements."""

    @abstractmethod
    def is_installed(self) -> bool:
        """Return True when the runner's binary/environment is ready locally."""

    @abstractmethod
    def install(self, on_progress: ProgressCallback | None = None, **kwargs: Any) -> dict[str, Any]:
        """Provision or verify the runner locally."""

    @abstractmethod
    def run(self, spec: dict[str, Any], on_progress: ProgressCallback | None = None) -> dict[str, Any]:
        """Execute one inference request and return output file paths and metadata."""

    @abstractmethod
    def cancel(self) -> None:
        """Cancel any active inference job or child process group."""
