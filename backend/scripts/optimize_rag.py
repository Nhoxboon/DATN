from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Make the backend package importable regardless of the current directory.
BACKEND_ROOT = Path(__file__).resolve().parent.parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

DEFAULT_DATASET = "app/training/training_dataset_multitopic.json"
DEFAULT_OUTPUT = "models/optimized_rag_multitopic.json"


def _resolve(path_str: str) -> Path:
    """Resolve a path relative to the backend root if it is not absolute."""
    path = Path(path_str)
    return path if path.is_absolute() else (BACKEND_ROOT / path)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Optimize the DSPy RAG module with BootstrapFewShot."
    )
    parser.add_argument(
        "--dataset",
        default=DEFAULT_DATASET,
        help=f"Path to the Q&A JSON dataset (default: {DEFAULT_DATASET}).",
    )
    parser.add_argument(
        "--output",
        default=DEFAULT_OUTPUT,
        help=f"Where to save the compiled model (default: {DEFAULT_OUTPUT}).",
    )
    parser.add_argument(
        "--max-bootstrapped-demos",
        type=int,
        default=4,
        help="Max bootstrapped demonstrations (default: 4).",
    )
    parser.add_argument(
        "--max-labeled-demos",
        type=int,
        default=2,
        help="Max labeled demonstrations (default: 2).",
    )
    parser.add_argument(
        "--notebook-id",
        required=True,
        help=(
            "Notebook id to scope retrieval to. Retrieval is mandatory in "
            "BootstrapFewShot, so this must be a notebook whose ingested "
            "documents match the dataset for demos to bootstrap usefully."
        ),
    )
    args = parser.parse_args()

    # Imported here so --help works even without the full runtime/credentials.
    from app.services.rag.dspy_rag import RAGModule
    from app.services.rag.service import RAGService
    from app.services.rag.trainer import (
        load_training_data,
        optimize_rag,
        save_optimized_model,
    )

    dataset_path = _resolve(args.dataset)
    output_path = _resolve(args.output)

    if not dataset_path.exists():
        print(f"✗ Dataset not found: {dataset_path}")
        return 1

    # Reuse production wiring: this configures the DSPy LM (Gemini) and builds
    # the retrieval service. We only borrow `retrieval_service` from it.
    print("Initializing RAG service (configuring DSPy + retrieval)...")
    service = RAGService(use_optimized=False, configure_dspy=True)

    rag_module = RAGModule(retrieval_service=service.retrieval_service)

    print(f"Loading training data from: {dataset_path}")
    train_data, dev_data = load_training_data(str(dataset_path))

    # Retrieval is scoped per request via a ContextVar; set it for the whole
    # (single-threaded) compile/eval run, then reset.
    print(f"Scoping retrieval to notebook: {args.notebook_id}")
    scope_token = service.retrieval_service.set_notebook_scope(args.notebook_id)
    try:
        optimized_rag = optimize_rag(
            rag_module,
            train_data,
            dev_data,
            max_bootstrapped_demos=args.max_bootstrapped_demos,
            max_labeled_demos=args.max_labeled_demos,
        )
    finally:
        service.retrieval_service.reset_notebook_scope(scope_token)

    save_optimized_model(optimized_rag, str(output_path))

    print("\nNext step: set `rag.optimized_model_path` in config.yaml to:")
    print(f"  {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
