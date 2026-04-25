"""Test Celery parallel processing workflow."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import time
from app.workers.tasks.document import process_document_task
from app.db.dependencies import get_supabase_client
from app.db.processing_status import get_processing_status_repository


def test_document_processing():
    """Test parallel document processing with Celery."""

    # Document to process
    pdf_path = "uploads/sample-local-pdf.pdf"
    document_name = Path(pdf_path).stem

    print(f"\n{'='*60}")
    print(f"Testing Celery Parallel Processing")
    print(f"{'='*60}")
    print(f"Document: {document_name}")
    print(f"Path: {pdf_path}")
    print(f"{'='*60}\n")

    # Submit task
    print("Submitting document processing task...")
    result = process_document_task.apply_async(
        args=[document_name, pdf_path],
        queue="document_processing"
    )

    print(f"✓ Task submitted")
    print(f"  Task ID: {result.id}")
    print(f"  Status: {result.status}")

    # Monitor progress
    print(f"\nMonitoring progress...")
    supabase_client = get_supabase_client()
    status_repo = get_processing_status_repository(supabase_client)

    last_status = None
    while True:
        status = status_repo.get_status(document_name)

        if status and status.get("status") != last_status:
            last_status = status.get("status")
            processed = status.get("processed_chunks", 0)
            total = status.get("total_chunks", "?")

            print(f"\n  Status: {last_status.upper()}")
            if total != "?":
                print(f"  Progress: {processed}/{total} chunks")

            if last_status in ["completed", "failed"]:
                break

        time.sleep(2)

    # Final result
    print(f"\n{'='*60}")
    print(f"Processing Complete!")
    print(f"{'='*60}")

    if status:
        print(f"  Document: {status.get('document_name')}")
        print(f"  Status: {status.get('status')}")
        print(f"  Total Chunks: {status.get('total_chunks')}")
        print(f"  Processed: {status.get('processed_chunks')}")

        if status.get('error_message'):
            print(f"  Error: {status.get('error_message')}")

    print(f"{'='*60}\n")

    return status


if __name__ == "__main__":
    test_document_processing()
