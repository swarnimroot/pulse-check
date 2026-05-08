"""Sonnet/Haiku synthesis — dedup, verbatim selection, addressability, briefs."""

from pulse_check.synthesis.anthropic_client import AnthropicClient
from pulse_check.synthesis.citation_validator import validate_citations
from pulse_check.synthesis.contracts import (
    BriefNarrative,
    BriefSection,
    Claim,
    NumericalDrift,
    ValidationResult,
)
from pulse_check.synthesis.orchestrator import synthesize_a1

__all__ = [
    "AnthropicClient",
    "BriefNarrative",
    "BriefSection",
    "Claim",
    "NumericalDrift",
    "ValidationResult",
    "synthesize_a1",
    "validate_citations",
]
