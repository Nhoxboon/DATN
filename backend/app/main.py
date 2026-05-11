"""Main FastAPI application factory."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import get_settings
from app.routers import auth, notebooks


def create_app() -> FastAPI:
    """Create and configure the DATN backend application."""
    settings = get_settings()
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

    @app.get("/health", tags=["health"])
    async def health() -> dict[str, str]:
        """Health check endpoint."""
        return {"status": "ok"}

    return app


app = create_app()
