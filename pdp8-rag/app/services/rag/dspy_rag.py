"""DSPy RAG implementation with retrieval and optimization."""

import dspy


class GenerateAnswer(dspy.Signature):
    """Generate a comprehensive answer from context with citations."""

    context: str = dspy.InputField(
        desc="Retrieved passages from PDP8 regulation document, may include markdown tables"
    )
    question: str = dspy.InputField(
        desc="User's question about Vietnam's electricity development plan"
    )
    answer: str = dspy.OutputField(
        desc="Comprehensive answer in clear paragraphs. Use **bold** for key terms. "
             "Cite sources with [N] format. Separate different aspects into distinct paragraphs with blank lines. "
             "IMPORTANT: If the context contains markdown tables with relevant data, preserve them in your answer using proper markdown table syntax. "
             "Present numerical data, lists of projects, or comparisons in table format when appropriate."
    )


class RAGModule(dspy.Module):
    """RAG module with integrated retrieval and generation."""

    def __init__(self, retrieval_service, num_passages: int = 5):
        """
        Initialize RAG module.

        Args:
            retrieval_service: Service for retrieving relevant passages
            num_passages: Number of passages to retrieve
        """
        super().__init__()
        self.retrieval_service = retrieval_service
        self.num_passages = num_passages
        self.generate_answer = dspy.ChainOfThought(GenerateAnswer)
        self.doc_names: list[str] | None = None  # Will be set by RAGService if filtering needed

    def forward(self, question: str, doc_names=None):
        """
        Answer a question using retrieval and generation.

        Args:
            question: User's question
            doc_names: Optional list of document names to filter

        Returns:
            DSPy prediction with answer and reasoning
        """
        # Use instance doc_ids if not provided in forward call
        if doc_names is None:
            doc_names = self.doc_names

        # Retrieve relevant passages
        chunks = self.retrieval_service.retrieve(
            query=question,
            doc_names=doc_names
        )

        # Format context with source numbering
        context = self.retrieval_service.format_context(chunks[:self.num_passages])

        # Generate answer
        prediction = self.generate_answer(context=context, question=question)

        # Add chunks to prediction
        prediction.chunks = chunks[:self.num_passages]

        return prediction


def validate_answer(example, pred, trace=None):
    """
    Validation metric for RAG answers.

    Checks if the answer is substantive and relevant.

    Args:
        example: Training example with question and gold answer
        pred: Prediction from the model
        trace: Optional trace for debugging

    Returns:
        Boolean indicating if answer is valid
    """
    # Check if answer exists and has reasonable length
    answer = pred.answer if hasattr(pred, 'answer') else ""

    if not answer or len(answer.strip()) < 50:
        return False

    generic_phrases = [
        "i don't know",
        "no information",
        "cannot answer",
        "unable to",
        "sorry",
        "i apologize"
    ]
    
    answer_lower = answer.lower()
    
    if any(phrase in answer_lower for phrase in generic_phrases):
        return False
    
    sentence_count = answer.count('.') + answer.count('?') + answer.count('!')
    if sentence_count < 2:
        return False
    answer_lower = answer.lower()
    question_lower = example.question.lower()

    key_terms = [
        word for word in question_lower.split()
        if len(word) > 4 and word not in ['what', 'when', 'where', 'which', 'are']
    ]

    mentions = sum(1 for term in key_terms if term in answer_lower)

    return mentions >= max(1, len(key_terms) // 3)


def answer_correctness_metric(example, pred, trace=None):
    """
    Metric to evaluate answer correctness using LLM as judge.

    Args:
        example: Training example with gold answer
        pred: Prediction from the model
        trace: Optional trace for debugging

    Returns:
        Score between 0 and 1
    """
    # Use DSPy's LLM to evaluate answer quality
    class EvaluateAnswer(dspy.Signature):
        """Evaluate if the predicted answer correctly addresses the question."""
        question: str = dspy.InputField()
        gold_answer: str = dspy.InputField(desc="Reference answer")
        predicted_answer: str = dspy.InputField(desc="Generated answer to evaluate")
        evaluation: str = dspy.OutputField(
            desc="Evaluation result: 'correct' if answer is accurate and complete, 'partial' if partially correct, 'incorrect' if wrong"
        )

    evaluator = dspy.Predict(EvaluateAnswer)

    try:
        result = evaluator(
            question=example.question,
            gold_answer=example.answer,
            predicted_answer=pred.answer if hasattr(pred, 'answer') else ""
        )

        eval_lower = result.evaluation.lower()
        if 'correct' in eval_lower and 'incorrect' not in eval_lower:
            return 1.0
        elif 'partial' in eval_lower:
            return 0.5
        else:
            return 0.0
    except:
        # Fallback to simple validation
        return 1.0 if validate_answer(example, pred, trace) else 0.0
