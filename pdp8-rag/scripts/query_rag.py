#!/usr/bin/env python3
"""Script to query the RAG system."""

import sys
from pathlib import Path

# Add project root to Python path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from app.services.rag.service import RAGService


def main():
    """Query the RAG system interactively."""
    print("=" * 70)
    print("PDP8 RAG Query System")
    print("=" * 70)
    print("\nInitializing RAG service...")

    # Initialize service
    rag_service = RAGService(use_optimized=True)

    print(f"Mode: {rag_service.mode}")
    print(f"Model: {rag_service.app_config.llm.gemini.model}")
    if rag_service.mode == "adaptive":
        print("🤖 Adaptive mode: Will automatically choose single-hop or multi-hop based on question complexity")
    print("\nReady! Type 'exit' or 'quit' to stop.\n")

    # Interactive query loop
    while True:
        try:
            question = input("\n❓ Question: ").strip()

            if not question:
                continue

            if question.lower() in ['exit', 'quit', 'q']:
                print("\nGoodbye!")
                break

            print("\n🔍 Searching and generating answer...\n")

            # Query RAG
            result = rag_service.query(question)

            # Display strategy if adaptive
            if result.get('strategy'):
                print(f"\n🎯 Strategy: {result['strategy'].upper()}")
                if result.get('strategy_reasoning'):
                    print(f"   Reason: {result['strategy_reasoning']}")

            # Display answer
            print("=" * 70)
            print("📝 ANSWER")
            print("=" * 70)
            print(result['answer'])
            print()

            # Display reasoning if available
            if result.get('reasoning'):
                print("=" * 70)
                print("💭 REASONING")
                print("=" * 70)
                print(result['reasoning'])
                print()

            # Display sources
            if result.get('sources'):
                print("=" * 70)
                print(f"📚 SOURCES ({len(result['sources'])} retrieved)")
                print("=" * 70)
                for i, source in enumerate(result['sources'], 1):
                    print(f"\n[{i}] {source['document']}")
                    print(f"    Pages: {source['page_range']}")
                    print(f"    Similarity: {source['similarity']:.3f}")
                    content_preview = source['content'][:200] + "..." if len(source['content']) > 200 else source['content']
                    print(f"    Preview: {content_preview}")

        except KeyboardInterrupt:
            print("\n\nGoodbye!")
            break
        except Exception as e:
            print(f"\n❌ Error: {str(e)}")


if __name__ == "__main__":
    main()
