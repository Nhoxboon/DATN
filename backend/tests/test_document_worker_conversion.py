"""Tests for DOCX conversion before the PDF worker pipeline."""

from __future__ import annotations

import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch


os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
os.environ.setdefault("SUPABASE_ANON_KEY", "anon")
os.environ.setdefault("SUPABASE_SERVICE_KEY", "service")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("GOOGLE_API_KEY", "test")

from app.workers.tasks import document as document_tasks  # noqa: E402


class DocumentWorkerConversionTests(unittest.TestCase):
    def test_pdf_path_passes_through_unchanged(self) -> None:
        self.assertEqual(
            document_tasks._ensure_pdf_for_processing("/tmp/source.pdf", "Source"),
            "/tmp/source.pdf",
        )

    def test_docx_is_converted_to_stable_pdf_path(self) -> None:
        with TemporaryDirectory() as temp_dir:
            source_path = Path(temp_dir) / "source.docx"
            source_path.write_bytes(b"docx-bytes")

            def fake_soffice(args: list[str], **_kwargs: object) -> SimpleNamespace:
                output_dir = Path(args[args.index("--outdir") + 1])
                (output_dir / "source.pdf").write_bytes(b"%PDF-1.4")
                return SimpleNamespace(returncode=0, stderr="", stdout="")

            with patch.object(document_tasks.tempfile, "gettempdir", return_value=temp_dir), patch.object(
                document_tasks.subprocess,
                "run",
                side_effect=fake_soffice,
            ) as run:
                pdf_path = Path(document_tasks._ensure_pdf_for_processing(str(source_path), "Source"))

            self.assertEqual(pdf_path.name, document_tasks.safe_pdf_storage_path("Source"))
            self.assertIn("datn-docx-conversions", pdf_path.parts)
            self.assertEqual(pdf_path.read_bytes(), b"%PDF-1.4")
            run.assert_called_once()

    def test_docx_conversion_accepts_non_matching_libreoffice_output_name(self) -> None:
        with TemporaryDirectory() as temp_dir:
            source_path = Path(temp_dir) / "source.docx"
            source_path.write_bytes(b"docx-bytes")

            def fake_soffice(args: list[str], **_kwargs: object) -> SimpleNamespace:
                output_dir = Path(args[args.index("--outdir") + 1])
                (output_dir / "unexpected-name.pdf").write_bytes(b"%PDF-1.4")
                return SimpleNamespace(returncode=0, stderr="", stdout="convert ok")

            with patch.object(document_tasks.tempfile, "gettempdir", return_value=temp_dir), patch.object(
                document_tasks.subprocess,
                "run",
                side_effect=fake_soffice,
            ):
                pdf_path = Path(document_tasks._ensure_pdf_for_processing(str(source_path), "Source"))

            self.assertEqual(pdf_path.name, document_tasks.safe_pdf_storage_path("Source"))
            self.assertEqual(pdf_path.read_bytes(), b"%PDF-1.4")

    def test_docx_conversion_failure_raises_runtime_error(self) -> None:
        with TemporaryDirectory() as temp_dir:
            source_path = Path(temp_dir) / "source.docx"
            source_path.write_bytes(b"docx-bytes")

            with patch.object(document_tasks.tempfile, "gettempdir", return_value=temp_dir), patch.object(
                document_tasks.subprocess,
                "run",
                return_value=SimpleNamespace(returncode=1, stderr="conversion failed", stdout=""),
            ):
                with self.assertRaisesRegex(RuntimeError, "DOCX conversion failed"):
                    document_tasks._ensure_pdf_for_processing(str(source_path), "Source")

    def test_cleanup_conversion_workspace_removes_only_temp_conversion_dir(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "datn-docx-conversions"
            workspace = root / "docx-to-pdf-test"
            pdf_path = workspace / "source.pdf"
            workspace.mkdir(parents=True)
            pdf_path.write_bytes(b"%PDF-1.4")

            with patch.object(document_tasks.tempfile, "gettempdir", return_value=temp_dir):
                document_tasks._cleanup_conversion_workspace(pdf_path)

            self.assertFalse(workspace.exists())


if __name__ == "__main__":
    unittest.main()
