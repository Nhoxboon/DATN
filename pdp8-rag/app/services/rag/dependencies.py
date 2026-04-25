"""RAG service dependencies."""

import dspy
from functools import lru_cache
from app.core.config import get_settings, get_app_config
from app.services.rag.service import RAGService


_rag_service_instance = None


def initialize_dspy():
    """
    Initialize DSPy settings once at startup.

    Note: This should be called before any async tasks are created.
    DSPy only allows configure() to be called from one async context.
    """
    settings = get_settings()
    app_config = get_app_config()

    lm = dspy.LM(
        model=f"gemini/{app_config.llm.gemini.model}",
        api_key=settings.google_api_key,
        temperature=app_config.llm.gemini.temperature,
        max_tokens=app_config.llm.gemini.max_tokens
    )

    # Configure DSPy with ChatAdapter for better Pydantic support
    try:
        dspy.settings.configure(lm=lm, adapter=dspy.ChatAdapter())
        print("[INFO] DSPy configured successfully")
    except RuntimeError as e:
        # If called from wrong async context, this will fail
        # In that case, configuration should happen in a different way
        print(f"[WARNING] DSPy configuration failed: {e}")
        print("[INFO] DSPy may need to use context() instead of global configure()")


def get_rag_service() -> RAGService:
    """
    Get or create RAG service singleton.

    Returns:
        RAG service instance
    """
    global _rag_service_instance

    if _rag_service_instance is None:
        _rag_service_instance = RAGService(use_optimized=True, configure_dspy=False)

    return _rag_service_instance
