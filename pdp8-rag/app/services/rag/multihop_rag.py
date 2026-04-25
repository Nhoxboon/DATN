"""Multi-hop RAG implementation for complex queries."""

import dspy


class GenerateSearchQuery(dspy.Signature):
    """Generate a search query to find missing information."""

    context: str = dspy.InputField(desc="Current context gathered so far")
    question: str = dspy.InputField(desc="The question to answer")
    query: str = dspy.OutputField(desc="Search query for the next hop")


class GenerateAnswer(dspy.Signature):
    """Generate a comprehensive answer from multi-hop context with citations."""

    context: str = dspy.InputField(
        desc="Retrieved passages from multiple retrieval hops, may include markdown tables"
    )
    question: str = dspy.InputField(desc="Question to answer")
    answer: str = dspy.OutputField(
        desc="Comprehensive answer in clear paragraphs. Use **bold** for key terms. "
             "Cite sources with [N] format. Separate different aspects into distinct paragraphs with blank lines. "
             "IMPORTANT: If the context contains markdown tables with relevant data, preserve them in your answer using proper markdown table syntax. "
             "Present numerical data, lists of projects, or comparisons in table format when appropriate."
    )


class MultiHopRAG(dspy.Module):
    """Multi-hop RAG that performs iterative retrieval."""

    def __init__(self, retrieval_service, max_hops: int = 3, passages_per_hop: int = 3):
        """
        Initialize multi-hop RAG.

        Args:
            retrieval_service: Retrieval service for searching
            max_hops: Maximum number of retrieval hops
            passages_per_hop: Number of passages to retrieve per hop
        """
        super().__init__()
        self.retrieval_service = retrieval_service
        self.max_hops = max_hops
        self.passages_per_hop = passages_per_hop

        # Initialize modules
        self.generate_query = dspy.ChainOfThought(GenerateSearchQuery)
        self.generate_answer = dspy.ChainOfThought(GenerateAnswer)
        self.doc_names: list[str] | None = None  # Will be set by RAGService if filtering needed

    def forward(self, question: str, doc_names=None):
        """
        Answer question using multi-hop retrieval.

        Args:
            question: User's question
            doc_names: Optional list of document names to filter

        Returns:
            Prediction with answer and all retrieved context
        """
        # Use instance doc_names if not provided in forward call
        if doc_names is None:
            doc_names = self.doc_names

        # Reduce hops when filtering by specific documents (they're already focused)
        max_hops = 2 if doc_names else self.max_hops

        context_parts = []
        all_chunks = []

        for hop in range(max_hops):
            # First hop: search based on question
            # Subsequent hops: generate new query based on gathered context
            if hop == 0:
                search_query = question
            else:
                # Generate next search query based on what we've found so far
                current_context = "\n\n".join(context_parts)
                query_pred = self.generate_query(context=current_context, question=question)
                search_query = query_pred.query

            # Retrieve passages
            chunks = self.retrieval_service.retrieve(
                query=search_query,
                doc_names=doc_names
            )[:self.passages_per_hop]

            # Add to context
            all_chunks.extend(chunks)

            # FIX: Add formatted content to context_parts
            for chunk in chunks:
                context_parts.append(chunk.get("content", ""))

        # Format context with source numbering
        context = self.retrieval_service.format_context(all_chunks)

        # Generate final answer from all context
        prediction = self.generate_answer(context=context, question=question)

        # Add chunks to prediction
        prediction.chunks = all_chunks
        prediction.hops = max_hops

        return prediction
