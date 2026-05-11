"""Embedding service using Google Generative AI."""

from typing import List
from google import genai
from app.core.config import Settings


class EmbeddingService:
    """Service for generating embeddings using Gemini."""

    def __init__(self, settings: Settings):
        """
        Initialize embedding service with Gemini.

        Args:
            settings: Environment settings
        """
        self.client = genai.Client(api_key=settings.google_api_key)
        self.model = "gemini-embedding-001"

    def embed_text(self, text: str) -> List[float]:
        """
        Generate embedding for a single text.

        Args:
            text: Text to embed

        Returns:
            Embedding vector (768 dimensions)
        """
        result = self.client.models.embed_content(model=self.model, contents=text)
        return (
            result.embeddings[0].values
            if result.embeddings and result.embeddings[0].values
            else []
        )

    def embed_query(self, query: str) -> List[float]:
        """
        Generate embedding for a query.

        Args:
            query: Query text to embed

        Returns:
            Embedding vector (768 dimensions)
        """
        result = self.client.models.embed_content(model=self.model, contents=query)
        return (
            result.embeddings[0].values
            if result.embeddings and result.embeddings[0].values
            else []
        )

    def embed_batch(self, texts: List[str]) -> List[List[float]]:
        """
        Generate embeddings for multiple texts.

        Args:
            texts: List of texts to embed

        Returns:
            List of embedding vectors
        """
        embeddings = []
        for text in texts:
            embedding = self.embed_text(text)
            embeddings.append(embedding)
        return embeddings
