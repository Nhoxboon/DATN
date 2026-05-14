"""Gemini context caching for document chunks."""

from typing import Optional, List, Dict, Any
from app.services.rag.cache_registry import (
    delete_cache_manifest as delete_manifest_from_redis,
    delete_cache_name as delete_cache_from_redis,
    get_cache_manifest as get_manifest_from_redis,
    get_cache_name as get_cache_from_redis,
    set_cache_manifest as set_manifest_in_redis,
    set_cache_name as set_cache_in_redis,
)
from google import genai
from google.genai import types


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

    def create_document_cache(
        self,
        cache_key: str,
        chunks: List[Dict[str, Any]],
        source_manifest: Optional[List[Dict[str, Any]]] = None,
        manifest_key: Optional[str] = None,
        ttl_hours: int = 1
    ) -> Optional[str]:
        """
        Create a context cache for document chunks.

        Args:
            cache_key: Redis cache key for this notebook/document scope
            chunks: List of chunk dictionaries with content
            source_manifest: Source metadata matching the cached source order
            manifest_key: Redis key for source_manifest
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
                metadata = chunk.get("metadata") or {}
                source_header = f"[Source {i}] (Pages: {page_range})"
                if metadata.get("has_visual", False):
                    source_header += (
                        f"\nContent type: {metadata.get('content_type', 'visual_description')} "
                        "extracted from image/figure descriptions"
                    )
                context_parts.append(f"{source_header}\n{content}\n")

            full_context = "\n\n".join(context_parts)

            # Check minimum token requirement (~1024 tokens = ~750 words = ~4500 chars)
            if len(full_context) < 4000:
                print(f"[CACHE] Context too small for caching: {len(full_context)} chars")
                return None

            # Create cache
            system_instruction = (
                "You are an expert document analyst capable of synthesizing information across various domains. "
                "Answer questions based on the provided document context. "
                # "answer only from the provided context, "
                "Use **bold** for key terms, cite sources only with [N] format, preserve tables, "
                "and treat image or figure descriptions as extracted evidence from document visuals."
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
            ttl_seconds = ttl_hours * 3600
            set_cache_in_redis(cache_key, cache_name, ttl_seconds)
            if manifest_key and source_manifest:
                set_manifest_in_redis(manifest_key, source_manifest, ttl_seconds)

            print(f"[CACHE] Created cache for {cache_key}: {cache_name}")
            return cache_name

        except Exception as e:
            print(f"[CACHE] Error creating cache: {e}")
            return None

    def get_cache_name(self, cache_key: str) -> Optional[str]:
        """Get cache name for a cache key."""
        return get_cache_from_redis(cache_key)

    def get_cache_manifest(self, manifest_key: str) -> Optional[List[Dict[str, Any]]]:
        """Get source manifest for a cache key."""
        return get_manifest_from_redis(manifest_key)

    def delete_cache(self, cache_key: str) -> bool:
        """Delete cache for a cache key."""
        cache_name = get_cache_from_redis(cache_key)
        if not cache_name:
            return False

        try:
            self.client.caches.delete(name=cache_name)
        except Exception as e:
            print(f"[CACHE] Error deleting cache: {e}")

        deleted = delete_cache_from_redis(cache_key)
        if deleted:
            print(f"[CACHE] Deleted cache for {cache_key}")
        return deleted

    def delete_cache_manifest(self, manifest_key: str) -> bool:
        """Delete source manifest for a cache key."""
        return delete_manifest_from_redis(manifest_key)

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
