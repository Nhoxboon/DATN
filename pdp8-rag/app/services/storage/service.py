"""Storage service for handling PDF uploads to Supabase Storage."""

from pathlib import Path
from typing import Optional
from supabase import Client


class StorageService:
    """Service for managing PDF storage in Supabase."""

    def __init__(self, client: Client, bucket_name: str = "pdfs"):
        """
        Initialize storage service.

        Args:
            client: Supabase client instance
            bucket_name: Name of the storage bucket
        """
        self.client = client
        self.bucket_name = bucket_name

    def upload_pdf(self, file_path: str, destination_path: Optional[str] = None, upsert: bool = True) -> dict:
        """
        Upload a PDF file to Supabase Storage.

        Args:
            file_path: Path to the local PDF file
            destination_path: Destination path in storage (defaults to filename)
            upsert: If True, overwrite existing file

        Returns:
            Upload response with file URL and metadata
        """
        file_path_obj = Path(file_path)

        if not file_path_obj.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        if not destination_path:
            destination_path = file_path_obj.name

        # Upload file (with upsert option)
        with open(file_path, "rb") as f:
            if upsert:
                # Try to update first, if fails, upload new
                try:
                    response = self.client.storage.from_(self.bucket_name).update(
                        destination_path,
                        f,
                        file_options={"content-type": "application/pdf"}
                    )
                except Exception:
                    # If update fails, upload as new
                    response = self.client.storage.from_(self.bucket_name).upload(
                        destination_path,
                        f,
                        file_options={"content-type": "application/pdf"}
                    )
            else:
                response = self.client.storage.from_(self.bucket_name).upload(
                    destination_path,
                    f,
                    file_options={"content-type": "application/pdf"}
                )

        # Get public URL
        public_url = self.client.storage.from_(self.bucket_name).get_public_url(destination_path)

        return {
            "path": destination_path,
            "public_url": public_url,
            "response": response
        }

    def download_pdf(self, file_path: str, local_path: str) -> str:
        """
        Download a PDF file from Supabase Storage.

        Args:
            file_path: Path of the file in storage
            local_path: Local path to save the file

        Returns:
            Local file path
        """
        # Download file
        response = self.client.storage.from_(self.bucket_name).download(file_path)

        # Save to local file
        with open(local_path, "wb") as f:
            f.write(response)

        return local_path

    def delete_pdf(self, file_path: str) -> list:
        """
        Delete a PDF file from Supabase Storage.

        Args:
            file_path: Path of the file in storage

        Returns:
            Delete response
        """
        response = self.client.storage.from_(self.bucket_name).remove([file_path])
        return response

    def list_pdfs(self, folder: Optional[str] = None) -> list:
        """
        List PDF files in storage.

        Args:
            folder: Optional folder path to list files from

        Returns:
            List of file metadata
        """
        path = folder if folder else ""
        response = self.client.storage.from_(self.bucket_name).list(path)
        return response

    def get_public_url(self, file_path: str) -> str:
        """
        Get public URL for a file.

        Args:
            file_path: Path of the file in storage

        Returns:
            Public URL
        """
        return self.client.storage.from_(self.bucket_name).get_public_url(file_path)
