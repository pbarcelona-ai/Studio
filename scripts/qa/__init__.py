"""Pre-render and post-render QA gate modules (slideshow_risk, composition_validator, visual_qa)."""
from __future__ import annotations

from .composition_validator import CompositionValidator, validate_composition
from .slideshow_risk import score_slideshow_risk
from .visual_qa import VisualQA, run_visual_qa

__all__ = [
    "CompositionValidator",
    "VisualQA",
    "run_visual_qa",
    "score_slideshow_risk",
    "validate_composition",
]
