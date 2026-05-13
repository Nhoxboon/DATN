"""Main FastAPI application factory."""

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import get_settings
from app.routers import auth, notebooks


logger = logging.getLogger(__name__)
runtime_logger = logging.getLogger("uvicorn.error")


def _worker_mode_active(document_processing_mode: str) -> bool:
    return document_processing_mode.strip().lower() == "worker"


def _enforce_worker_mode(settings) -> None:
    if settings.datn_require_worker_mode and not _worker_mode_active(settings.document_processing_mode):
        raise RuntimeError(
            "DATN_REQUIRE_WORKER_MODE is enabled, but DOCUMENT_PROCESSING_MODE is not 'worker'. "
            "Docker/production indexing must run through Celery worker mode."
        )


def create_app() -> FastAPI:
    """Create and configure the DATN backend application."""
    settings = get_settings()
    _enforce_worker_mode(settings)

    app = FastAPI(
        title="DATN API",
        description="Authentication API shell for DATN and future RAG modules",
        version="0.1.0",
        docs_url="/docs",
        redoc_url="/redoc",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(auth.router)
    app.include_router(notebooks.router)

    @app.on_event("startup")
    async def log_runtime_settings() -> None:
        message = (
            "DATN runtime settings: document_processing_mode=%s worker_mode_active=%s "
            "require_worker_mode=%s redis_url=%s uploads_dir=%s"
        )
        args = (
            settings.document_processing_mode,
            _worker_mode_active(settings.document_processing_mode),
            settings.datn_require_worker_mode,
            settings.redis_url,
            settings.uploads_dir,
        )
        logger.info(message, *args)
        runtime_logger.info(message, *args)
        print(
            "DATN runtime settings: document_processing_mode=%s worker_mode_active=%s "
            "require_worker_mode=%s redis_url=%s uploads_dir=%s" % args,
            flush=True,
        )

    @app.get("/health", tags=["health"])
    async def health() -> dict[str, str | bool]:
        """Health check endpoint."""
        return {
            "status": "ok",
            "document_processing_mode": settings.document_processing_mode,
            "worker_mode_active": _worker_mode_active(settings.document_processing_mode),
            "require_worker_mode": settings.datn_require_worker_mode,
        }

    return app


app = create_app()
