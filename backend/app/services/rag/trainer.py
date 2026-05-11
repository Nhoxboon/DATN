"""Training and optimization for DSPy RAG."""

import json
import dspy
from pathlib import Path
from typing import List
from app.services.rag.dspy_rag import RAGModule, validate_answer, answer_correctness_metric


def create_training_example(question: str, answer: str) -> dspy.Example:
    """
    Create a training example for RAG.

    Args:
        question: User question
        answer: Gold standard answer

    Returns:
        DSPy Example with inputs set
    """
    return dspy.Example(question=question, answer=answer).with_inputs("question")


def load_training_data(json_path: str) -> tuple[List[dspy.Example], List[dspy.Example]]:
    """
    Load and split training data from JSON file.

    Args:
        json_path: Path to QnA JSON file

    Returns:
        Tuple of (train_examples, dev_examples)
    """
    with open(json_path, 'r', encoding='utf-8') as f:
        qna_data = json.load(f)

    examples = [
        create_training_example(
            question=item.get('question') or item.get('query'),
            answer=item['answer']
        )
        for item in qna_data
    ]

    # Split 70/30 train/dev for better evaluation
    split_idx = int(len(examples) * 0.7)
    train_examples = examples[:split_idx]
    dev_examples = examples[split_idx:]

    print(f"Loaded {len(train_examples)} training examples and {len(dev_examples)} dev examples")

    return train_examples, dev_examples


def optimize_rag(
    rag_module: RAGModule,
    train_data: List[dspy.Example],
    dev_data: List[dspy.Example],
    max_bootstrapped_demos: int = 4,
    max_labeled_demos: int = 2
):
    """
    Optimize RAG module using BootstrapFewShot.

    Args:
        rag_module: RAG module to optimize
        train_data: Training examples
        dev_data: Development set for evaluation
        max_bootstrapped_demos: Max bootstrapped demonstrations
        max_labeled_demos: Max labeled demonstrations

    Returns:
        Optimized RAG module
    """
    print("=" * 60)
    print("Starting RAG Optimization with BootstrapFewShot")
    print("=" * 60)

    # Create optimizer
    optimizer = dspy.BootstrapFewShot(
        metric=answer_correctness_metric,
        max_bootstrapped_demos=max_bootstrapped_demos,
        max_labeled_demos=max_labeled_demos,
        max_rounds=2  # Number of optimization rounds
    )

    # Compile (optimize) the RAG module
    print(f"\nOptimizing with {len(train_data)} training examples...")
    optimized_rag = optimizer.compile(
        rag_module,
        trainset=train_data
    )

    print("\n" + "=" * 60)
    print("Optimization Complete!")
    print("=" * 60)

    # Evaluate on dev set
    if dev_data:
        print(f"\nEvaluating on {len(dev_data)} dev examples...")
        evaluate_rag(optimized_rag, dev_data)

    return optimized_rag


def evaluate_rag(rag_module: RAGModule, eval_data: List[dspy.Example]):
    """
    Evaluate RAG module on a dataset.

    Args:
        rag_module: RAG module to evaluate
        eval_data: Evaluation examples
    """
    correct = 0
    total = len(eval_data)

    print(f"\n{'Question':<50} {'Validation':<15}")
    print("-" * 65)

    for example in eval_data:
        try:
            pred = rag_module(question=example.question)
            is_valid = validate_answer(example, pred)
            correct += int(is_valid)

            status = "✓ PASS" if is_valid else "✗ FAIL"
            question_preview = example.question[:47] + "..." if len(example.question) > 47 else example.question
            print(f"{question_preview:<50} {status:<15}")

        except Exception as e:
            print(f"{example.question[:47]+'...':<50} {'✗ ERROR':<15}")
            print(f"  Error: {str(e)}")

    accuracy = correct / total if total > 0 else 0
    print("-" * 65)
    print(f"\nAccuracy: {correct}/{total} ({accuracy*100:.1f}%)")


def save_optimized_model(optimized_rag: RAGModule, output_path: str):
    """
    Save optimized RAG module.

    Args:
        optimized_rag: Optimized RAG module
        output_path: Path to save the model
    """
    output_path_obj = Path(output_path)
    output_path_obj.parent.mkdir(parents=True, exist_ok=True)

    optimized_rag.save(str(output_path_obj))
    print(f"\n✓ Optimized model saved to: {output_path_obj}")


def load_optimized_model(model_path: str, retrieval_service) -> RAGModule:
    """
    Load optimized RAG module.

    Args:
        model_path: Path to saved model
        retrieval_service: Retrieval service instance

    Returns:
        Loaded RAG module
    """
    rag_module = RAGModule(retrieval_service=retrieval_service)
    rag_module.load(model_path)

    print(f"✓ Loaded optimized model from: {model_path}")
    return rag_module
