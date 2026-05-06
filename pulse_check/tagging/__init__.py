"""LOCAL LLM (Qwen via Ollama) tagging — aspects, deliberation, reasons."""

from pulse_check.tagging.aspect_classifier import (
    PROMPT_VERSION as ASPECT_PROMPT_VERSION,
)
from pulse_check.tagging.aspect_classifier import (
    TAXONOMY_VERSION,
    AspectClassifier,
    AspectPrediction,
    ProductContext,
)
from pulse_check.tagging.content_type_classifier import (
    PROMPT_VERSION as CONTENT_TYPE_PROMPT_VERSION,
)
from pulse_check.tagging.content_type_classifier import (
    ContentTypeClassifier,
    ContentTypePrediction,
)
from pulse_check.tagging.ollama import OllamaClient

__all__ = [
    "ASPECT_PROMPT_VERSION",
    "CONTENT_TYPE_PROMPT_VERSION",
    "TAXONOMY_VERSION",
    "AspectClassifier",
    "AspectPrediction",
    "ContentTypeClassifier",
    "ContentTypePrediction",
    "OllamaClient",
    "ProductContext",
]
