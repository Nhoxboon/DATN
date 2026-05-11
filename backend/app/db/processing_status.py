"""Repository for document processing status tracking."""

from typing import Optional
from datetime import datetime
from supabase import Client


class ProcessingStatus:
    """Document processing status values."""
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class ProcessingStatusRepository:
    """Repository for managing document processing status."""

    def __init__(self, client: Client):
        """
        Initialize repository with Supabase client.

        Args:
            client: Supabase client instance
        """
        self.client = client

    def create_status(
        self,
        notebook_id: str,
        user_id: str,
        document_name: str,
        task_id: str,
        total_chunks: Optional[int] = None
    ) -> dict:
        """
        Create or reset processing status record (upsert).

        Args:
            document_name: Name of the document
            task_id: Celery task ID
            total_chunks: Total number of chunks to process

        Returns:
            Created/updated status record
        """
        data = {
            "notebook_id": notebook_id,
            "user_id": user_id,
            "document_name": document_name,
            "status": ProcessingStatus.PENDING,
            "task_id": task_id,
            "total_chunks": total_chunks,
            "processed_chunks": 0,
            "error_message": None,
            "completed_at": None,
            "created_at": datetime.utcnow().isoformat(),
            "updated_at": datetime.utcnow().isoformat()
        }

        result = self.client.table("document_processing_status")\
            .upsert(data, on_conflict="notebook_id,document_name")\
            .execute()
        return result.data[0] if result.data else {}

    def update_status(
        self,
        notebook_id: str,
        document_name: str,
        status: str,
        processed_chunks: Optional[int] = None,
        total_chunks: Optional[int] = None,
        error_message: Optional[str] = None
    ) -> dict:
        """
        Update processing status.

        Args:
            document_name: Name of the document
            status: New status value
            processed_chunks: Number of chunks processed
            error_message: Error message if failed

        Returns:
            Updated status record
        """
        update_data = {
            "status": status,
            "updated_at": datetime.utcnow().isoformat()
        }

        if processed_chunks is not None:
            update_data["processed_chunks"] = processed_chunks

        if total_chunks is not None:
            update_data["total_chunks"] = total_chunks

        if error_message:
            update_data["error_message"] = error_message

        if status == ProcessingStatus.COMPLETED:
            update_data["completed_at"] = datetime.utcnow().isoformat()

        result = self.client.table("document_processing_status")\
            .update(update_data)\
            .eq("notebook_id", notebook_id)\
            .eq("document_name", document_name)\
            .execute()

        return result.data[0] if result.data else {}

    def get_status(self, notebook_id: str, document_name: str) -> Optional[dict]:
        """
        Get processing status for a document.

        Args:
            document_name: Name of the document

        Returns:
            Status record or None if not found
        """
        result = self.client.table("document_processing_status")\
            .select("*")\
            .eq("notebook_id", notebook_id)\
            .eq("document_name", document_name)\
            .execute()

        return result.data[0] if result.data else None

    def delete_status(self, notebook_id: str, document_name: str) -> bool:
        """
        Delete processing status record.

        Args:
            document_name: Name of the document

        Returns:
            True if deleted successfully
        """
        self.client.table("document_processing_status")\
            .delete()\
            .eq("notebook_id", notebook_id)\
            .eq("document_name", document_name)\
            .execute()

        return True

    def list_processing_documents(self, notebook_id: str | None = None) -> list[dict]:
        """
        List all documents currently being processed.

        Returns:
            List of processing status records
        """
        query = self.client.table("document_processing_status").select("*").eq("status", ProcessingStatus.PROCESSING)
        if notebook_id:
            query = query.eq("notebook_id", notebook_id)
        result = query.execute()

        return result.data if result.data else []

    def list_failed_documents(self, notebook_id: str | None = None) -> list[dict]:
        """
        List all documents that failed processing.

        Returns:
            List of failed status records
        """
        query = self.client.table("document_processing_status").select("*").eq("status", ProcessingStatus.FAILED)
        if notebook_id:
            query = query.eq("notebook_id", notebook_id)
        result = query.execute()

        return result.data if result.data else []


def get_processing_status_repository(client: Client) -> ProcessingStatusRepository:
    """
    Factory function to get processing status repository.

    Args:
        client: Supabase client

    Returns:
        ProcessingStatusRepository instance
    """
    return ProcessingStatusRepository(client)
