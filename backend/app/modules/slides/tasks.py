"""Celery task for generating notebook slide decks."""

from __future__ import annotations

import logging
import tempfile
from pathlib import Path
from typing import Any

from google import genai

from app.core.config import get_app_config, get_settings
from app.db.dependencies import get_supabase_client
from app.db.repository import get_document_repository
from app.modules.slides.constants import MAX_CONTEXT_CHARS
from app.modules.slides.coverage_utils import _expected_coverage_topics
from app.modules.slides.pillow_pdf_renderer import _render_deck_pdf_for_config
from app.modules.slides.repository import get_slide_deck_repository
from app.modules.slides.slide_generator import (
    _build_context,
    _generate_deck,
    _summarize_context,
)
from app.modules.slides.visual_processor import _materialize_visuals, _visual_candidates
from app.workers.celery_app import celery_app


logger = logging.getLogger(__name__)


@celery_app.task(bind=True, max_retries=2, default_retry_delay=60)
def generate_slide_deck_task(
    self,
    deck_id: str,
    notebook_id: str,
    user_id: str,
    document_names: list[str],
) -> dict[str, Any]:
    """Generate a grounded slide deck, render a raster PDF, and upload it."""
    settings = get_settings()
    client = get_supabase_client()
    repository = get_slide_deck_repository(client)
    document_repository = get_document_repository(client)
    if not repository.get(deck_id):
        logger.info("Slide deck task skipped because deck no longer exists deck_id=%s", deck_id)
        return _cancelled_result(deck_id, "missing")

    app_config = get_app_config()
    genai_client = genai.Client(api_key=settings.google_api_key)

    try:
        repository.update_status(deck_id, "processing", {"error_message": None})
    except ValueError as exc:
        if _is_missing_deck_error(exc):
            logger.info("Slide deck task skipped because deck no longer exists deck_id=%s", deck_id)
            return _cancelled_result(deck_id, "missing")
        raise

    uploaded_storage_path: str | None = None
    try:
        chunks = document_repository.get_all_chunks_by_names(document_names, notebook_id)
        if not chunks:
            raise ValueError("No indexed chunks were found for the selected documents.")

        context = _build_context(chunks)
        coverage_topics = _expected_coverage_topics(context)
        if len(context) > MAX_CONTEXT_CHARS:
            context = _summarize_context(genai_client, app_config.llm.gemini.model, context, document_names)

        visual_candidates = _visual_candidates(chunks)
        deck, outline = _generate_deck(
            genai_client=genai_client,
            model=app_config.llm.gemini.model,
            context=context,
            document_names=document_names,
            visual_candidates=visual_candidates,
            coverage_topics=coverage_topics,
        )
        deck_json = _materialize_visuals(
            deck=deck.model_dump(),
            genai_client=genai_client,
            image_model=app_config.slide_deck.image_model,
            crop_model=app_config.llm.gemini.model,
            client=client,
            settings=settings,
            user_id=user_id,
            notebook_id=notebook_id,
            visual_candidates=visual_candidates,
        )
        deck_json["story_outline"] = outline.model_dump()
        deck_json["source_count"] = len(document_names)

        with tempfile.TemporaryDirectory(prefix="datn-slide-deck-") as temp_dir:
            workspace = Path(temp_dir)
            pdf_path = workspace / "presentation.pdf"
            pdf_renderer = _render_deck_pdf_for_config(deck_json, pdf_path, app_config.slide_deck)
            deck_json["pdf_renderer"] = pdf_renderer
            deck_json.setdefault("pdf_renderer_version", "pillow" if pdf_renderer == "pillow_fallback" else "unknown")

            storage_path = f"{user_id}/{notebook_id}/{deck_id}.pdf"
            if not repository.get(deck_id):
                logger.info("Slide deck task cancelled before upload deck_id=%s", deck_id)
                return _cancelled_result(deck_id, "deleted")

            _upload_pdf(client, settings.slide_deck_bucket, storage_path, pdf_path)
            uploaded_storage_path = storage_path

        metadata = {
            "document_names": document_names,
            "source_count": len(document_names),
            "task_id": self.request.id,
            "title": str(deck_json.get("title") or "Presentation"),
            "deck_json": deck_json,
            "content_type": "application/pdf",
            "error_message": None,
            "planner_model": app_config.llm.gemini.model,
            "image_model": app_config.slide_deck.image_model,
            "pdf_renderer": pdf_renderer,
        }
        try:
            repository.update_status(deck_id, "completed", metadata, storage_path=storage_path)
        except ValueError as exc:
            if _is_missing_deck_error(exc):
                _remove_uploaded_pdf(client, settings.slide_deck_bucket, uploaded_storage_path)
                logger.info("Slide deck task finished after deck was deleted deck_id=%s", deck_id)
                return _cancelled_result(deck_id, "deleted")
            raise

        return {
            "deck_id": deck_id,
            "status": "completed",
            "slide_count": len(deck_json.get("slides", [])),
            "storage_path": storage_path,
            "pdf_renderer": pdf_renderer,
        }
    except Exception as exc:
        logger.exception("Slide deck generation failed deck_id=%s notebook_id=%s", deck_id, notebook_id)
        try:
            repository.update_status(
                deck_id,
                "failed",
                {
                    "document_names": document_names,
                    "source_count": len(document_names),
                    "task_id": self.request.id,
                    "error_message": str(exc),
                },
            )
        except ValueError as update_exc:
            if _is_missing_deck_error(update_exc):
                _remove_uploaded_pdf(client, settings.slide_deck_bucket, uploaded_storage_path)
                logger.info("Slide deck failure ignored because deck was deleted deck_id=%s", deck_id)
                return _cancelled_result(deck_id, "deleted")
            raise
        raise


def _upload_pdf(client: Any, bucket: str, storage_path: str, pdf_path: Path) -> None:
    file_options = {"content-type": "application/pdf"}
    with pdf_path.open("rb") as file:
        try:
            client.storage.from_(bucket).update(storage_path, file, file_options=file_options)
        except Exception:
            file.seek(0)
            client.storage.from_(bucket).upload(storage_path, file, file_options=file_options)


def _remove_uploaded_pdf(client: Any, bucket: str, storage_path: str | None) -> None:
    if not storage_path:
        return
    try:
        client.storage.from_(bucket).remove([storage_path])
    except Exception:
        logger.info("Could not remove cancelled slide deck object path=%s.", storage_path, exc_info=True)


def _is_missing_deck_error(exc: Exception) -> bool:
    return isinstance(exc, ValueError) and str(exc) == "Slide deck not found."


def _cancelled_result(deck_id: str, reason: str) -> dict[str, Any]:
    return {
        "deck_id": deck_id,
        "status": "cancelled",
        "reason": reason,
    }
