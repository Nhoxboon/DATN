#!/usr/bin/env python3
"""Script to process all regulation PDFs except PDP8 and sample documents."""

import sys
import time
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from app.workers.tasks.document import process_document_task
from app.db.dependencies import get_supabase_client
from app.db.processing_status import get_processing_status_repository


EXCLUDED_FILES = {
    "PDP8_full-with-annexes_EN.pdf",
    "pdp8.pdf",
    "sample-local-pdf.pdf"
}


def get_regulation_pdfs(uploads_dir: Path) -> list[Path]:
    """Get all PDF files in uploads directory except excluded ones."""
    all_pdfs = list(uploads_dir.glob("*.pdf"))
    return [pdf for pdf in all_pdfs if pdf.name not in EXCLUDED_FILES]


def process_single_document(file_path: Path, status_repo) -> bool:
    """Process a single document and monitor its progress."""
    document_name = file_path.stem
    file_size = file_path.stat().st_size / (1024 * 1024)

    print("=" * 60)
    print(f"Processing: {file_path.name}")
    print("=" * 60)
    print(f"Document: {document_name}")
    print(f"Path: {file_path}")
    print(f"Size: {file_size:.2f} MB")
    print("=" * 60)
    print()

    print("Submitting document processing task...")
    result = process_document_task.apply_async(
        args=[document_name, str(file_path)],
        queue="document_processing"
    )

    print(f"✓ Task submitted")
    print(f"  Task ID: {result.id}")
    print()
    print("Monitoring progress...")
    print()

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
                    print("✓ Processing Complete!")
                    print()
                    return True

                elif current_status == "failed":
                    print()
                    print()
                    print(f"✗ Processing Failed: {error}")
                    print()
                    return False

            time.sleep(2)

    except KeyboardInterrupt:
        print()
        print()
        print("Monitoring stopped. Processing continues in background.")
        print(f"Task ID: {result.id}")
        return None


def main():
    """Process all regulation PDFs."""
    uploads_dir = project_root / "uploads"

    if not uploads_dir.exists():
        print(f"❌ Error: Uploads directory not found at {uploads_dir}")
        return

    pdfs = get_regulation_pdfs(uploads_dir)

    if not pdfs:
        print("No PDFs found to process.")
        return

    print("=" * 60)
    print("Regulation Documents Processing")
    print("=" * 60)
    print(f"Total PDFs found: {len(pdfs)}")
    print(f"Excluded: {', '.join(EXCLUDED_FILES)}")
    print("=" * 60)
    print()

    print("Documents to process:")
    for i, pdf in enumerate(pdfs, 1):
        size = pdf.stat().st_size / (1024 * 1024)
        print(f"  {i:2d}. {pdf.name} ({size:.2f} MB)")
    print()

    response = input("Proceed with processing? (y/n): ")
    if response.lower() != 'y':
        print("Processing cancelled.")
        return

    print()
    supabase_client = get_supabase_client()
    status_repo = get_processing_status_repository(supabase_client)

    successful = 0
    failed = 0
    skipped = 0

    for i, pdf in enumerate(pdfs, 1):
        print(f"\n[{i}/{len(pdfs)}] Processing {pdf.name}...")
        result = process_single_document(pdf, status_repo)

        if result is True:
            successful += 1
        elif result is False:
            failed += 1
        else:
            skipped += 1

    print()
    print("=" * 60)
    print("Processing Summary")
    print("=" * 60)
    print(f"  Total documents: {len(pdfs)}")
    print(f"  Successful: {successful}")
    print(f"  Failed: {failed}")
    print(f"  Skipped: {skipped}")
    print("=" * 60)


if __name__ == "__main__":
    main()
