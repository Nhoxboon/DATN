#!/usr/bin/env python3
"""Script to train and optimize the DSPy RAG model."""

import sys
import warnings
from pathlib import Path

# Suppress known harmless warnings
warnings.filterwarnings("ignore", message="Failed to deep copy attribute")
warnings.filterwarnings("ignore", category=DeprecationWarning)

# Add project root to Python path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import dspy
from app.core.config import get_settings, get_app_config
from app.db.dependencies import get_supabase_client
from app.services.embedding import EmbeddingService
from app.services.rag.retrieval import RetrievalService
from app.services.rag.dspy_rag import RAGModule
from app.services.rag.trainer import load_training_data, optimize_rag, save_optimized_model


def main():
    """Train and optimize the RAG model."""
    print("=" * 70)
    print("DSPy RAG Training for PDP8 Regulation Analysis")
    print("=" * 70)
    print()

    # Load configuration
    print("Loading configuration...")
    settings = get_settings()
    app_config = get_app_config()

    # Configure DSPy with Gemini
    print(f"Configuring DSPy with {app_config.llm.gemini.model}...")
    lm = dspy.LM(
        model=f"gemini/{app_config.llm.gemini.model}",
        api_key=settings.google_api_key,
        temperature=app_config.llm.gemini.temperature,
        max_tokens=app_config.llm.gemini.max_tokens
    )
    dspy.settings.configure(lm=lm)

    # Initialize services
    print("Initializing services...")
    supabase_client = get_supabase_client()
    embedding_service = EmbeddingService(settings)
    retrieval_service = RetrievalService(
        supabase_client=supabase_client,
        embedding_service=embedding_service,
        top_k=app_config.rag.retrieval.top_k
    )

    # Initialize RAG module
    print("Initializing RAG module...")
    rag_module = RAGModule(
        retrieval_service=retrieval_service,
        num_passages=app_config.rag.retrieval.top_k
    )

    # Load training data
    print("\nLoading training data...")
    train_data, dev_data = load_training_data("app/training/qna.json")

    # Optimize RAG
    print("\n" + "=" * 70)
    optimized_rag = optimize_rag(
        rag_module=rag_module,
        train_data=train_data,
        dev_data=dev_data,
        max_bootstrapped_demos=4,
        max_labeled_demos=2
    )

    # Save optimized model
    print("\n" + "=" * 70)
    print("Saving Optimized Model")
    print("=" * 70)
    save_optimized_model(optimized_rag, "models/optimized_rag.json")

    print("\n" + "=" * 70)
    print("Training Complete!")
    print("=" * 70)
    print("\nThe optimized RAG model is ready to use.")
    print("You can now use it via the API or query script.")


if __name__ == "__main__":
    main()
