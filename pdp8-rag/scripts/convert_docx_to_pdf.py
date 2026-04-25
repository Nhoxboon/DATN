#!/usr/bin/env python3
"""Convert all DOCX files in uploads directory to PDF format."""

import os
import subprocess
from pathlib import Path


def find_docx_files(root_dir: str) -> list[Path]:
    """Find all DOCX files recursively."""
    root = Path(root_dir)
    return list(root.rglob("*.docx"))


def convert_docx_to_pdf(docx_path: Path) -> bool:
    """
    Convert a DOCX file to PDF using LibreOffice.

    Args:
        docx_path: Path to the DOCX file

    Returns:
        True if conversion successful, False otherwise
    """
    output_dir = docx_path.parent

    try:
        # Try LibreOffice command (macOS/Linux)
        result = subprocess.run(
            [
                "soffice",
                "--headless",
                "--convert-to", "pdf",
                "--outdir", str(output_dir),
                str(docx_path)
            ],
            capture_output=True,
            text=True,
            timeout=60
        )

        if result.returncode == 0:
            print(f"✓ Converted: {docx_path.name}")
            return True
        else:
            print(f"✗ Failed: {docx_path.name}")
            print(f"  Error: {result.stderr}")
            return False

    except FileNotFoundError:
        print("Error: LibreOffice (soffice) not found.")
        print("Install with: brew install --cask libreoffice")
        return False
    except subprocess.TimeoutExpired:
        print(f"✗ Timeout: {docx_path.name}")
        return False
    except Exception as e:
        print(f"✗ Error converting {docx_path.name}: {e}")
        return False


def main():
    """Convert all DOCX files to PDF."""
    uploads_dir = Path(__file__).parent.parent / "uploads"

    if not uploads_dir.exists():
        print(f"Error: Uploads directory not found: {uploads_dir}")
        return

    print(f"Scanning for DOCX files in: {uploads_dir}")
    docx_files = find_docx_files(uploads_dir)

    if not docx_files:
        print("No DOCX files found.")
        return

    print(f"Found {len(docx_files)} DOCX files\n")

    successful = 0
    failed = 0

    for docx_file in docx_files:
        if convert_docx_to_pdf(docx_file):
            successful += 1
        else:
            failed += 1

    print(f"\n{'='*50}")
    print(f"Conversion complete:")
    print(f"  Successful: {successful}")
    print(f"  Failed: {failed}")
    print(f"  Total: {len(docx_files)}")

    if successful > 0:
        print(f"\nPDF files are saved in the same directories as the DOCX files.")


if __name__ == "__main__":
    main()
