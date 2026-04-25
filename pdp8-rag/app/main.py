"""Main FastAPI application factory."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from app.routers import rag, documents
from app.api import chat
from app.services.rag.dependencies import initialize_dspy

# Initialize DSPy at module level before any async context is created
# This ensures it's configured once per worker process
initialize_dspy()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Handle application startup and shutdown."""
    # DSPy already initialized at module level

    # Pre-initialize RAG service to avoid cold start on first request
    # This loads heavy models (reranker, embeddings) at startup
    from app.services.rag.dependencies import get_rag_service
    print("[INFO] Pre-initializing RAG service...")
    try:
        rag_service = get_rag_service()
        print(f"[INFO] RAG service initialized successfully (mode: {rag_service.mode})")
    except Exception as e:
        print(f"[WARNING] Failed to pre-initialize RAG service: {e}")

    yield


def create_app() -> FastAPI:
    """
    Create and configure FastAPI application.

    Returns:
        Configured FastAPI app
    """
    app = FastAPI(
        title="PDP8 RAG API",
        description="RAG system for analyzing Vietnam's Electricity Master Plan VIII (PDP8)",
        version="1.0.0",
        docs_url="/docs",
        redoc_url="/redoc",
        lifespan=lifespan
    )

    # Add CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],  # In production, specify actual origins
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Include routers
    app.include_router(rag.router)
    app.include_router(documents.router)
    app.include_router(chat.router)

    @app.get("/")
    async def root():
        """Root endpoint."""
        return {
            "message": "PDP8 RAG API",
            "version": "1.0.0",
            "docs": "/docs",
            "health": "/rag/health"
        }

    return app


# Create app instance
app = create_app()
