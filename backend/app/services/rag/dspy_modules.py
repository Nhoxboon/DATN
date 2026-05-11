"""DSPy modules for RAG."""

import dspy
from typing import List


class GenerateAnswer(dspy.Signature):
    """Generate an answer based on retrieved context from PDP8 regulation."""

    context: str = dspy.InputField(desc="Retrieved text chunks from PDP8 regulation document")
    question: str = dspy.InputField(desc="User's question about the regulation")
    answer: str = dspy.OutputField(desc="Detailed answer based on the regulation context")


class RAG(dspy.Module):
    """DSPy RAG module for PDP8 regulation queries."""

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
