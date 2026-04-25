#!/usr/bin/env python3
"""Script to train and optimize multi-hop RAG."""

import sys
import warnings
from pathlib import Path

# Suppress warnings
warnings.filterwarnings("ignore", message="Failed to deep copy attribute")

# Add project root to Python path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import dspy
from app.core.config import get_settings, get_app_config
from app.db.dependencies import get_supabase_client
from app.services.embedding import EmbeddingService
from app.services.rag.retrieval import RetrievalService
from app.services.rag.multihop_rag import MultiHopRAG
from app.services.rag.trainer import load_training_data, optimize_rag


def main():
    """Train multi-hop RAG."""
    print("=" * 70)
    print("DSPy Multi-Hop RAG Training for PDP8")
    print("=" * 70)
    print()

    # Load configuration
    print("Loading configuration...")
    settings = get_settings()
    app_config = get_app_config()

    # Configure DSPy
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

    # Initialize multi-hop RAG
    print("Initializing Multi-Hop RAG module...")
    multihop_rag = MultiHopRAG(
        retrieval_service=retrieval_service,
        max_hops=app_config.rag.multihop.max_hops,
        passages_per_hop=app_config.rag.multihop.passages_per_hop
    )

    # Load training data
    print("\nLoading training data...")
    train_data, dev_data = load_training_data("app/training/qna.json")

    # Optimize multi-hop RAG
    print("\n" + "=" * 70)
    optimized_multihop = optimize_rag(
        rag_module=multihop_rag,
        train_data=train_data,
        dev_data=dev_data,
        max_bootstrapped_demos=4,
        max_labeled_demos=2
    )

    # Save optimized model
    print("\n" + "=" * 70)
    print("Saving Optimized Multi-Hop Model")
    print("=" * 70)

    output_path = Path("models/optimized_multihop_rag.json")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    optimized_multihop.save(str(output_path))
    print(f"\n✓ Optimized multi-hop model saved to: {output_path}")

    print("\n" + "=" * 70)
    print("Multi-Hop Training Complete!")
    print("=" * 70)
    print("\nThe optimized multi-hop RAG model is ready to use.")


if __name__ == "__main__":
    main()
