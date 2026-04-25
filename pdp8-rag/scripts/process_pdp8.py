#!/usr/bin/env python3
"""Script to process the PDP8 regulation document."""

import sys
import time
from pathlib import Path

# Add project root to Python path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from app.workers.tasks.document import process_document_task
from app.db.dependencies import get_supabase_client
from app.db.processing_status import get_processing_status_repository


def main():
    """Process the PDP8 document."""
    # Document details
    document_name = "PDP8_full-with-annexes_EN"
    file_path = "uploads/PDP8_full-with-annexes_EN.pdf"

    # Verify file exists
    if not Path(file_path).exists():
        print(f"❌ Error: File not found at {file_path}")
        return

    file_size = Path(file_path).stat().st_size / (1024 * 1024)  # Size in MB

    print("=" * 60)
    print("PDP8 Document Processing")
    print("=" * 60)
    print(f"Document: {document_name}")
    print(f"Path: {file_path}")
    print(f"Size: {file_size:.2f} MB")
    print("=" * 60)
    print()

    # Submit task
    print("Submitting document processing task...")
    result = process_document_task.apply_async(
        args=[document_name, file_path],
        queue="document_processing"
    )

    print(f"✓ Task submitted")
    print(f"  Task ID: {result.id}")
    print()

    # Monitor progress
    print("Monitoring progress...")
    print("(Press Ctrl+C to stop monitoring - processing will continue)")
    print()

    supabase_client = get_supabase_client()
    status_repo = get_processing_status_repository(supabase_client)

    try:
        while True:
            status = status_repo.get_status(document_name)

            if status:
                current_status = status.get("status")
                processed = status.get("processed_chunks", 0)
                total = status.get("total_chunks")
                error = status.get("error_message")

                if total:
                    progress = f"{processed}/{total} chunks ({processed*100//total}%)"
                else:
                    progress = f"{processed}/? chunks"

                print(f"\r  Status: {current_status.upper():<12} Progress: {progress:<20}", end="", flush=True)

                if current_status == "completed":
                    print()
                    print()
                    print("=" * 60)
                    print("Processing Complete!")
                    print("=" * 60)
                    print(f"  Document: {document_name}")
                    print(f"  Status: completed")
                    print(f"  Total Chunks: {total}")
                    print(f"  Processed: {processed}")
                    print("=" * 60)
                    break

                elif current_status == "failed":
                    print()
                    print()
                    print("=" * 60)
                    print("Processing Failed!")
                    print("=" * 60)
                    print(f"  Document: {document_name}")
                    print(f"  Status: failed")
                    print(f"  Error: {error}")
                    print("=" * 60)
                    break

            time.sleep(2)

    except KeyboardInterrupt:
        print()
        print()
        print("Monitoring stopped. Processing continues in background.")
        print(f"Task ID: {result.id}")


if __name__ == "__main__":
    main()
