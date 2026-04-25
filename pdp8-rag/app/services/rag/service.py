"""RAG service for PDP8 regulation queries."""

import dspy
import dspy.streaming  # type: ignore
from pathlib import Path
from typing import Dict, Any, AsyncGenerator, Union, Optional, List
from app.core.config import get_settings, get_app_config
from app.db.dependencies import get_supabase_client
from app.services.embedding import EmbeddingService
from app.services.rag.retrieval import RetrievalService
from app.services.rag.dspy_rag import RAGModule
from app.services.rag.multihop_rag import MultiHopRAG
from app.services.rag.adaptive_rag import AdaptiveRAG
from app.services.rag.trainer import load_optimized_model
from app.services.rag.gemini_cache import GeminiCacheService


class RAGService:
    """Service for answering questions about PDP8 regulation using optimized RAG."""

    def __init__(self, use_optimized: bool = True, configure_dspy: bool = True):
        """
        Initialize RAG service.

        Args:
            use_optimized: Whether to use the optimized model (default: True)
            configure_dspy: Whether to configure DSPy settings (default: True)
        """
        # Load configuration
        self.settings = get_settings()
        self.app_config = get_app_config()
        self.rag: Union[AdaptiveRAG, MultiHopRAG, RAGModule, dspy.Module]

        # Configure DSPy only if requested (to avoid async task conflicts)
        # Note: For async contexts, DSPy configuration should be done once at startup
        # Individual async tasks should use dspy.context() if needed
        if configure_dspy:
            lm = dspy.LM(
                model=f"gemini/{self.app_config.llm.gemini.model}",
                api_key=self.settings.google_api_key,
                temperature=self.app_config.llm.gemini.temperature,
                max_tokens=self.app_config.llm.gemini.max_tokens
            )
            # Use ChatAdapter for better structured output support with Pydantic models
            dspy.settings.configure(lm=lm, adapter=dspy.ChatAdapter())

        # Initialize services
        supabase_client = get_supabase_client()
        embedding_service = EmbeddingService(self.settings)
        self.retrieval_service = RetrievalService(
            supabase_client=supabase_client,
            embedding_service=embedding_service,
            top_k=self.app_config.rag.retrieval.top_k,
            use_reranking=self.app_config.rag.retrieval.use_reranking
        )

        # Initialize Gemini cache service for fast document-filtered queries
        self.cache_service = GeminiCacheService(
            api_key=self.settings.google_api_key,
            model=self.app_config.llm.gemini.model
        )

        # Load RAG module based on mode
        mode = self.app_config.rag.mode.lower()

        if mode == "adaptive":
            # Use adaptive RAG that chooses strategy based on query
            self.rag = AdaptiveRAG(
                retrieval_service=self.retrieval_service,
                single_hop_passages=self.app_config.rag.retrieval.top_k,
                max_hops=self.app_config.rag.multihop.max_hops,
                passages_per_hop=self.app_config.rag.multihop.passages_per_hop
            )
            self.mode = "adaptive"
            self.is_optimized = False
        elif mode == "multi-hop":
            # Force multi-hop RAG
            self.rag = MultiHopRAG(
                retrieval_service=self.retrieval_service,
                max_hops=self.app_config.rag.multihop.max_hops,
                passages_per_hop=self.app_config.rag.multihop.passages_per_hop
            )
            self.mode = "multi-hop"
            self.is_optimized = False
        elif mode == "single-hop":
            # Use single-hop (optimized if available)
            if use_optimized and Path("models/optimized_rag.json").exists():
                self.rag = load_optimized_model(
                    "models/optimized_rag.json",
                    self.retrieval_service
                )
                self.is_optimized = True
            else:
                self.rag = RAGModule(
                    retrieval_service=self.retrieval_service,
                    num_passages=self.app_config.rag.retrieval.top_k
                )
                self.is_optimized = False
            self.mode = "single-hop"
        else:
            raise ValueError(f"Invalid RAG mode: {mode}. Must be 'adaptive', 'single-hop', or 'multi-hop'.")

    def query(self, question: str, document_name: Optional[str] = None, doc_names: Optional[List[str]] = None) -> Dict[str, Any]:
        """
        Answer a question using RAG.

        Args:
            question: User's question
            document_name: Document to search (default: None - search all documents)
            doc_names: Optional list of document names to filter (takes precedence over document_name)

        Returns:
            Dictionary with answer, reasoning, and source chunks
        """
        import time
        start_time = time.time()

        # Run RAG with doc_ids if provided
        print("[TIMING] Starting DSPy RAG call...")
        if doc_names is not None:
            prediction = self.rag(question=question, doc_names=doc_names)
        else:
            prediction = self.rag(question=question)
        print(f"[TIMING] DSPy RAG completed in {time.time() - start_time:.2f}s")

        # Extract response
        response = {
            "question": question,
            "answer": prediction.answer if hasattr(prediction, 'answer') else str(prediction),
            "reasoning": prediction.rationale if hasattr(prediction, 'rationale') else None,
            "sources": [],
            "mode": self.mode,
            "strategy": prediction.strategy if hasattr(prediction, 'strategy') else self.mode,
            "strategy_reasoning": prediction.strategy_reasoning if hasattr(prediction, 'strategy_reasoning') else None,
            "is_optimized": self.is_optimized
        }

        # Add source chunks if available
        if hasattr(prediction, 'chunks'):
            response["sources"] = [
                {
                    "content": chunk.get("content", ""),
                    "document": chunk.get("document_name", ""),
                    "pages": chunk.get("pages", []),
                    "page_range": chunk.get("page_range", "unknown"),
                    "similarity": chunk.get("similarity", 0.0)
                }
                for chunk in prediction.chunks
            ]

        return response

    async def query_stream(
        self,
        question: str,
        document_name: Optional[str] = None,
        doc_names: Optional[List[str]] = None
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        Answer a question using RAG with TRUE DSPy streaming.

        Runs DSPy streaming in a separate thread with its own event loop
        to avoid async context conflicts.

        Args:
            question: User's question
            document_name: Document to search (default: None - search all documents)
            doc_names: Optional list of document names to filter (takes precedence over document_name)

        Yields:
            Dictionaries with streaming tokens and final metadata
        """
        import asyncio
        import queue
        import threading
        import time

        # Fast path: Use cached context for document-filtered queries (single or multiple)
        if doc_names and len(doc_names) <= 3:  # Support up to 3 documents with caching
            # Create a combined cache key for multiple documents
            cache_key = "|".join(sorted(doc_names))
            cache_name = self.cache_service.get_cache_name(cache_key)

            # If cache doesn't exist, create it
            if not cache_name:
                print(f"[CACHE] Creating cache for documents: {', '.join(doc_names)}")
                start = time.time()
                # Get ALL chunks from the specified documents (not query-filtered)
                chunks = await asyncio.to_thread(
                    self.retrieval_service.doc_repo.get_all_chunks_by_names,
                    doc_names
                )
                print(f"[CACHE] Fetched {len(chunks)} total chunks from {len(doc_names)} document(s)")
                cache_name = await asyncio.to_thread(
                    self.cache_service.create_document_cache,
                    cache_key,
                    chunks,
                    ttl_hours=1
                )
                print(f"[CACHE] Cache created in {time.time() - start:.2f}s")

            # Use cached generation if cache exists
            if cache_name:
                num_docs = len(doc_names)
                strategy = f"cached-{'single' if num_docs == 1 else 'multi'}-hop"
                print(f"[CACHE] Using cached context for {num_docs} document(s)")
                try:
                    # Do retrieval in parallel for source attribution (needed by FE)
                    retrieval_task = asyncio.create_task(
                        asyncio.to_thread(
                            self.retrieval_service.retrieve,
                            query=question,
                            doc_names=doc_names
                        )
                    )

                    # Stream from cached context (fast generation)
                    async for token in self.cache_service.generate_with_cache_stream(
                        cache_name=cache_name,
                        question=question,
                        temperature=self.app_config.llm.gemini.temperature,
                        max_tokens=self.app_config.llm.gemini.max_tokens
                    ):
                        yield {"type": "token", "content": token}

                    # Wait for retrieval to finish and get sources
                    retrieved_chunks = await retrieval_task
                    sources = [
                        {
                            "content": chunk.get("content", ""),
                            "document": chunk.get("document_name", ""),
                            "pages": chunk.get("pages", []),
                            "page_range": chunk.get("page_range", "unknown"),
                            "similarity": chunk.get("similarity", 0.0)
                        }
                        for chunk in retrieved_chunks
                    ]

                    # Yield metadata with sources
                    yield {
                        "type": "metadata",
                        "strategy": strategy,
                        "strategy_reasoning": f"Using cached context from {num_docs} document(s) with retrieval for sources",
                        "sources": sources,
                        "is_optimized": True
                    }
                    return
                except Exception as e:
                    print(f"[CACHE] Error using cache, falling back to DSPy: {e}")

        # Queue to pass chunks from DSPy thread to main async context
        chunk_queue = queue.Queue()

        # Run DSPy streaming in a separate thread with its own event loop
        def run_dspy_streaming():
            """Run DSPy streaming in a separate thread."""
            # Create new event loop for this thread
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

            try:
                # Run the streaming implementation
                async def stream():
                    async for item in self._query_stream_impl(question, document_name, doc_names):
                        chunk_queue.put(("chunk", item))
                    chunk_queue.put(("done", None))

                loop.run_until_complete(stream())
            except Exception as e:
                chunk_queue.put(("error", str(e)))
            finally:
                loop.close()

        # Start DSPy streaming thread
        thread = threading.Thread(target=run_dspy_streaming, daemon=True)
        thread.start()

        # Yield chunks as they arrive from the queue
        while True:
            # Non-blocking get with timeout
            try:
                msg_type, data = chunk_queue.get(timeout=0.1)

                if msg_type == "chunk":
                    yield data
                elif msg_type == "done":
                    break
                elif msg_type == "error":
                    # Fallback to simulated streaming on error
                    import re
                    result = await asyncio.to_thread(self.query, question, document_name)
                    answer = result.get("answer", "")
                    tokens = re.split(r'(\s+)', answer)

                    for token in tokens:
                        if token:
                            yield {"type": "token", "content": token}
                            if token.strip():
                                await asyncio.sleep(0.02)

                    yield {
                        "type": "metadata",
                        "strategy": result.get("strategy"),
                        "strategy_reasoning": result.get("strategy_reasoning"),
                        "sources": result.get("sources", [])
                    }
                    break

            except queue.Empty:
                # No chunks available yet, continue waiting
                await asyncio.sleep(0.01)
                continue

    async def _query_stream_impl(
        self,
        question: str,
        document_name: Optional[str] = None,
        doc_names: Optional[List[str]] = None
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """Internal implementation of query_stream within DSPy context."""
        import asyncio

        # Set doc_ids on RAG module if provided
        if doc_names is not None and hasattr(self.rag, 'doc_names'):
            self.rag.doc_names = doc_names

        # For adaptive RAG, we need to specify which predictor to stream from
        # Since the complexity is assessed first, we'll stream from the chosen strategy
        if self.mode == "adaptive":
            # Type narrowing for adaptive RAG
            assert isinstance(self.rag, AdaptiveRAG)

            # Set doc_names on sub-modules
            if doc_names is not None:
                self.rag.single_hop.doc_names = doc_names
                self.rag.multi_hop.doc_names = doc_names

            # Use optimized strategy selection (skip assessment for filtered docs)
            if doc_names is not None and len(doc_names) <= 2:
                # Force single-hop for document-filtered queries
                target_module = self.rag.single_hop
                strategy = "single-hop"
                strategy_reasoning = "Using single-hop for document-filtered query (focused scope)"
            else:
                # Assess complexity for unfiltered or multi-document queries
                assessment = self.rag.assess_complexity(question=question)

                if hasattr(assessment, 'complexity') and assessment.complexity == "complex":
                    target_module = self.rag.multi_hop
                    strategy = "multi-hop"
                    strategy_reasoning = assessment.reasoning
                else:
                    target_module = self.rag.single_hop
                    strategy = "single-hop"
                    strategy_reasoning = assessment.reasoning

            # Stream from the selected module
            stream_listeners = [
                dspy.streaming.StreamListener(  # type: ignore
                    signature_field_name="answer",
                    predict=target_module.generate_answer  # type: ignore
                )
            ]

            stream_module = dspy.streamify(target_module, stream_listeners=stream_listeners)  # type: ignore
            output_stream = stream_module(question=question, doc_names=doc_names)  # type: ignore
        else:
            # For single-hop or multi-hop mode, stream directly
            if self.mode == "single-hop":
                stream_listeners = [
                    dspy.streaming.StreamListener(  # type: ignore
                        signature_field_name="answer",
                        predict=self.rag.generate_answer  # type: ignore
                    )
                ]
            else:  # multi-hop
                stream_listeners = [
                    dspy.streaming.StreamListener(  # type: ignore
                        signature_field_name="answer",
                        predict=self.rag.generate_answer  # type: ignore
                    )
                ]

            stream_rag = dspy.streamify(self.rag, stream_listeners=stream_listeners)  # type: ignore
            output_stream = stream_rag(question=question, doc_names=doc_names)  # type: ignore
            strategy = self.mode
            strategy_reasoning = None

        final_prediction = None
        streamed_tokens = False

        async for chunk in output_stream:
            if isinstance(chunk, dspy.streaming.StreamResponse):  # type: ignore
                # True streaming token received from DSPy
                streamed_tokens = True
                yield {
                    "type": "token",
                    "content": chunk.chunk
                }
            elif isinstance(chunk, dspy.Prediction):
                # Final prediction received
                final_prediction = chunk

                # If DSPy didn't stream (Gemini doesn't support it), simulate streaming
                if not streamed_tokens and hasattr(chunk, 'answer'):
                    answer = chunk.answer
                    # Stream word-by-word while preserving newlines
                    import re
                    # Split by spaces but keep newlines as separate tokens
                    tokens = re.split(r'(\s+)', answer)
                    for i, token in enumerate(tokens):
                        if token:  # Skip empty strings
                            yield {
                                "type": "token",
                                "content": token
                            }
                            # Only delay for actual words, not whitespace
                            if token.strip():
                                await asyncio.sleep(0.015)  # 15ms delay per word

        # Yield final metadata (sources, strategy, etc.)
        if final_prediction:
            # Add strategy info for adaptive mode
            if self.mode == "adaptive":
                final_prediction.strategy = strategy
                final_prediction.strategy_reasoning = strategy_reasoning

            metadata = {
                "type": "metadata",
                "reasoning": final_prediction.rationale if hasattr(final_prediction, 'rationale') else None,
                "mode": self.mode,
                "strategy": final_prediction.strategy if hasattr(final_prediction, 'strategy') else self.mode,
                "strategy_reasoning": final_prediction.strategy_reasoning if hasattr(final_prediction, 'strategy_reasoning') else None,
                "is_optimized": self.is_optimized,
                "sources": []
            }

            # Add source chunks if available
            if hasattr(final_prediction, 'chunks'):
                metadata["sources"] = [
                    {
                        "content": chunk.get("content", ""),
                        "document": chunk.get("document_name", ""),
                        "pages": chunk.get("pages", []),
                        "page_range": chunk.get("page_range", "unknown"),
                        "similarity": chunk.get("similarity", 0.0)
                    }
                    for chunk in final_prediction.chunks
                ]

            yield metadata
