"""Repository pattern for database operations."""

from typing import List, Dict, Any, Optional, Protocol
from supabase import Client


class DocumentRepository(Protocol):
    """Protocol for document repository."""

    def insert_chunk(
        self,
        document_name: str,
        chunk_id: int,
        content: str,
        embedding: List[float],
        metadata: Optional[Dict[str, Any]] = None,
        pages: Optional[List[int]] = None,
        page_range: Optional[str] = None
    ) -> Dict[str, Any]: ...

    def search_similar(
        self,
        query_embedding: List[float],
        limit: int = 5,
        document_name: Optional[str] = None,
        doc_names: Optional[List[str]] = None
    ) -> List[Dict[str, Any]]: ...

    def list_documents(self) -> List[str]: ...

    def get_document_name_by_id(self, doc_id: int) -> Optional[str]: ...

    def delete_by_name(self, document_name: str) -> bool: ...


class SupabaseDocumentRepository:
    """Supabase implementation of document repository."""

    def __init__(self, client: Client):
        """
        Initialize repository with Supabase client.

        Args:
            client: Supabase client instance
        """
        self.client = client

    def insert_chunk(
        self,
        document_name: str,
        chunk_id: int,
        content: str,
        embedding: List[float],
        metadata: Optional[Dict[str, Any]] = None,
        pages: Optional[List[int]] = None,
        page_range: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Insert a document chunk with its embedding and page information.

        Args:
            document_name: Name of the source document
            chunk_id: Chunk identifier
            content: Text content of the chunk
            embedding: Vector embedding (3072 dimensions for Gemini)
            metadata: Additional metadata
            pages: List of page numbers this chunk spans
            page_range: Page range string (e.g., "1-3")

        Returns:
            Inserted record
        """
        data = {
            "document_name": document_name,
            "chunk_id": chunk_id,
            "content": content,
            "embedding": embedding,
            "metadata": metadata or {},
            "pages": pages,
            "page_range": page_range
        }

        result = self.client.table("documents").insert(data).execute()
        if result.data and isinstance(result.data, list) and len(result.data) > 0:
            return result.data[0]  # type: ignore[return-value]
        return {}

    def search_similar(
        self,
        query_embedding: List[float],
        limit: int = 5,
        document_name: Optional[str] = None,
        doc_names: Optional[List[str]] = None
    ) -> List[Dict[str, Any]]:
        """
        Perform similarity search using pgvector.

        Args:
            query_embedding: Query vector embedding
            limit: Number of results to return
            document_name: Optional filter by single document name
            doc_names: Optional filter by list of document names (takes precedence over document_name)

        Returns:
            List of similar documents with content and metadata
        """
        # If doc_names provided, search across those documents
        if doc_names is not None and len(doc_names) > 0:
            # Use RPC function with IN clause simulation
            # We'll call the RPC for each document and combine results
            all_results = []
            for doc in doc_names:
                rpc_params = {
                    "query_embedding": query_embedding,
                    "match_count": limit,
                    "filter_document": doc
                }
                result = self.client.rpc("match_documents", rpc_params).execute()
                if result.data and isinstance(result.data, list):
                    all_results.extend(result.data)

            # Sort combined results by similarity and return top-k
            all_results.sort(key=lambda x: x.get("similarity", 0), reverse=True)
            return all_results[:limit]

        # Original RPC-based search
        rpc_params = {
            "query_embedding": query_embedding,
            "match_count": limit
        }

        if document_name:
            rpc_params["filter_document"] = document_name

        result = self.client.rpc("match_documents", rpc_params).execute()
        if result.data and isinstance(result.data, list):
            return result.data  # type: ignore[return-value]
        return []

    def list_documents(self) -> List[str]:
        """
        Get list of all document names.

        Returns:
            List of unique document names
        """
        all_docs = set()
        page_size = 1000
        offset = 0

        while True:
            result = self.client.table("documents").select("document_name").range(offset, offset + page_size - 1).execute()

            if not result.data:
                break

            for doc in result.data:
                if isinstance(doc, dict) and "document_name" in doc:
                    all_docs.add(str(doc["document_name"]))

            if len(result.data) < page_size:
                break

            offset += page_size

        return sorted(list(all_docs))

    def get_document_name_by_id(self, doc_id: int) -> Optional[str]:
        """
        Get document name by document ID.

        Args:
            doc_id: Document ID

        Returns:
            Document name or None if not found
        """
        result = self.client.table("documents").select("document_name").eq("id", doc_id).limit(1).execute()
        if result.data and isinstance(result.data, list) and len(result.data) > 0:
            return result.data[0].get("document_name")
        return None

    def get_all_chunks_by_names(self, doc_names: List[str]) -> List[Dict[str, Any]]:
        """
        Get all chunks for specified documents.

        Args:
            doc_names: List of document names

        Returns:
            List of all chunks from the specified documents
        """
        all_chunks = []
        page_size = 1000

        for doc_name in doc_names:
            offset = 0
            while True:
                result = self.client.table("documents")\
                    .select("content, page_range, pages, document_name")\
                    .eq("document_name", doc_name)\
                    .range(offset, offset + page_size - 1)\
                    .execute()

                if not result.data:
                    break

                all_chunks.extend(result.data)

                if len(result.data) < page_size:
                    break

                offset += page_size

        return all_chunks

    def delete_by_name(self, document_name: str) -> bool:
        """
        Delete all chunks of a document.

        Args:
            document_name: Name of the document to delete

        Returns:
            True if successful
        """
        self.client.table("documents").delete().eq("document_name", document_name).execute()
        return True


def get_document_repository(client: Client) -> DocumentRepository:
    """
    Factory function to get document repository.

    Args:
        client: Supabase client

    Returns:
        Document repository instance
    """
    return SupabaseDocumentRepository(client)
