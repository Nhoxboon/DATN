"""Gemini context caching for document chunks."""

from typing import Optional, List, Dict, Any
from app.services.rag.cache_registry import get_cache_name as get_cache_from_redis, set_cache_name as set_cache_in_redis
from google import genai
from google.genai import types
import os
from datetime import datetime, timedelta


class GeminiCacheService:
    """Service for managing Gemini context caches for document chunks."""

    def __init__(self, api_key: str, model: str = "gemini-2.5-flash"):
        """
        Initialize cache service.

        Args:
            api_key: Google API key
            model: Gemini model name
        """
        self.client = genai.Client(api_key=api_key)
        self.model = model
        self._cache_registry: Dict[str, str] = {}  # doc_name -> cache_name

    def create_document_cache(
        self,
        doc_name: str,
        chunks: List[Dict[str, Any]],
        ttl_hours: int = 1
    ) -> Optional[str]:
        """
        Create a context cache for document chunks.

        Args:
            doc_name: Document name
            chunks: List of chunk dictionaries with content
            ttl_hours: Cache time-to-live in hours

        Returns:
            Cache name if successful, None otherwise
        """
        try:
            # Format chunks into context
            context_parts = []
            for i, chunk in enumerate(chunks, 1):
                content = chunk.get("content", "")
                page_range = chunk.get("page_range", "unknown")
                context_parts.append(
                    f"[Source {i}] (Pages: {page_range})\n{content}\n"
                )

            full_context = "\n\n".join(context_parts)

            # Check minimum token requirement (~1024 tokens = ~750 words = ~4500 chars)
            if len(full_context) < 4000:
                print(f"[CACHE] Context too small for caching: {len(full_context)} chars")
                return None

            # Create cache
            system_instruction = (
                "You are an expert analyst of Vietnam's Power Development Plan VIII (PDP8). "
                "Answer questions based on the provided document context. "
                "Use **bold** for key terms, cite sources with [N] format, and preserve tables."
            )

            cache = self.client.caches.create(
                model=self.model,
                config=types.CreateCachedContentConfig(
                    system_instruction=system_instruction,
                    contents=[{"role": "user", "parts": [{"text": full_context}]}],
                    ttl=f"{ttl_hours * 3600}s"  # Convert hours to seconds
                )
            )

            cache_name = cache.name
            set_cache_in_redis(doc_name, cache_name, ttl_hours * 3600)

            print(f"[CACHE] Created cache for {doc_name}: {cache_name}")
            return cache_name

        except Exception as e:
            print(f"[CACHE] Error creating cache: {e}")
            return None

    def get_cache_name(self, doc_name: str) -> Optional[str]:
        """Get cache name for a document."""
        return get_cache_from_redis(doc_name)

    def delete_cache(self, doc_name: str) -> bool:
        """Delete cache for a document."""
        cache_name = self._cache_registry.get(doc_name)
        if not cache_name:
            return False

        try:
            self.client.caches.delete(name=cache_name)
            del self._cache_registry[doc_name]
            print(f"[CACHE] Deleted cache for {doc_name}")
            return True
        except Exception as e:
            print(f"[CACHE] Error deleting cache: {e}")
            return False

    def generate_with_cache(
        self,
        cache_name: str,
        question: str,
        temperature: float = 0.7,
        max_tokens: int = 8000
    ) -> str:
        """
        Generate answer using cached context.

        Args:
            cache_name: Name of the cache to use
            question: User question
            temperature: Generation temperature
            max_tokens: Maximum tokens to generate

        Returns:
            Generated answer
        """
        try:
            response = self.client.models.generate_content(
                model=self.model,
                contents=question,
                config=types.GenerateContentConfig(
                    cached_content=cache_name,
                    temperature=temperature,
                    max_output_tokens=max_tokens
                )
            )

            return response.text

        except Exception as e:
            print(f"[CACHE] Error generating with cache: {e}")
            raise

    async def generate_with_cache_stream(
        self,
        cache_name: str,
        question: str,
        temperature: float = 0.7,
        max_tokens: int = 8000
    ):
        """
        Generate answer using cached context with streaming.

        Args:
            cache_name: Name of the cache to use
            question: User question
            temperature: Generation temperature
            max_tokens: Maximum tokens to generate

        Yields:
            Response chunks
        """
        import asyncio

        try:
            # Run sync streaming in thread pool
            response = await asyncio.to_thread(
                self.client.models.generate_content_stream,
                model=self.model,
                contents=question,
                config=types.GenerateContentConfig(
                    cached_content=cache_name,
                    temperature=temperature,
                    max_output_tokens=max_tokens
                )
            )

            # Iterate sync generator in thread pool
            for chunk in response:
                if chunk.text:
                    yield chunk.text

        except Exception as e:
            print(f"[CACHE] Error streaming with cache: {e}")
            raise
