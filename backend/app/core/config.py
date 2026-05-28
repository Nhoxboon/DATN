"""Application configuration."""

from functools import lru_cache
from pathlib import Path
from typing import Optional

import yaml
from pydantic import BaseModel, field_validator
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
    optimized_model_path: Optional[str] = None
    retrieval: RetrievalConfig
    generation: GenerationConfig
    multihop: MultiHopConfig
    reranking: RerankingConfig


class SlideDeckConfig(BaseModel):
    """Slide deck generation settings."""

    image_model: str
    pdf_renderer: str = "browser"
    pdf_renderer_fallback: str = "pillow"
    browser_render_timeout_seconds: int = 30
    browser_max_retries: int = 2
    browser_screenshot_scale: float = 2


class AudioOverviewConfig(BaseModel):
    """Audio overview generation settings."""

    tts_model: str = "gemini-2.5-flash-preview-tts"
    min_duration_seconds: int = 150
    min_script_words: int = 460
    max_context_chars: int = 42000
    batch_context_chars: int = 6000
    max_render_attempts: int = 3
    audio_rate: int = 24000
    script_temperature: float = 0.45
    script_max_output_tokens: int = 7000
    podcast_speakers: list[str] = Field(default_factory=lambda: ["Speaker A", "Speaker B"])
    briefing_speakers: list[str] = Field(default_factory=lambda: ["Narrator"])
    podcast_voices: list[str] = Field(default_factory=lambda: ["Kore", "Puck"])
    briefing_voice: str = "Charon"
    encode_bitrate: str = "96k"
    encode_timeout_seconds: int = 300
    probe_timeout_seconds: int = 60

    @field_validator("podcast_speakers", "podcast_voices")
    @classmethod
    def require_two_items(cls, value: list[str]) -> list[str]:
        """Require two configured entries for Gemini multi-speaker TTS."""
        clean_value = [item.strip() for item in value if item.strip()]
        if len(clean_value) != 2:
            raise ValueError("must contain exactly two non-empty values")
        return clean_value

    @field_validator("briefing_speakers")
    @classmethod
    def require_one_item(cls, value: list[str]) -> list[str]:
        """Require one configured entry for single-speaker TTS."""
        clean_value = [item.strip() for item in value if item.strip()]
        if len(clean_value) != 1:
            raise ValueError("must contain exactly one non-empty value")
        return clean_value

    @field_validator("tts_model", "briefing_voice", "encode_bitrate")
    @classmethod
    def require_non_empty_string(cls, value: str) -> str:
        """Reject empty audio overview string settings."""
        clean_value = value.strip()
        if not clean_value:
            raise ValueError("must not be empty")
        return clean_value


class AppConfig(BaseModel):
    """Application configuration from YAML."""

    llm: LLMSettings
    pdf: PDFConfig
    slide_deck: SlideDeckConfig
    audio_overview: AudioOverviewConfig
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
    audio_overview_bucket: str = Field(default="audio-overviews", description="Supabase Storage bucket for audio overviews")
    slide_deck_bucket: str = Field(default="slide-decks", description="Supabase Storage bucket for slide deck PDFs")
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
