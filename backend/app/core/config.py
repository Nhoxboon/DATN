"""Application configuration."""

from functools import lru_cache
from pathlib import Path
from typing import Optional

import yaml
from pydantic import BaseModel
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


BACKEND_ROOT = Path(__file__).resolve().parents[2]
PROJECT_ROOT = Path(__file__).resolve().parents[3]


class LLMConfig(BaseModel):
    """LLM configuration loaded from config.yaml."""

    model: str
    embedding_model: str
    temperature: float
    max_tokens: int


class LLMSettings(BaseModel):
    """LLM provider settings."""

    provider: str
    gemini: LLMConfig
    openai: LLMConfig


class PDFConfig(BaseModel):
    """PDF processing settings."""

    use_llm: bool
    llm_model: str
    describe_images: bool = False
    image_caption_model: Optional[str] = None


class ChunkingConfig(BaseModel):
    """Document chunking settings."""

    strategy: str
    chunk_size: int
    similarity_threshold: float


class VectorDBConfig(BaseModel):
    """Vector database settings."""

    embedding_dimension: int
    similarity_metric: str


class RetrievalConfig(BaseModel):
    """RAG retrieval settings."""

    top_k: int
    similarity_threshold: float
    per_document_k: int = 10
    initial_chunks_per_doc: int = 2
    top_n_documents: int = 5
    deep_chunks_per_doc: int = 8
    use_reranking: bool = True


class GenerationConfig(BaseModel):
    """RAG generation settings."""

    temperature: float
    max_tokens: int


class MultiHopConfig(BaseModel):
    """Multi-hop RAG settings."""

    enabled: bool
    max_hops: int
    passages_per_hop: int


class RerankingConfig(BaseModel):
    """Reranking settings."""

    model: str = "BAAI/bge-reranker-v2-m3"
    enabled: bool = True


class RAGConfig(BaseModel):
    """RAG settings."""

    mode: str
    retrieval: RetrievalConfig
    generation: GenerationConfig
    multihop: MultiHopConfig
    reranking: RerankingConfig


class AppConfig(BaseModel):
    """Application configuration from YAML."""

    llm: LLMSettings
    pdf: PDFConfig
    chunking: ChunkingConfig
    vector_db: VectorDBConfig
    rag: RAGConfig


class Settings(BaseSettings):
    """Environment settings for the backend."""

    model_config = SettingsConfigDict(
        env_file=(str(PROJECT_ROOT / ".env"), str(BACKEND_ROOT / ".env")),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    supabase_url: str = Field(..., description="Supabase project URL")
    supabase_anon_key: str = Field(..., description="Supabase anonymous key")
    supabase_service_key: str = Field(..., description="Supabase service role key")
    redis_url: str = Field(..., description="Redis connection URL for streaming/cache")
    google_api_key: str = Field(..., description="Google Gemini API key for future RAG modules")
    document_processing_mode: str = Field(default="worker", description="Document processing mode: worker")
    uploads_dir: str = Field(default="/app/uploads", description="Local shared upload directory for worker mode")
    datn_require_worker_mode: bool = Field(
        default=False,
        description="Fail startup unless document processing is configured for Celery worker mode",
    )

    @property
    def cors_origins(self) -> list[str]:
        """Allowed origins for browser requests."""
        return ["*"]


@lru_cache
def get_settings() -> Settings:
    """Return cached settings."""
    return Settings()  # type: ignore[call-arg]


def load_app_config(config_path: str | Path = BACKEND_ROOT / "config.yaml") -> AppConfig:
    """Load RAG application configuration from YAML."""
    config_file = Path(config_path)
    if not config_file.exists():
        raise FileNotFoundError(f"Config file not found: {config_file}")

    with config_file.open("r", encoding="utf-8") as file:
        config_data = yaml.safe_load(file)

    return AppConfig(**config_data)


@lru_cache
def get_app_config(config_path: str | Path = BACKEND_ROOT / "config.yaml") -> AppConfig:
    """Return cached RAG configuration."""
    return load_app_config(config_path)
