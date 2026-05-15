"""RAG service for document-grounded notebook queries."""

import dspy
import dspy.streaming  # type: ignore
import math
import re
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
from app.services.rag.cache_registry import build_document_cache_key, build_document_cache_manifest_key


CITATION_PATTERN = re.compile(r"\[(\d+(?:\s*,\s*\d+)*)\]")


def _citation_numbers(match: re.Match[str]) -> list[int]:
    return [int(value.strip()) for value in match.group(1).split(",")]


class RAGService:
    """Service for answering questions from user-provided document context."""

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
            optimized_model_path = self.app_config.rag.optimized_model_path
            # Domain-specific optimized models must be explicitly configured.
            if use_optimized and optimized_model_path and Path(optimized_model_path).exists():
                self.rag = load_optimized_model(
                    optimized_model_path,
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

    @staticmethod
    def _get_effective_doc_names(
        document_name: Optional[str] = None,
        doc_names: Optional[List[str]] = None
    ) -> Optional[List[str]]:
        """Normalize single-document and multi-document filters."""
        if doc_names is not None:
            return doc_names
        if document_name:
            return [document_name]
        return None

    @staticmethod
    def _coerce_chunk_id(value: Any) -> Optional[int]:
        if isinstance(value, bool) or value is None:
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _is_valid_similarity(value: Any) -> bool:
        if isinstance(value, bool) or value is None:
            return False
        try:
            return math.isfinite(float(value))
        except (TypeError, ValueError):
            return False

    @staticmethod
    def _format_source(chunk: Dict[str, Any]) -> Dict[str, Any]:
        """Format a retrieved chunk for API responses and frontend citations."""
        metadata = chunk.get("metadata") or {}
        source = {
            "content": chunk.get("content", ""),
            "document": chunk.get("document_name", ""),
            "pages": chunk.get("pages", []),
            "page_range": chunk.get("page_range", "unknown"),
            "metadata": metadata,
            "content_type": metadata.get("content_type", "text"),
            "has_visual": bool(metadata.get("has_visual", False)),
            "image_url": metadata.get("image_url")
        }
        chunk_id = RAGService._coerce_chunk_id(chunk.get("chunk_id"))
        if chunk_id is not None:
            source["chunk_id"] = chunk_id
        if RAGService._is_valid_similarity(chunk.get("similarity")):
            source["similarity"] = float(chunk["similarity"])
        return source

    @staticmethod
    def _manifest_has_chunk_ids(source_manifest: List[Dict[str, Any]]) -> bool:
        return all(
            RAGService._coerce_chunk_id(source.get("chunk_id")) is not None
            for source in source_manifest
        )

    async def _attach_cached_source_similarities(
        self,
        question: str,
        notebook_id: str,
        source_manifest: List[Dict[str, Any]],
        sources: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Attach fresh embedding similarity scores to manifest-backed cached citations."""
        import asyncio

        cited_keys: list[tuple[str, int]] = []
        cited_docs: set[str] = set()
        chunk_counts_by_doc: dict[str, int] = {}

        for manifest_source in source_manifest:
            document = str(manifest_source.get("document") or "")
            chunk_id = self._coerce_chunk_id(manifest_source.get("chunk_id"))
            if document and chunk_id is not None:
                chunk_counts_by_doc[document] = chunk_counts_by_doc.get(document, 0) + 1

        for source in sources:
            document = str(source.get("document") or "")
            chunk_id = self._coerce_chunk_id(source.get("chunk_id"))
            if not document or chunk_id is None:
                raise ValueError("Cached citation source is missing document or chunk_id.")
            cited_keys.append((document, chunk_id))
            cited_docs.add(document)

        query_embedding = await asyncio.to_thread(
            self.retrieval_service.embedding_service.embed_text,
            question
        )
        if not query_embedding:
            raise ValueError("Could not generate query embedding for cached relevance scoring.")

        scores_by_key: dict[tuple[str, int], float] = {}
        for document in sorted(cited_docs):
            limit = chunk_counts_by_doc.get(document, 0)
            if limit <= 0:
                raise ValueError(f"Cached manifest has no chunk count for document '{document}'.")

            results = await asyncio.to_thread(
                self.retrieval_service.doc_repo.search_similar,
                query_embedding=query_embedding,
                notebook_id=notebook_id,
                limit=limit,
                document_name=document
            )
            for result in results:
                result_document = str(result.get("document_name") or document)
                result_chunk_id = self._coerce_chunk_id(result.get("chunk_id"))
                similarity = result.get("similarity")
                if result_chunk_id is not None and self._is_valid_similarity(similarity):
                    scores_by_key[(result_document, result_chunk_id)] = float(similarity)

        scored_sources: List[Dict[str, Any]] = []
        for source, key in zip(sources, cited_keys):
            if key not in scores_by_key:
                raise ValueError(f"Could not resolve cached relevance score for {key[0]} chunk {key[1]}.")
            scored_source = dict(source)
            scored_source["similarity"] = scores_by_key[key]
            scored_sources.append(scored_source)

        return scored_sources

    @staticmethod
    def _resolve_manifest_citations(
        answer: str,
        source_manifest: List[Dict[str, Any]]
    ) -> Optional[tuple[str, List[Dict[str, Any]]]]:
        """Rewrite cached answer citations to match sources from the cached source manifest."""
        matches = list(CITATION_PATTERN.finditer(answer))
        if not matches:
            return None

        source_index_map: dict[int, int] = {}
        resolved_sources: List[Dict[str, Any]] = []

        for match in matches:
            for source_number in _citation_numbers(match):
                if source_number < 1 or source_number > len(source_manifest):
                    return None
                if source_number not in source_index_map:
                    source_index_map[source_number] = len(resolved_sources) + 1
                    resolved_sources.append(source_manifest[source_number - 1])

        def replace_citation(match: re.Match[str]) -> str:
            compact_numbers = []
            seen_numbers = set()
            for source_number in _citation_numbers(match):
                compact_number = source_index_map[source_number]
                if compact_number not in seen_numbers:
                    compact_numbers.append(str(compact_number))
                    seen_numbers.add(compact_number)
            return f"[{', '.join(compact_numbers)}]"

        return CITATION_PATTERN.sub(replace_citation, answer), resolved_sources

    def query(
        self,
        question: str,
        notebook_id: str,
        document_name: Optional[str] = None,
        doc_names: Optional[List[str]] = None
    ) -> Dict[str, Any]:
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
        effective_doc_names = self._get_effective_doc_names(document_name, doc_names)

        scope_token = self.retrieval_service.set_notebook_scope(notebook_id)
        try:
            # Run RAG with doc_ids if provided
            print("[TIMING] Starting DSPy RAG call...")
            if effective_doc_names is not None:
                prediction = self.rag(question=question, doc_names=effective_doc_names)
            else:
                prediction = self.rag(question=question)
            print(f"[TIMING] DSPy RAG completed in {time.time() - start_time:.2f}s")
        finally:
            self.retrieval_service.reset_notebook_scope(scope_token)

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
                self._format_source(chunk)
                for chunk in prediction.chunks
            ]

        return response

    async def query_stream(
        self,
        question: str,
        notebook_id: str,
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
        effective_doc_names = self._get_effective_doc_names(document_name, doc_names)
        scope_token = self.retrieval_service.set_notebook_scope(notebook_id)

        # Fast path: Use cached context for document-filtered queries (single or multiple)
        if effective_doc_names and len(effective_doc_names) <= 3:  # Support up to 3 documents with caching
            # Create a notebook-scoped combined cache key for multiple documents
            cache_key = build_document_cache_key(notebook_id, effective_doc_names)
            manifest_key = build_document_cache_manifest_key(notebook_id, effective_doc_names)
            cache_name = self.cache_service.get_cache_name(cache_key)
            source_manifest = self.cache_service.get_cache_manifest(manifest_key)

            # Old cache entries created before manifests are unsafe for citation display.
            if cache_name and not source_manifest:
                print(f"[CACHE] Cache manifest missing for {cache_key}; recreating cache")
                self.cache_service.delete_cache(cache_key)
                cache_name = None
            elif cache_name and source_manifest and not self._manifest_has_chunk_ids(source_manifest):
                print(f"[CACHE] Cache manifest missing chunk ids for {cache_key}; recreating cache")
                self.cache_service.delete_cache(cache_key)
                self.cache_service.delete_cache_manifest(manifest_key)
                cache_name = None
                source_manifest = None

            # If cache doesn't exist, create it
            if not cache_name:
                print(f"[CACHE] Creating cache for documents: {', '.join(effective_doc_names)}")
                start = time.time()
                # Get ALL chunks from the specified documents (not query-filtered)
                chunks = await asyncio.to_thread(
                    self.retrieval_service.doc_repo.get_all_chunks_by_names,
                    effective_doc_names,
                    notebook_id
                )
                print(f"[CACHE] Fetched {len(chunks)} total chunks from {len(effective_doc_names)} document(s)")
                source_manifest = [
                    self._format_source(chunk)
                    for chunk in chunks
                ]
                cache_name = await asyncio.to_thread(
                    self.cache_service.create_document_cache,
                    cache_key,
                    chunks,
                    source_manifest,
                    manifest_key,
                    ttl_hours=1
                )
                source_manifest = self.cache_service.get_cache_manifest(manifest_key)
                print(f"[CACHE] Cache created in {time.time() - start:.2f}s")
                if cache_name and (
                    not source_manifest or not self._manifest_has_chunk_ids(source_manifest)
                ):
                    print(f"[CACHE] Cache manifest still missing chunk ids for {cache_key}; skipping cache path")
                    self.cache_service.delete_cache(cache_key)
                    self.cache_service.delete_cache_manifest(manifest_key)
                    cache_name = None
                    source_manifest = None

            # Use cached generation if cache exists
            if cache_name and source_manifest:
                num_docs = len(effective_doc_names)
                strategy = f"cached-{'single' if num_docs == 1 else 'multi'}-hop"
                print(f"[CACHE] Using cached context for {num_docs} document(s)")
                try:
                    cached_answer = await asyncio.to_thread(
                        self.cache_service.generate_with_cache,
                        cache_name=cache_name,
                        question=question,
                        temperature=self.app_config.llm.gemini.temperature,
                        max_tokens=self.app_config.llm.gemini.max_tokens
                    )

                    resolved = self._resolve_manifest_citations(cached_answer, source_manifest)
                    if not resolved:
                        raise ValueError("Cached answer did not produce resolvable source citations.")

                    answer, sources = resolved
                    sources = await self._attach_cached_source_similarities(
                        question,
                        notebook_id,
                        source_manifest,
                        sources
                    )

                    # Stream the validated cached answer after citation resolution.
                    for token in re.split(r"(\s+)", answer):
                        if token:
                            yield {"type": "token", "content": token}
                            if token.strip():
                                await asyncio.sleep(0.01)

                    # Yield metadata with sources
                    yield {
                        "type": "metadata",
                        "strategy": strategy,
                        "strategy_reasoning": (
                            f"Using cached context from {num_docs} document(s) with manifest-backed citations"
                        ),
                        "sources": sources,
                        "is_optimized": True
                    }
                    self.retrieval_service.reset_notebook_scope(scope_token)
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
                    async for item in self._query_stream_impl(question, notebook_id, None, effective_doc_names):
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
                    result = await asyncio.to_thread(self.query, question, notebook_id, None, effective_doc_names)
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
        self.retrieval_service.reset_notebook_scope(scope_token)

    async def _query_stream_impl(
        self,
        question: str,
        notebook_id: str,
        document_name: Optional[str] = None,
        doc_names: Optional[List[str]] = None
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """Internal implementation of query_stream within DSPy context."""
        import asyncio
        effective_doc_names = self._get_effective_doc_names(document_name, doc_names)
        scope_token = self.retrieval_service.set_notebook_scope(notebook_id)

        # Set doc_ids on RAG module if provided
        if effective_doc_names is not None and hasattr(self.rag, 'doc_names'):
            setattr(self.rag, "doc_names", effective_doc_names)

        # For adaptive RAG, we need to specify which predictor to stream from
        # Since the complexity is assessed first, we'll stream from the chosen strategy
        if self.mode == "adaptive":
            # Type narrowing for adaptive RAG
            assert isinstance(self.rag, AdaptiveRAG)

            # Set doc_names on sub-modules
            if effective_doc_names is not None:
                self.rag.single_hop.doc_names = effective_doc_names
                self.rag.multi_hop.doc_names = effective_doc_names

            # Use optimized strategy selection (skip assessment for filtered docs)
            if effective_doc_names is not None and len(effective_doc_names) <= 2:
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
            output_stream = stream_module(question=question, doc_names=effective_doc_names)  # type: ignore
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
            output_stream = stream_rag(question=question, doc_names=effective_doc_names)  # type: ignore
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
                    self._format_source(chunk)
                    for chunk in final_prediction.chunks
                ]

            yield metadata
        self.retrieval_service.reset_notebook_scope(scope_token)
