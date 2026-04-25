"""Application configuration using pydantic-settings and YAML."""

from functools import lru_cache
from pathlib import Path
import yaml
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class LLMConfig(BaseModel):
    """LLM configuration."""
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
    """PDF processing configuration."""
    use_llm: bool
    llm_model: str


class ChunkingConfig(BaseModel):
    """Chunking configuration."""
    strategy: str
    chunk_size: int
    similarity_threshold: float


class VectorDBConfig(BaseModel):
    """Vector database configuration."""
    embedding_dimension: int
    similarity_metric: str


class RetrievalConfig(BaseModel):
    """RAG retrieval configuration."""
    top_k: int
    similarity_threshold: float
    per_document_k: int = 10
    use_reranking: bool = True


class GenerationConfig(BaseModel):
    """RAG generation configuration."""
    temperature: float
    max_tokens: int


class MultiHopConfig(BaseModel):
    """Multi-hop RAG configuration."""
    enabled: bool
    max_hops: int
    passages_per_hop: int


class RerankingConfig(BaseModel):
    """Reranking configuration."""
    model: str = "BAAI/bge-reranker-v2-m3"
    enabled: bool = True


class RAGConfig(BaseModel):
    """RAG configuration."""
    mode: str  # "adaptive", "single-hop", "multi-hop"
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
    """Environment settings."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False
    )

    # Supabase
    supabase_url: str = Field(..., description="Supabase project URL")
    supabase_anon_key: str = Field(..., description="Supabase anonymous key")
    supabase_service_key: str = Field(..., description="Supabase service role key")

    # Redis
    redis_url: str = Field(..., description="Redis connection URL")

    # Gemini API
    google_api_key: str = Field(..., description="Google Gemini API key")


def load_app_config(config_path: str = "config.yaml") -> AppConfig:
    """
    Load application configuration from YAML file.

    Args:
        config_path: Path to config YAML file

    Returns:
        AppConfig instance
    """
    config_file = Path(config_path)
    if not config_file.exists():
        raise FileNotFoundError(f"Config file not found: {config_path}")

    with open(config_file, "r") as f:
        config_data = yaml.safe_load(f)

    return AppConfig(**config_data)


@lru_cache()
def get_settings() -> Settings:
    """
    Get settings instance (cached).

    Returns:
        Settings loaded from .env file
    """
    return Settings()  # type: ignore[call-arg]


@lru_cache()
def get_app_config(config_path: str = "config.yaml") -> AppConfig:
    """
    Get application configuration (cached).

    Args:
        config_path: Path to config YAML file

    Returns:
        AppConfig instance
    """
    return load_app_config(config_path)
