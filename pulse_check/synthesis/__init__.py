"""Sonnet/Haiku synthesis — dedup, verbatim selection, addressability, briefs."""

from pulse_check.synthesis.anthropic_client import AnthropicClient
from pulse_check.synthesis.contracts import (
    BriefNarrative,
    BriefSection,
    Claim,
    NumericalDrift,
    ValidationResult,
)

__all__ = [
    "AnthropicClient",
    "BriefNarrative",
    "BriefSection",
    "Claim",
    "NumericalDrift",
    "ValidationResult",
]
