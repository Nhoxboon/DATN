"""DSPy modules for RAG."""

import dspy
from typing import List


class GenerateAnswer(dspy.Signature):
    """Generate an answer based on retrieved document context."""

    context: str = dspy.InputField(desc="Retrieved text chunks from user-provided documents")
    question: str = dspy.InputField(desc="User's question about the selected documents")
    answer: str = dspy.OutputField(desc="Detailed answer based on the regulation context")
    # answer: str = dspy.OutputField(desc="Detailed answer based only on the retrieved document context")


class RAG(dspy.Module):
    """DSPy RAG module for document-grounded queries."""

    def __init__(self):
        """Initialize RAG module."""
        super().__init__()
        self.generate_answer = dspy.ChainOfThought(GenerateAnswer)

    def forward(self, question: str, context: str):
        """
        Generate answer from question and retrieved context.

        Args:
            question: User's question
            context: Retrieved context from vector search

        Returns:
            Answer with reasoning
        """
        prediction = self.generate_answer(context=context, question=question)
        return prediction
